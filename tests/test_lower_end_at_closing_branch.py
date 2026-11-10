"""The Ampere -> Maxwell lowering ends a program at its closing self-branch after an unconditional jump back.

One of OoT's compute programs is a loop that leaves only by predicated EXITs (@P0 EXIT): it ends with the loop's
unconditional BRA back and NVIDIA's closing BRA to itself, and has no unconditional EXIT, so it was refused as "native
program has no unconditional EXIT". The self-branch was taken as the end only after a jump table. Now also when the
instruction before it is an unconditional BRA or EXIT, which nothing falls through from; a self-branch that can be
fallen into is still no end.
python -I -B tests/test_lower_end_at_closing_branch.py [--cxx clang++]
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
static Shader::Ampere::LoweredProgram lower_all(std::vector<Instruction> code) { return Shader::Ampere::LowerToMaxwell(code); }
// BRA from instruction `at` to instruction `to` (unconditional)
static Instruction bra(int at, int to) {
    const uint64_t rel = static_cast<uint64_t>(static_cast<int64_t>(to) * 16 - (static_cast<int64_t>(at) * 16 + 16));
    return insn(0x00007947, static_cast<uint32_t>(rel), 0x03800000 | static_cast<uint32_t>((rel >> 32) & 0x3ffff), 0x000fea00);
}
static const Instruction exit_p0 = insn(0x0000094d, 0, 0x03800000, 0x000fea00);   // @P0 EXIT
static const Instruction nop = insn(0x00007918, 0, 0, 0x000fc000);
int main() {
    {   // loop: @P0 EXIT; BRA 0; BRA self (and padding)
        const auto r = lower_all({exit_p0, bra(1, 0), bra(2, 2), nop, nop});
        CHECK(r);
        CHECK(r.source_size == 3 * 16);
    }
    CHECK(!lower_all({exit_p0, nop, bra(2, 2), nop}));          // the self-branch can be fallen into: no end
    CHECK(lower_all({exit_p0, exit_insn, bra(2, 2)}));            // EXIT first: ends at the EXIT, as before
    std::printf("PASS: a loop that leaves by predicated EXITs ends at its closing self-branch\n");
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default=shutil.which("clang++") and "clang++" or "g++")
    a = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="lower-end-branch-") as tmp:
        cpp = Path(tmp) / "fixture.cpp"
        exe = Path(tmp) / "fixture"
        cpp.write_text(FIXTURE, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-O1", "-Wno-everything" if "clang" in a.cxx else "-w",
                        "-I" + str(ROOT / "gpu" / "vk" / "eden"), "-I" + str(ROOT / "gpu" / "vk" / "compat"),
                        str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
