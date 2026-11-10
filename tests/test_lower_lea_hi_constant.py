"""The Ampere -> Maxwell lowering takes LEA.HI with a constant-buffer base and no carry (native op 0xa11).

Forty of OoT's vertex programs stopped at it as "native constant LEA carry mode", so they were never drawn:
LEA.HI Rd, Ra, c[bank][offset], RZ, s (no .X, no carry out) is the constant plus the high word of (Ra << s), that is
Ra shifted right by 32 - s (arithmetic with .SX32). It lowers to the constant in R251 (as every constant operand), a
Maxwell SHR of Ra into R250 and IADD Rd = R250 + R251, the register form's (0x211) high word.
python -I -B tests/test_lower_lea_hi_constant.py [--cxx clang++]
"""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "g++"]

ROOT = Path(__file__).resolve().parents[1]

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
static constexpr uint64_t PT = 7ULL << 16;
// the constant c[bank][offset] into R251 (Maxwell MOV c[][], as every constant operand)
static uint64_t ldc(uint32_t bank, uint32_t offset) {
    return 0x4c98000000000000ULL | PT | 251 | (15ULL << 39) | (uint64_t{offset / 4} << 20) | (uint64_t{bank} << 34);
}
static uint64_t shr(uint32_t a, uint32_t amount, bool sign) {
    return 0x3828000000000000ULL | PT | 250 | (uint64_t{a} << 8) | (uint64_t{amount} << 20) | (uint64_t{sign} << 48);
}
static uint64_t iadd(uint32_t d) { return 0x5c10000000000000ULL | PT | d | (250ULL << 8) | (251ULL << 20); }
int main() {
    {   // LEA.HI R0, R13, c[0x3][0xc4], RZ, 0x1b (e9274029dc836a07, 2d279e3ea5e7499f): c + (R13 >> 5)
        const auto r = lower(insn(0x0d007a11, 0x00c03100, 0x078fd8ff, 0x000fe400));
        CHECK(r);
        CHECK(r.instructions.size() >= 3);
        CHECK(r.instructions[0] == ldc(3, 0xc4));
        CHECK(r.instructions[1] == shr(13, 5, false));
        CHECK(r.instructions[2] == iadd(0));
    }
    {   // LEA.HI R0, R4, c[0x3][0xc4], RZ, 0x1b (269f35e2fa245b12)
        const auto r = lower(insn(0x04007a11, 0x00c03100, 0x078fd8ff, 0x000fe400));
        CHECK(r);
        CHECK(r.instructions[1] == shr(4, 5, false) && r.instructions[2] == iadd(0));
    }
    {   // .SX32 (bit 73): an arithmetic shift; another destination (R7) and shift (8: Ra >> 24)
        const auto r = lower(insn(0x03077a11, 0x00c03100, 0x078f42ff, 0x000fe400));
        CHECK(r);
        CHECK(r.instructions[0] == ldc(3, 0xc4));
        CHECK(r.instructions[1] == shr(3, 24, true));
        CHECK(r.instructions[2] == iadd(7));
    }
    // LEA.HI.X.SX32 (bits 73-74) keeps its own lowering: the carry predicate is added (more than three instructions)
    {
        const auto r = lower(insn(0x0d007a11, 0x00c03100, 0x078fdeff, 0x000fe400));
        CHECK(r);
        CHECK(r.instructions.size() > 4);
    }
    // a carry out (bits 81-83 not PT), a high source (Rc not RZ) and a zero shift are still refused
    CHECK(!lower(insn(0x0d007a11, 0x00c03100, 0x078dd8ff, 0x000fe400)));
    CHECK(!lower(insn(0x0d007a11, 0x00c03100, 0x078fd805, 0x000fe400)));
    CHECK(!lower(insn(0x0d007a11, 0x00c03100, 0x078f00ff, 0x000fe400)));
    std::printf("PASS: LEA.HI with a constant base and no carry lowers to SHR + IADD\n");
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default=shutil.which("clang++") and "clang++" or "g++")
    a = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="lower-lea-hi-") as tmp:
        cpp = Path(tmp) / "fixture.cpp"
        exe = Path(tmp) / "fixture"
        cpp.write_text(FIXTURE, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-O1", "-Wno-everything" if "clang" in a.cxx else "-w",
                        "-I" + str(ROOT / "gpu" / "vk" / "eden"), "-I" + str(ROOT / "gpu" / "vk" / "compat"),
                        str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
