"""The Ampere -> Maxwell lowering takes SULD.P on a 1D surface (native op 0xb97, dimension code 0).

Seventeen of OoT's compute programs stopped at it as "native formatted surface load mode": the lowering took only 2D,
2D_ARRAY and 3D. 1D is Maxwell SULD.P with dimension code 0 and one coordinate register, which the Maxwell frontend
already reads as a Color1D image (and the back end binds as VK_IMAGE_VIEW_TYPE_1D). 1D_BUFFER and 1D_ARRAY are not seen
in the game and stay refused.
python -I -B tests/test_lower_suld_1d.py [--cxx clang++]
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
// Maxwell SULD.P Rd, [Ra], dimension, channel mask, the descriptor at its offset in the bound buffer
static uint64_t suld(uint32_t d, uint32_t a, uint32_t channels, uint32_t dimension, uint32_t offset) {
    return 0xeb00000000000000ULL | (7ULL << 16) | d | (uint64_t{a} << 8) | (uint64_t{channels} << 20) |
           (uint64_t{dimension} << 33) | (uint64_t{offset} << 36) | (1ULL << 51);
}
int main() {
    {   // SULD.P.1D.R.IGN R0, [R0], the descriptor at 0x10 (16 programs, from the log)
        const auto r = lower(insn(0x00007b97, 0x00001000, 0x001e0100, 0x000f6200));
        CHECK(r);
        CHECK(r.instructions.size() >= 1 && r.instructions[0] == suld(0, 0, 1, 0, 0x10));
        CHECK(r.required_texture_buffer == 0);
    }
    {   // SULD.P.1D.R.IGN R0, [R1], the descriptor at 0x8 (the 17th)
        const auto r = lower(insn(0x01007b97, 0x00000800, 0x001e0100, 0x000f6200));
        CHECK(r);
        CHECK(r.instructions.size() >= 1 && r.instructions[0] == suld(0, 1, 1, 0, 0x8));
    }
    {   // 2D (dimension code 3) as before
        const auto r = lower(insn(0x04027b97, 0x60001000, 0x001e0f00, 0x000f6200));
        CHECK(r);
        CHECK(r.instructions.size() >= 1 && r.instructions[0] == suld(2, 4, 15, 3, 0x10));
    }
    {   // 1D takes one coordinate register: R254 is the last one allowed (an extended register: the program gets
        // its register-map marker first, so the load is looked for), RZ (R255) is not
        const auto r = lower(insn(0xfe007b97, 0x00001000, 0x001e0100, 0x000f6200));
        CHECK(r);
        CHECK(std::find(r.instructions.begin(), r.instructions.end(), suld(0, 254, 1, 0, 0x10)) != r.instructions.end());
        CHECK(!lower(insn(0xff007b97, 0x00001000, 0x001e0100, 0x000f6200)));
    }
    // 1D_BUFFER and 1D_ARRAY (codes 1 and 2) are still refused
    CHECK(!lower(insn(0x00007b97, 0x20001000, 0x001e0100, 0x000f6200)));
    CHECK(!lower(insn(0x00007b97, 0x40001000, 0x001e0100, 0x000f6200)));
    std::printf("PASS: SULD.P on a 1D surface lowers to Maxwell SULD.P.1D\n");
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default=shutil.which("clang++") and "clang++" or "g++")
    a = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="lower-suld-1d-") as tmp:
        cpp = Path(tmp) / "fixture.cpp"
        exe = Path(tmp) / "fixture"
        cpp.write_text(FIXTURE, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-O1", "-Wno-everything" if "clang" in a.cxx else "-w",
                        "-I" + str(ROOT / "gpu" / "vk" / "eden"), "-I" + str(ROOT / "gpu" / "vk" / "compat"),
                        str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
