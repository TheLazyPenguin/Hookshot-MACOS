"""The Ampere -> Maxwell lowering takes TLD.MS, a multisampled texture's texel (native op 0xb66, bit 78).

Three of OoT's fragment programs stopped at it as "native texel fetch mode or descriptor binding": the lowering refused
every bit from 76 up but the offsets one. 2D at level zero is Maxwell TLDS 2D.LZ.MS (encoding 6: x, y in Ra, Ra+1, the
sample index in Rb), which the Maxwell frontend already reads as an ImageFetch with a sample, and the texture pass then
declares the image multisampled. Other dimensions, a level, offsets with it, an odd Ra and RZ as the sample stay refused.
python -I -B tests/test_lower_tld_ms.py [--cxx clang++]
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
// Maxwell TLDS Rd, Ra, Rb (second destination, descriptor offset, .NODEP, swizzle, encoding), as the lowering makes it
static uint64_t tlds(uint32_t d, uint32_t a, uint32_t b, uint32_t d2, uint32_t offset, uint32_t swizzle, uint32_t encoding) {
    return 0xda00000000000000ULL | (7ULL << 16) | d | (uint64_t{a} << 8) | (uint64_t{b} << 20) | (uint64_t{d2} << 28) |
           (uint64_t{offset} << 36) | (1ULL << 49) | (uint64_t{swizzle} << 50) | (uint64_t{encoding} << 53);
}
static bool has(const Shader::Ampere::LoweredProgram& r, uint64_t want) {
    return std::find(r.instructions.begin(), r.instructions.end(), want) != r.instructions.end();
}
int main() {
    // TLD.SCR.LZ.MS 2D, RGB into Rd, Rd+1 and the second destination, the descriptor at 0x8 of buffer 2 (the log's three)
    struct Case { uint32_t w0, w1, w2; uint32_t d, a, b, d2; } cases[] = {
        {0x00087b66, 0x30800809, 0x049e4704, 8, 0, 9, 4},
        {0x040a7b66, 0x30800809, 0x049e4709, 10, 4, 9, 9},
        {0x10127b66, 0x30800813, 0x049e4716, 18, 16, 19, 22},
    };
    for (const Case& c : cases) {
        const auto r = lower(insn(c.w0, c.w1, c.w2, 0x001fc200));
        CHECK(r);
        CHECK(has(r, tlds(c.d, c.a, c.b, c.d2, 0x8, 0, 6)));
        CHECK(r.required_texture_buffer == 2);
    }
    const uint32_t w0 = 0x00087b66, w1 = 0x30800809, w2 = 0x049e4704, w3 = 0x001fc200;
    // without bit 78: the plain 2D.LZ fetch, encoding 2, as before
    CHECK(has(lower(insn(w0, w1, w2 & ~(1u << 14), w3)), tlds(8, 0, 9, 4, 0x8, 0, 2)));
    CHECK(!lower(insn(w0, w1 & ~(7u << 29), w2, w3)));                      // 1D
    CHECK(!lower(insn(0x01087b66, w1, w2, w3)));                            // x, y not an aligned pair
    CHECK(!lower(insn(w0, w1, (w2 & ~(7u << 23)) | (3u << 23), w3)));     // .LL: a level
    CHECK(!lower(insn(w0, w1, w2 | (1u << 12), w3)));                       // offsets with it
    CHECK(!lower(insn(w0, (w1 & ~0xffu) | 0xff, w2, w3)));                  // RZ as the sample
    CHECK(!lower(insn(w0, w1, w2 | (1u << 13), w3)));                       // bit 77: still refused
    std::printf("PASS: TLD.MS 2D at level zero lowers to Maxwell TLDS 2D.LZ.MS\n");
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default=shutil.which("clang++") and "clang++" or "g++")
    a = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="lower-tld-ms-") as tmp:
        cpp = Path(tmp) / "fixture.cpp"
        exe = Path(tmp) / "fixture"
        cpp.write_text(FIXTURE, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-O1", "-Wno-everything" if "clang" in a.cxx else "-w",
                        "-I" + str(ROOT / "gpu" / "vk" / "eden"), "-I" + str(ROOT / "gpu" / "vk" / "compat"),
                        str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
