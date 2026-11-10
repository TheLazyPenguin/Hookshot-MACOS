"""The Ampere -> Maxwell lowering does not take an immediate's low byte for a register in the scratch range.

Two of OoT's large compute programs (~32,000 instructions) were refused as "native program uses lowering scratch
registers" at LOP3.LUT R231, R231, 0xfffffffe (and R236, R236, 0xfffffffd): with the uniform register bank in use, R231
is a high GPR, and the scan that marks an instruction's high GPRs went over every 8-bit field, the immediate's low byte at
bit 32 too, so 0xfe was taken for R254, a scratch register. The check that decides whether an instruction has high GPRs
at all already counted only the fields that hold registers; the marking now does the same.
python -I -B tests/test_lower_immediate_not_register.py [--cxx clang++]
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
// LDG.E R1, [UR4+0x2c]: puts the uniform register bank in use (R216 and up are then high GPRs)
static const Instruction uniform_ldg = insn(0xff017981, 0x00002c04, 0x0c1e8900, 0x000ea800);
static Shader::Ampere::LoweredProgram lower3(Instruction i) {
    return Shader::Ampere::LowerToMaxwell(std::vector<Instruction>{uniform_ldg, i, exit_insn});
}
int main() {
    // LOP3.LUT R231, R231, 0xfffffffe, RZ, 0xc0 and R236, R236, 0xfffffffd (the two programs, from the log)
    CHECK(lower3(insn(0xe7e77812, 0xfffffffe, 0x078ec0ff, 0x000fc600)));
    CHECK(lower3(insn(0xecec7812, 0xfffffffd, 0x078ec0ff, 0x000fd600)));
    // an immediate below the scratch registers lowered before as well
    CHECK(lower3(insn(0xe7e77812, 0x00000010, 0x078ec0ff, 0x000fc600)));
    std::printf("PASS: an immediate's low byte is not taken for a scratch register\n");
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default=shutil.which("clang++") and "clang++" or "g++")
    a = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="lower-imm-reg-") as tmp:
        cpp = Path(tmp) / "fixture.cpp"
        exe = Path(tmp) / "fixture"
        cpp.write_text(FIXTURE, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-O1", "-Wno-everything" if "clang" in a.cxx else "-w",
                        "-I" + str(ROOT / "gpu" / "vk" / "eden"), "-I" + str(ROOT / "gpu" / "vk" / "compat"),
                        str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
