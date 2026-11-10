"""The Ampere -> Maxwell lowering takes ISBERD.O, a task or mesh program reading back its own output region (op 0x923).

One of OoT's task programs stopped at it as "native stage buffer access mode": reads were taken from the input region
only. It is kept as the nx2 stage-buffer pseudo instruction with .O (bit 47), which the frontend reads as IsbeReadOutput
(the word IsbeWriteAttribute writes there: a task's payload, a mesh's attributes). Writes are still always to the output
region, and reads still only from the attribute region (not the map).
python -I -B tests/test_lower_isberd_output.py [--cxx clang++]
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
// the nx2 stage-buffer pseudo instruction: dest 0-7, Ra 8-15, offset 20-43, .32 44, .ATTR 45, .SKEW 46, .O 47, write 48
static uint64_t isbe(uint32_t reg, uint32_t a, uint32_t offset, bool is32, bool attr, bool output, bool write) {
    return 0xefc0000000000000ULL | (7ULL << 16) | reg | (uint64_t{a} << 8) | (uint64_t{offset} << 20) |
           (uint64_t{is32} << 44) | (uint64_t{attr} << 45) | (uint64_t{output} << 47) | (uint64_t{write} << 48);
}
int main() {
    {   // ISBERD.32.ATTR.O R5, [RZ+0x10]: the task program's read of its payload (from the log)
        const auto r = lower(insn(0xff057923, 0x00001000, 0x0000b800, 0x000e2200));
        CHECK(r);
        CHECK(r.instructions.size() >= 1 && r.instructions[0] == isbe(5, 255, 0x10, true, true, true, false));
    }
    {   // without .O: the input region, as before
        const auto r = lower(insn(0xff057923, 0x00001000, 0x00003800, 0x000e2200));
        CHECK(r);
        CHECK(r.instructions.size() >= 1 && r.instructions[0] == isbe(5, 255, 0x10, true, true, false, false));
    }
    CHECK(!lower(insn(0xff057923, 0x00001000, 0x00008800, 0x000e2200)));   // .O but the map region: still refused
    CHECK(!lower(insn(0xff007927, 0x00001005, 0x00003800, 0x000e2200)));   // ISBEWR without .O: still refused
    CHECK(lower(insn(0xff007927, 0x00001005, 0x0000b800, 0x000e2200)));    // ISBEWR.O: as before
    std::printf("PASS: ISBERD.O reads back the output region\n");
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default=shutil.which("clang++") and "clang++" or "g++")
    a = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="lower-isberd-o-") as tmp:
        cpp = Path(tmp) / "fixture.cpp"
        exe = Path(tmp) / "fixture"
        cpp.write_text(FIXTURE, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-O1", "-Wno-everything" if "clang" in a.cxx else "-w",
                        "-I" + str(ROOT / "gpu" / "vk" / "eden"), "-I" + str(ROOT / "gpu" / "vk" / "compat"),
                        str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
