"""The Ampere -> Maxwell lowering takes R2UR's source as one register, not a pair (native op 0x3c2).

One of OoT's vertex programs was refused as "native program uses lowering scratch registers" at R2UR UR6, R238: with the
uniform bank in use R238 is a high GPR, and with no span known for R2UR's source its alignment made it a pair, R238 and
R239 (R236, 4-aligned, the quad up to R239). R239 is the lowering's own scratch register, which R2UR's eight
words use. R2UR reads one 32-bit register; R239 itself is still refused.
python -I -B tests/test_lower_r2ur_one_register.py [--cxx clang++]
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
int main() {
    CHECK(lower(insn(0xee0673c2, 0x00000000, 0x000e0000, 0x000e2200)));   // R2UR UR6, R238 (from the log)
    // R2UR UR6, R236: refused on main too (4-aligned, taken for the quad R236-R239), a second case the one-register span fixes
    CHECK(lower(insn(0xec0673c2, 0x00000000, 0x000e0000, 0x000e2200)));
    // R2UR UR6, R239: R239 itself is the lowering's scratch, and still refused
    CHECK(!lower(insn(0xef0673c2, 0x00000000, 0x000e0000, 0x000e2200)));
    std::printf("PASS: R2UR reads one register\n");
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default=shutil.which("clang++") and "clang++" or "g++")
    a = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="lower-r2ur-") as tmp:
        cpp = Path(tmp) / "fixture.cpp"
        exe = Path(tmp) / "fixture"
        cpp.write_text(FIXTURE, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-O1", "-Wno-everything" if "clang" in a.cxx else "-w",
                        "-I" + str(ROOT / "gpu" / "vk" / "eden"), "-I" + str(ROOT / "gpu" / "vk" / "compat"),
                        str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
