"""The Ampere -> Maxwell lowering takes IMNMX with an immediate wider than Maxwell's 20 bits (native op 0x817).

Three of OoT's vertex programs stopped at it as "native integer min/max mode": IMNMX R, R, 0x7f0004, PT does not fit
Maxwell IMNMX's signed 20-bit immediate. Such an immediate now goes into R251 (MOV32I) and the register form is used;
one that fits keeps the immediate form.
python -I -B tests/test_lower_imnmx_wide_immediate.py [--cxx clang++]
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
static uint64_t mov32i(uint32_t d, uint32_t value) { return 0x0100000000000000ULL | PT | d | (15ULL << 12) | (uint64_t{value} << 20); }
// Maxwell IMNMX (register form) Rd = min/max(Ra, Rb) by the predicate in 39-42, .U32 unless bit 48
static uint64_t imnmx_r(uint32_t d, uint32_t a, uint32_t b, bool sign = false) {
    return 0x5c20000000000000ULL | PT | d | (uint64_t{a} << 8) | (uint64_t{b} << 20) | (7ULL << 39) | (uint64_t{sign} << 48);
}
static uint64_t imnmx_i(uint32_t d, uint32_t a, uint32_t imm) {
    return 0x3820000000000000ULL | PT | d | (uint64_t{a} << 8) | (uint64_t{imm & 0x7ffff} << 20) |
           (uint64_t{imm >> 31} << 56) | (7ULL << 39);
}
int main() {
    {   // IMNMX.U32 R26, R25, 0x7f0004, PT (from the log): the immediate in R251, then the register form
        const auto r = lower(insn(0x191a7817, 0x007f0004, 0x03800000, 0x000fc400));
        CHECK(r);
        CHECK(r.instructions.size() >= 2);
        CHECK(r.instructions[0] == mov32i(251, 0x007f0004));
        CHECK(r.instructions[1] == imnmx_r(0x1a, 0x19, 251));
    }
    {   // R38, R35 and R32, R28 (the other two)
        CHECK(lower(insn(0x23267817, 0x007f0004, 0x03800000, 0x000fe200)).instructions[1] == imnmx_r(0x26, 0x23, 251));
        CHECK(lower(insn(0x1c207817, 0x007f0004, 0x03800000, 0x000fe200)).instructions[1] == imnmx_r(0x20, 0x1c, 251));
    }
    {   // an immediate that fits keeps the immediate form, positive and negative
        const auto r = lower(insn(0x191a7817, 0x0007ffff, 0x03800000, 0x000fc400));
        CHECK(r && r.instructions[0] == imnmx_i(0x1a, 0x19, 0x0007ffff));
        const auto n = lower(insn(0x191a7817, 0xfffffff0, 0x03800000, 0x000fc400));
        CHECK(n && n.instructions[0] == imnmx_i(0x1a, 0x19, 0xfffffff0));
    }
    {   // the boundaries: 0x00080000 and 0xfff7ffff do not fit a signed 20-bit immediate, 0xfff80000 does
        const auto up = lower(insn(0x191a7817, 0x00080000, 0x03800000, 0x000fc400));
        CHECK(up && up.instructions[0] == mov32i(251, 0x00080000) && up.instructions[1] == imnmx_r(0x1a, 0x19, 251));
        const auto down = lower(insn(0x191a7817, 0xfff7ffff, 0x03800000, 0x000fc400));
        CHECK(down && down.instructions[0] == mov32i(251, 0xfff7ffff) && down.instructions[1] == imnmx_r(0x1a, 0x19, 251));
        const auto fits = lower(insn(0x191a7817, 0xfff80000, 0x03800000, 0x000fc400));
        CHECK(fits && fits.instructions[0] == imnmx_i(0x1a, 0x19, 0xfff80000));
    }
    {   // .S32 (word 2 bit 9, native bit 73): bit 48 in the register form too
        const auto r = lower(insn(0x191a7817, 0x007f0004, 0x03800200, 0x000fc400));
        CHECK(r && r.instructions[1] == imnmx_r(0x1a, 0x19, 251, true));
    }
    std::printf("PASS: IMNMX with a wide immediate lowers through R251\n");
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default=shutil.which("clang++") and "clang++" or "g++")
    a = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="lower-imnmx-") as tmp:
        cpp = Path(tmp) / "fixture.cpp"
        exe = Path(tmp) / "fixture"
        cpp.write_text(FIXTURE, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-O1", "-Wno-everything" if "clang" in a.cxx else "-w",
                        "-I" + str(ROOT / "gpu" / "vk" / "eden"), "-I" + str(ROOT / "gpu" / "vk" / "compat"),
                        str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
