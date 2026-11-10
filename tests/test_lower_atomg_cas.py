"""The Ampere -> Maxwell lowering takes ATOMG.E.CAS (32-bit global compare-and-swap) to Maxwell's ATOM.E.CAS.

Six of OoT's compute programs stopped at it as "unsupported native opcode (native op 0x3a9)". Maxwell's ATOM.E.CAS
reads the comparator and the value as the pair Rb, Rb+1: an even Rb with Rc = Rb + 1 is passed as it is, anything
else is copied to R250/R251 first. The Maxwell frontend's ATOM_cas makes it GlobalAtomicCompareExchange32.
python -I -B tests/test_lower_atomg_cas.py [--cxx clang++]
"""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "g++"]

ROOT = Path(__file__).resolve().parents[1]
EDEN = ROOT / "gpu" / "vk" / "eden" / "shader_recompiler"

FIXTURE = r'''#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include "shader_recompiler/frontend/ampere/lower_to_maxwell.h"
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL:%d %s\n", __LINE__, #x); std::exit(1); } } while (0)
using Shader::Ampere::Instruction;
static Instruction insn(uint32_t a, uint32_t b, uint32_t c, uint32_t d) { Instruction i{}; i.words[0] = a; i.words[1] = b; i.words[2] = c; i.words[3] = d; return i; }
static const Instruction exit_insn = insn(0x0000794d, 0, 0x03800000, 0x000fea00);   // EXIT
static Shader::Ampere::LoweredProgram lower(Instruction i) { return Shader::Ampere::LowerToMaxwell(std::vector<Instruction>{i, exit_insn}); }
// ATOMG.E.CAS.STRONG.GPU PT, Rd, [Ra + offset], Rb, Rc
static Instruction cas(uint32_t d, uint32_t a, uint32_t b, uint32_t c, uint32_t offset = 0) {
    return insn(0x000073a9 | (d << 16) | (a << 24), b | (offset << 8), 0x001ee100 | c, 0x000ea400);
}
static uint64_t atom_cas(uint32_t d, uint32_t a, uint32_t pair, uint32_t offset = 0) {
    return 0xeef0000000000000ULL | (7ULL << 16) | d | (uint64_t{a} << 8) | (uint64_t{pair} << 20) |
           (uint64_t{offset & 0xfffff} << 28) | (1ULL << 48);
}
static uint64_t mov(uint32_t d, uint32_t s) { return 0x5c98000000000000ULL | (7ULL << 16) | d | (15ULL << 39) | (uint64_t{s} << 20); }
int main() {
    {   // ATOMG.E.CAS.STRONG.GPU PT, R0, [R0], R8, R9 (9a6fe9d7a7ce2007): the pair as it is
        const auto r = lower(cas(0, 0, 8, 9));
        CHECK(r);
        CHECK(r.instructions.size() >= 1 && r.instructions[0] == atom_cas(0, 0, 8));
    }
    {   // R36, [R36], R38, R39 with an offset of -16
        const auto r = lower(cas(36, 36, 38, 39, 0xfffff0));
        CHECK(r);
        CHECK(r.instructions[0] == atom_cas(36, 36, 38, 0xffff0));
    }
    {   // R30, [R38], R30, R31 (f4867235b77e1107): the destination is the comparator too
        const auto r = lower(cas(30, 38, 30, 31));
        CHECK(r);
        CHECK(r.instructions[0] == atom_cas(30, 38, 30));
    }
    {   // R4, [R2], R9, R6: not a pair, copied to R250/R251 first
        const auto r = lower(cas(4, 2, 9, 6));
        CHECK(r);
        CHECK(r.instructions.size() >= 3);
        CHECK(r.instructions[0] == mov(250, 9));
        CHECK(r.instructions[1] == mov(251, 6));
        CHECK(r.instructions[2] == atom_cas(4, 2, 250));
    }
    // a 64-bit CAS (size bits 73-75) and an odd address register are refused
    CHECK(!lower(insn(0x000073a9, 8, 0x001ee309, 0x000ea400)));
    CHECK(!lower(cas(0, 1, 8, 9)));
    std::printf("PASS: ATOMG.E.CAS lowers to ATOM.E.CAS with its operands as a pair\n");
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default=shutil.which("clang++") and "clang++" or "g++")
    a = p.parse_args()
    # The frontend's half: ATOM_cas translates (it threw "not implemented") into the new IR opcode, which the storage
    # buffer pass and the SPIR-V back end know
    atomics = (EDEN / "frontend" / "maxwell" / "translate" / "impl" / "atomic_operations_global_memory.cpp").read_text(encoding="utf-8")
    if "void TranslatorVisitor::ATOM_cas(u64 insn)" not in atomics or "GlobalAtomicCompareExchange(" not in atomics:
        raise SystemExit("the Maxwell frontend does not translate ATOM_cas")
    stub = (EDEN / "frontend" / "maxwell" / "translate" / "impl" / "not_implemented.cpp").read_text(encoding="utf-8")
    if "TranslatorVisitor::ATOM_cas" in stub:
        raise SystemExit("ATOM_cas is still a not-implemented stub")
    opcodes = (EDEN / "frontend" / "ir" / "opcodes.inc").read_text(encoding="utf-8")
    count = sum(1 for line in opcodes.splitlines() if line.startswith("OPCODE("))
    for f in ("opcodes.cpp", "opcodes.h"):
        text = (EDEN / "frontend" / "ir" / f).read_text(encoding="utf-8")
        if f"META_TABLE[{count}]" not in text or f"NUM_ARGS[{count}]" not in text:
            raise SystemExit(f"frontend/ir/{f}: the opcode tables are not sized for the {count} opcodes")
    storage = (EDEN / "ir_opt" / "global_memory_to_storage_buffer_pass.cpp").read_text(encoding="utf-8")
    if "return IR::Opcode::StorageAtomicCompareExchange32;" not in storage:
        raise SystemExit("the storage buffer pass does not turn the global compare-exchange into a storage one")
    spirv = (EDEN / "backend" / "spirv" / "emit_spirv_atomic.cpp").read_text(encoding="utf-8")
    for name in ("EmitStorageAtomicCompareExchange32", "EmitGlobalAtomicCompareExchange32"):
        if f"Id {name}(" not in spirv:
            raise SystemExit(f"the SPIR-V back end has no {name}")
    with tempfile.TemporaryDirectory(prefix="lower-atomg-cas-") as tmp:
        cpp = Path(tmp) / "fixture.cpp"
        exe = Path(tmp) / "fixture"
        cpp.write_text(FIXTURE, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-O1", "-Wno-everything" if "clang" in a.cxx else "-w",
                        "-I" + str(ROOT / "gpu" / "vk" / "eden"), "-I" + str(ROOT / "gpu" / "vk" / "compat"),
                        str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
