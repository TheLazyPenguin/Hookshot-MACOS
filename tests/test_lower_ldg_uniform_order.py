"""The Ampere -> Maxwell lowering takes LDG and STG [URn+imm] with ordering bit 78 set beside 77 (native ops 0x981, 0x986).

Two of OoT's compute programs stopped at the load as "native global load uniform addressing mode", and one of them then
at a store as "native global store uniform addressing mode": the uniform-address forms allowed bit 77 (as the register
form does: a Maxwell LDG or STG needs nothing for the memory ordering) but not 78 beside it. They are Maxwell LDG.E /
STG.E of the uniform register pair plus the offset, their sizes as before, fenced by MEMBAR.GL on both sides when
bit 78 is set (77-79 all set: .STRONG.GPU, as SUST.STRONG.GPU is). Other unknown bits stay refused.
python -I -B tests/test_lower_ldg_uniform_order.py [--cxx clang++]
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
#include <algorithm>
#include <string>
#include <vector>
#include "shader_recompiler/frontend/ampere/lower_to_maxwell.h"
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL:%d %s\n", __LINE__, #x); std::exit(1); } } while (0)
using Shader::Ampere::Instruction;
static Instruction insn(uint32_t a, uint32_t b, uint32_t c, uint32_t d) { Instruction i{}; i.words[0] = a; i.words[1] = b; i.words[2] = c; i.words[3] = d; return i; }
static const Instruction exit_insn = insn(0x0000794d, 0, 0x03800000, 0x000fea00);   // EXIT
static Shader::Ampere::LoweredProgram lower(Instruction i) { return Shader::Ampere::LowerToMaxwell(std::vector<Instruction>{i, exit_insn}); }
static const uint64_t* find_ldg(const Shader::Ampere::LoweredProgram& r) {
    for (const uint64_t& i : r.instructions) if ((i >> 51) == (0xeed0000000000000ULL >> 51)) return &i;   // LDG, not STG
    return nullptr;
}
static int membars(const Shader::Ampere::LoweredProgram& r) {
    int n = 0;
    for (const uint64_t& i : r.instructions) n += (i & 0xfff8000000000f00ULL) == 0xef98000000000100ULL;   // MEMBAR.GL
    return n;
}
static void check(uint32_t w0, uint32_t w1, uint32_t w2, uint32_t dest, uint32_t offset, uint32_t size) {
    const auto r = lower(insn(w0, w1, w2, 0x000ea800));
    CHECK(r);
    // bit 78 (with 77 and 79): .STRONG.GPU, fenced by MEMBAR.GL on both sides; without it, no fence
    CHECK(membars(r) == ((w2 >> 14) & 1 ? 2 : 0));
    const uint64_t* ldg = find_ldg(r);
    CHECK(ldg);
    CHECK((*ldg & 0xff) == dest);                          // Rd
    CHECK(((*ldg >> 20) & 0xffffff) == offset);            // the immediate offset
    CHECK(((*ldg >> 48) & 7) == size);                     // 32 or 128 bits
    CHECK(((*ldg >> 45) & 1) == 1);                        // .E: a 64-bit address
    const uint32_t address = (*ldg >> 8) & 0xff;
    CHECK(address != 255 && (address & 1) == 0);           // the uniform pair, in an aligned register pair
}
int main() {
    // LDG.E [UR4+0x2c] into R1 (32 bits) and [UR4+0x20] into R8 (128 bits), ordering bits 77 and 78 set (the log's two)
    check(0xff017981, 0x00002c04, 0x0c1ee900, 1, 0x2c, 4);
    check(0xff087981, 0x00002004, 0x0c1eed00, 8, 0x20, 6);
    // bit 77 alone and neither, as before
    check(0xff017981, 0x00002c04, 0x0c1ea900, 1, 0x2c, 4);
    check(0xff017981, 0x00002c04, 0x0c1e8900, 1, 0x2c, 4);
    // still refused: bit 76 in the uniform form, an odd uniform register
    CHECK(!lower(insn(0xff017981, 0x00002c04, 0x0c1ef900, 0x000ea800)));
    CHECK(!lower(insn(0xff017981, 0x00002c05, 0x0c1ee900, 0x000ea800)));
    {   // STG.E [UR6+0x30], R7 (32 bits), bits 77-79 set (the second program's store): Maxwell STG.E, data R7
        const auto r = lower(insn(0xff000986, 0x00003007, 0x0c10e906, 0x000fee00));
        CHECK(r);
        const uint64_t* stg = nullptr;
        for (const uint64_t& i : r.instructions) if ((i >> 51) == (0xeed8000000000000ULL >> 51)) stg = &i;
        CHECK(membars(r) == 2);   // .STRONG.GPU: fenced
        CHECK(stg && (*stg & 0xff) == 7 && ((*stg >> 20) & 0xffffff) == 0x30 && ((*stg >> 48) & 7) == 4 &&
              ((*stg >> 45) & 1) == 1 && (((*stg >> 8) & 0xff) & 1) == 0);
        CHECK(membars(lower(insn(0xff000986, 0x00003007, 0x0c10a906, 0x000fee00))) == 0);   // bits 77 and 79, as before
        CHECK(!lower(insn(0xff000986, 0x00003007, 0x0c10f906, 0x000fee00)));   // bit 76: still refused
    }
    std::printf("PASS: LDG and STG [URn+imm] with ordering bits 77-78 lower to Maxwell LDG.E / STG.E\n");
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default=shutil.which("clang++") and "clang++" or "g++")
    a = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="lower-ldg-order-") as tmp:
        cpp = Path(tmp) / "fixture.cpp"
        exe = Path(tmp) / "fixture"
        cpp.write_text(FIXTURE, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-O1", "-Wno-everything" if "clang" in a.cxx else "-w",
                        "-I" + str(ROOT / "gpu" / "vk" / "eden"), "-I" + str(ROOT / "gpu" / "vk" / "compat"),
                        str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
