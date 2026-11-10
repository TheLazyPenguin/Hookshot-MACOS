"""The seed's compute programs answer the storage buffer pass's pointer question from their control section (issue 940).

With the pass's port on (EDEN_NX2_GM_LEGACY=0) an access is bound to a constant buffer pointer only when that pointer is mapped
(Env::IsCbufStorageBufferPointer). The prepare translates the seed's compute programs with nothing bound: every answer was no,
every access was left to the run-time search, and play used those programs under their keys; in Kokiri Forest one hung the GPU
(Xid 109). For those programs the answer is now the layout's: the address word of each uniform and storage buffer table entry
of c0, nothing else. This builds vk_bank.cpp's CsLayout, cs_layout_of and seed_cs_buffer_word as they are in the source and
checks them on a made-up control section, and checks that IsCbufStorageBufferPointer asks it before reading c0.
python -I -B tests/test_seed_cs_pointers.py [--cxx g++]
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "g++"]

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "gpu" / "vk" / "vk_bank.cpp"
SHADER = ROOT / "gpu" / "vk" / "vk_shader.cpp"


def block(text, marker, end="}"):
    start = text.index(marker)
    at = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[at] == "{") - (text[at] == "}")
        at += 1
    return text[start:at] + (";" if end == "};" else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cxx", default="g++")
    a = ap.parse_args()
    bank = BANK.read_text(encoding="utf-8")
    parts = [block(bank, "struct CsLayout {", "};"), block(bank, "CsLayout cs_layout_of("), block(bank, "bool seed_cs_buffer_word(")]
    cpp = r"""
#include <algorithm>
#include <cstdint>
#include <cstdio>
thread_local const uint8_t* seed_cs_control = nullptr;
""" + "\n".join(parts) + r"""
int fails = 0;
void want(uint32_t offset, bool expected) {
    if (seed_cs_buffer_word(offset) != expected) std::printf("c0+%#x: %d, wanted %d\n", offset, !expected, expected), fails++;
}
int main() {
    uint8_t control[0xd8]{};
    control[0xa9] = 5;   // (push constants: 5 words, the area rounded to 32 bytes: tables from 0x30)
    control[0xb1] = 2, control[0xb2] = 3, control[0xb3] = 4, control[0xb6] = 1;
    want(0x30, false);   // (nothing given: not the seed's)
    seed_cs_control = control;
    for (uint32_t o : {0x30u, 0x40u, 0x50u, 0x60u, 0x70u}) want(o, true);   // (2 uniform buffers at 0x30, 3 storage buffers at 0x50)
    for (uint32_t o : {0x0u, 0x8u, 0x10u, 0x18u, 0x20u, 0x28u}) want(o, false);   // (the workgroup counts and the push area)
    for (uint32_t o : {0x34u, 0x38u, 0x58u, 0x78u}) want(o, false);   // (an entry's high word and size)
    for (uint32_t o : {0x80u, 0x88u, 0x90u, 0xa0u, 0x880u}) want(o, false);   // (texture handles, past the layout, the pointer table)
    control[0xb1] = 0, control[0xb2] = 20, control[0xa9] = 0;   // (more slots than the 16 the back end binds)
    want(0x10, true), want(0x100, true), want(0x110, false);
    if (fails) return 1;
    std::puts("ok");
}
"""
    with tempfile.TemporaryDirectory(prefix="seed-cs-ptr-") as tmp:
        src, exe = Path(tmp) / "fixture.cpp", Path(tmp) / "fixture"
        src.write_text(cpp, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-Wall", str(src), "-o", str(exe)], check=True)
        got = subprocess.run([str(exe)], capture_output=True, text=True)
        if got.returncode or got.stdout.strip() != "ok":
            raise SystemExit("seed_cs_buffer_word:\n" + got.stdout + got.stderr)
    shader = SHADER.read_text(encoding="utf-8")
    ask = block(shader, "bool IsCbufStorageBufferPointer(u32 index, u32 offset) override {")
    seed = ask.find("seed_cs_buffer_word(offset)")
    read = ask.find("ReadCbufValue(")
    if seed < 0 or read < 0 or seed > read or "seed_cs_control" not in ask[:seed]:
        raise SystemExit("IsCbufStorageBufferPointer does not answer the seed's compute programs from their layout before reading c0")
    print("PASS: the seed's compute programs take c0's buffer table entries for pointers, and nothing else")


if __name__ == "__main__":
    main()
