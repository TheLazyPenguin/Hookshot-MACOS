"""Aligned uniform buffers must not evict every cached handle read."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]


def block(text, marker):
    start = text.index(marker)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    source = (ROOT / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    cache = source[source.index("struct UbWord {"):source.index("// (a range an update does overlap:")]
    fixture = r'''
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr,"FAIL:%d %s\n",__LINE__,#x); std::exit(1); } } while(0)
uint64_t rec_value_now = 1;
uint32_t stamp = 1;
size_t ub_limit = SIZE_MAX;
struct UbUpdate { uint64_t dst; std::vector<uint8_t> bytes; };
std::vector<UbUpdate> ub_updates;
uint32_t memory_page_stamp(uint64_t) { return stamp; }
bool ub_gap_holds(uint64_t addr, uint64_t n, size_t first, size_t lim) {
    for (size_t i = first; i < lim; i++) {
        const auto& u = ub_updates[i];
        if (u.dst < addr + n && addr < u.dst + u.bytes.size()) return false;
    }
    return true;
}
bool ub_try_gap(size_t first, size_t lim, uint64_t addr, uint64_t n) {
    return ub_gap_holds(addr, n, first, lim);
}
uint64_t reads = 0;
bool fail_read = false;
bool memory_read_as_submitted(uint64_t addr, void* dst, uint64_t n) {
    reads++;
    if (fail_read) return false;
    auto* bytes = static_cast<uint8_t*>(dst);
    for (uint64_t i = 0; i < n; i++) bytes[i] = (uint8_t)((addr + i) >> 9);
    return true;
}
'''
    fixture += cache + "\n" + block(source, "bool ub_read(")
    fixture += r'''
int main() {
    const uint64_t a = 0x100000040ull, b = a + 512;
    const bool legacy = std::getenv("RX_VK_UB_WORD_HASH") && !std::atoi(std::getenv("RX_VK_UB_WORD_HASH"));
    uint32_t v = 0;
    for (int i = 0; i < 1000; i++) {
        const uint64_t addr = i % 2 ? b : a;
        CHECK(ub_read(addr, &v, 4));
        CHECK(v == (i % 2 ? 0x01010101u : 0));
    }
    CHECK(reads == (legacy ? 1000 : 2));
    // The same handle offset in adjacent pages must not all share one slot either.
    rec_value_now++; reads = 0;
    for (int i = 0; i < 1000; i++) {
        const uint64_t addr = i % 2 ? a + 4096 : a;
        CHECK(ub_read(addr, &v, 4));
        CHECK(v == (i % 2 ? 0x08080808u : 0));
    }
    CHECK(reads == (legacy ? 1000 : 2));
    // Adjacent words across this boundary collided under the XOR mix, even though the old index kept them apart.
    rec_value_now++; reads = 0;
    for (int i = 0; i < 1000; i++) {
        const uint64_t addr = i % 2 ? 0x8000 : 0x7ffc;
        CHECK(ub_read(addr, &v, 4));
        CHECK(v == (i % 2 ? 0x40404040u : 0x3f3f3f3fu));
    }
    std::printf("adjacent boundary words: %llu backing reads for 1000 reads\n", (unsigned long long)reads);
    CHECK(reads == 2);
    // The index uses only word bits 0..20: check the complete period and its wraparound. A repeated slot less than
    // 64 words apart would evict within a contiguous 256-byte window. The additive mix's closest repeat is 126.
    std::array<int64_t, 128> last;
    last.fill(-1);
    uint64_t closest = UINT64_MAX;
    for (uint64_t word = 0; word < (1ull << 21) + 128; word++) {
        const uint32_t slot = ub_word_index(word * 4);
        CHECK(slot < last.size());
        if (last[slot] >= 0) closest = std::min(closest, word - (uint64_t)last[slot]);
        last[slot] = (int64_t)word;
    }
    CHECK(closest == (legacy ? 128 : 126));
    std::printf("closest repeating slot: %llu words apart\n", (unsigned long long)closest);
    // Repeated actual reads of a contiguous window crossing the boundary must retain all 64 words.
    rec_value_now++; reads = 0;
    for (int pass = 0; pass < 2; pass++) {
        for (uint64_t word = 0; word < 64; word++) {
            const uint64_t addr = 0x7f80 + word * 4;
            CHECK(ub_read(addr, &v, 4));
            CHECK(v == (uint32_t)((addr >> 9) & 255) * 0x01010101u);
        }
    }
    CHECK(reads == 64);
    // Slot collisions never substitute another address's value.
    uint64_t collision = a + 4;
    while (ub_word_index(collision) != ub_word_index(a)) collision += 4;
    CHECK(ub_read(collision, &v, 4));
    CHECK(ub_read(a, &v, 4)); CHECK(v == 0);
    // A new recording and a changed page stamp both force a fresh read.
    auto before = reads;
    rec_value_now++;
    CHECK(ub_read(a, &v, 4)); CHECK(reads == before + 1);
    before = reads; stamp++;
    CHECK(ub_read(a, &v, 4)); CHECK(reads == before + 1);
    // Inline updates still override a previously cached word.
    ub_updates.push_back({a, {0x12, 0x34, 0x56, 0x78}});
    CHECK(ub_read(a, &v, 4)); CHECK(v == 0x78563412u);
    // A failed backing read does not return a cached word through the update.
    fail_read = true;
    CHECK(!ub_read(a, &v, 4));
    std::puts(legacy ? "PASS: legacy index reproduces aligned-buffer thrashing" :
                      "PASS: aligned handles stay cached; collisions, recordings, stamps and updates remain correct");
}
'''
    with tempfile.TemporaryDirectory(prefix="ub-word-index-") as tmp:
        cpp = Path(tmp) / "fixture.cpp"
        exe = Path(tmp) / "fixture"
        cpp.write_text(fixture, encoding="utf-8")
        subprocess.run([args.cxx, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror", "-D_CRT_SECURE_NO_WARNINGS", str(cpp), "-o", str(exe)], check=True)
        for value in ("1", "0"):
            env = dict(os.environ, RX_VK_UB_WORD_HASH=value)
            subprocess.run([str(exe)], check=True, env=env)


if __name__ == "__main__":
    main()
