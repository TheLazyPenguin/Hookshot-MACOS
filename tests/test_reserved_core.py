"""The core hos_reserved_cpus keeps for the replay (host/hos_thread.c pick_reserved_core): the last core of the fastest kind.

On a CPU of one kind every core has the same EfficiencyClass and the last core is kept, as before; on Intel's hybrid CPUs
the efficiency cores come last and have the lower class, so the last performance core is kept instead. None is kept with
fewer than 8 logical processors, nor on a CPU of more than one kind with fewer than 4 cores of the fastest kind.

python -I -B tests/test_reserved_core.py [--cxx clang++]
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "g++"]

ROOT = Path(__file__).resolve().parents[1]


def block(text, marker):
    start = text.index(marker)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--source', type=Path, default=ROOT / 'host/hos_thread.c')
    args = parser.parse_args()
    helper = block(args.source.read_text(encoding='utf-8'), 'static uint64_t pick_reserved_core(')
    helper += chr(10) + block(args.source.read_text(encoding='utf-8'), 'static uint64_t pick_cache_cores(')
    fixture = r'''
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>
#define CHECK(ok) do { if (!(ok)) { std::fprintf(stderr, "failed line %d\n", __LINE__); std::exit(1); } } while (0)
''' + helper + r'''
struct Core { uint64_t mask; unsigned char cls; };
uint64_t pick(const std::vector<Core>& cores) {
    std::vector<uint64_t> masks;
    std::vector<unsigned char> classes;
    for (const Core& c : cores) masks.push_back(c.mask), classes.push_back(c.cls);
    return pick_reserved_core(masks.data(), classes.data(), (int)cores.size());
}
// n cores of `per` logical processors each from logical processor `first`, all of class cls
void add(std::vector<Core>& v, int n, int per, int first, unsigned char cls) {
    for (int i = 0; i < n; i++) v.push_back({((1ull << per) - 1) << (first + i * per), cls});
}
struct L3 { uint64_t mask, size; int per = 1; };   // (per: logical processors a core, 2 with SMT)
uint64_t cache(const std::vector<L3>& l3) {
    std::vector<uint64_t> masks, sizes, cores;
    for (const L3& c : l3) {
        masks.push_back(c.mask), sizes.push_back(c.size);
        for (int bit = 0; bit < 64; bit += c.per)   // (its cores: runs of `per` logical processors of its mask)
            if (c.mask >> bit & 1) cores.push_back(((1ull << c.per) - 1) << bit);
    }
    return pick_cache_cores(masks.data(), sizes.data(), (int)l3.size(), cores.data(), (int)cores.size());
}
int main() {
    {   // the cores that share the largest L3, when the CPU's L3s differ
        const uint64_t MB = 1 << 20;
        CHECK(cache({{0xFF, 96 * MB}, {0xFF00, 32 * MB}}) == 0xFF);                    // Ryzen 9 9950X3D, SMT off: 8 cores
        CHECK(cache({{0xFFFF, 96 * MB, 2}, {0xFFFF0000, 32 * MB, 2}}) == 0xFFFF);      // 9950X3D / 7950X3D with SMT: 8 cores
        CHECK(cache({{0xFFFF0000, 96 * MB, 2}, {0xFFFF, 32 * MB, 2}}) == 0xFFFF0000);  // (the cache on the second CCD)
        CHECK(cache({{0xFFF, 96 * MB, 2}, {0xFFF000, 32 * MB, 2}}) == 0);              // 7900X3D with SMT: 6 cores are too few
        CHECK(cache({{0x3F, 96 * MB}, {0xFC0, 32 * MB}}) == 0);                        // 7900X3D, SMT off: the same 6
        // a hybrid CPU's two kinds of core are not an X3D's two CCDs: their L3s are not shared by as many logical processors
        CHECK(cache({{0xFF, 16 * MB, 2}, {0xFFFF00, 8 * MB, 2}}) == 0);                // Ryzen AI 9 HX 370: 4 Zen 5 + 8 Zen 5c, SMT
        CHECK(cache({{0xF, 16 * MB}, {0xFF0, 8 * MB}}) == 0);                          // (the same with SMT off)
        CHECK(cache({{0xFF, 16 * MB, 2}, {0xFF00, 8 * MB}}) == 0);                     // (shared by as many, but 4 cores on the largest)
        CHECK(cache({{0xFFFF, 32 * MB, 2}, {0xFFFF0000, 32 * MB, 2}}) == 0);     // Ryzen 9 7950X: both CCDs alike
        CHECK(cache({{0xFFFF, 96 * MB, 2}}) == 0);                               // 9800X3D: one L3 for all
        CHECK(cache({{0xFFFFFF, 30 * MB}}) == 0);                                // Intel hybrid: one L3 for all
        CHECK(cache({}) == 0);
        CHECK(cache({{0xFF, 96 * MB}, {0xFF00, 96 * MB}, {0xFF0000, 32 * MB}}) == 0xFFFF);   // (two of the largest: both)
        {   // (the cores could not be read: none)
            const uint64_t masks[2] = {0xFF, 0xFF00}, sizes[2] = {96 * MB, 32 * MB};
            CHECK(pick_cache_cores(masks, sizes, 2, nullptr, 0) == 0);
        }
    }
    std::vector<Core> v;
    add(v, 12, 2, 0, 0);   // Ryzen 9 3900X: 12 cores with SMT, one kind
    CHECK(pick(v) == 0xC00000);
    v.clear();
    add(v, 6, 2, 0, 0);    // Ryzen 5 7600X
    CHECK(pick(v) == 0xC00);
    v.clear();
    add(v, 8, 1, 0, 0);    // 8 cores without SMT
    CHECK(pick(v) == 0x80);
    v.clear();
    add(v, 4, 2, 0, 0);    // 4 cores with SMT: 8 logical processors, one kind
    CHECK(pick(v) == 0xC0);
    v.clear();
    add(v, 6, 1, 0, 0);    // 6 cores without SMT: fewer than 8 logical processors, none kept
    CHECK(pick(v) == 0);
    v.clear();
    add(v, 8, 2, 0, 1);    // i7-12700K: 8 performance cores with HT (0-15), then 4 efficiency cores (16-19)
    add(v, 4, 1, 16, 0);
    CHECK(pick(v) == 0xC000);
    v.clear();
    add(v, 8, 2, 0, 1);    // i9-13900K: 8 performance cores with HT (0-15), then 16 efficiency cores (16-31)
    add(v, 16, 1, 16, 0);
    CHECK(pick(v) == 0xC000);
    v.clear();
    add(v, 4, 1, 0, 0);    // efficiency cores listed first, then performance cores: still the last fast one
    add(v, 4, 2, 4, 1);
    CHECK(pick(v) == 0xC00);
    v.clear();
    add(v, 4, 1, 0, 1);    // Lunar Lake: 4 performance cores, 4 efficiency cores, no HT: one of the 4 kept
    add(v, 4, 1, 4, 0);
    CHECK(pick(v) == 0x8);
    v.clear();
    add(v, 2, 2, 0, 1);    // i5-1235U: 2 performance cores with HT, 8 efficiency cores: neither of the 2 kept
    add(v, 8, 1, 4, 0);
    CHECK(pick(v) == 0);
    v.clear();
    add(v, 2, 2, 0, 1);    // i3-1215U: 2 performance cores with HT, 4 efficiency cores (8 logical): none kept
    add(v, 4, 1, 4, 0);
    CHECK(pick(v) == 0);
    v.clear();
    add(v, 3, 2, 0, 1);    // 3 fast cores of more than one kind: none kept
    add(v, 8, 1, 6, 0);
    CHECK(pick(v) == 0);
    CHECK(pick({}) == 0);
    v.clear();
    add(v, 8, 2, 0, 0);
    v.push_back({0, 1});   // (an empty mask is no core, of whatever class)
    CHECK(pick(v) == 0xC000);
    std::puts("PASS: the last core of the fastest kind with 4+ of them, the last core on CPUs of one kind, none under 8 "
              "logical processors");
}
'''
    with tempfile.TemporaryDirectory(prefix='reserved-core-') as tmp:
        cpp = Path(tmp) / 'fixture.cpp'
        exe = Path(tmp) / 'fixture.exe'
        cpp.write_text(fixture, encoding='utf-8')
        subprocess.run([args.cxx, '-std=c++20', '-Wall', '-Wextra', '-Werror', str(cpp), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    main()
