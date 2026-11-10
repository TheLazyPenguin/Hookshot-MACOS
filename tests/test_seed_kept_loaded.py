"""The seed's prepare counts a program read in already as kept.

prepare_run's seed pass leaves out each program the program cache keeps: seed_translate by its key, seed_compute by its key's
variants. Both looked only at disk_records, and program_cache_load and program_cache_load_some take a key's records out of it as
they read them in. With RX_VK_PREPARE_BACKGROUND=1, the start of an update that the cache and notes already fit (the one after a
background prepare that did not finish) reads in, before the game, every noted program and every kept compute program
(precompile_run); the prepare behind the game then translated all of those again and kept each a second time. Both now also ask
loaded_variants, the variants of the key in memory. This builds loaded_variants as it is in the source, with a stand-in Program,
and checks it counts only ready programs that did not fail; and that seed_translate and seed_compute ask it.
python -I -B tests/test_seed_kept_loaded.py [--cxx g++]
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "g++"]

ROOT = Path(__file__).resolve().parents[1]
SHADER = ROOT / "gpu" / "vk" / "vk_shader.cpp"


def block(text, marker):
    start = text.index(marker)
    at = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[at] == "{") - (text[at] == "}")
        at += 1
    return text[start:at]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cxx", default="g++")
    a = ap.parse_args()
    src = SHADER.read_text(encoding="utf-8")
    cpp = r"""
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <mutex>
#include <unordered_map>
#include <unordered_set>
#include <vector>
struct Program {
    std::atomic<bool> ready{false};
    bool failed = false;
    uint64_t variant = 0;
};
std::mutex shader_mu;
std::unordered_map<uint64_t, std::vector<std::unique_ptr<Program>>> programs;
""" + block(src, "size_t loaded_variants(") + r"""
int main() {
    int fails = 0;
    auto add = [](uint64_t key, uint64_t variant, bool ready, bool failed) {
        auto p = std::make_unique<Program>();
        p->variant = variant, p->ready = ready, p->failed = failed;
        programs[key].push_back(std::move(p));
    };
    add(7, 0x11, true, false), add(7, 0x22, true, false), add(7, 0x33, false, false), add(7, 0x44, true, true);
    std::unordered_set<uint64_t> v;
    if (loaded_variants(7, &v) != 2 || v != std::unordered_set<uint64_t>{0x11, 0x22}) std::puts("key 7: wanted its two ready variants"), fails++;
    if (loaded_variants(8, nullptr) != 0 || programs.count(8)) std::puts("key 8: wanted none, and no entry made"), fails++;
    if (fails) return 1;
    std::puts("ok");
}
"""
    with tempfile.TemporaryDirectory(prefix="seed-kept-") as tmp:
        c, exe = Path(tmp) / "fixture.cpp", Path(tmp) / "fixture"
        c.write_text(cpp, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-Wall", str(c), "-o", str(exe)], check=True)
        got = subprocess.run([str(exe)], capture_output=True, text=True)
        if got.returncode or got.stdout.strip() != "ok":
            raise SystemExit("loaded_variants:\n" + got.stdout + got.stderr)
    translate = block(src, "std::unique_ptr<Program> seed_translate(const SeedStage* const by_stage[8], const uint32_t attributes[16], "
                      "const uint8_t color_types[8],\n                                        uint64_t* key_out) {")
    if "loaded_variants(key, nullptr)" not in translate:
        raise SystemExit("seed_translate does not count a program read in already as kept")
    compute = block(src, "SeedVariants seed_compute(")
    if "loaded_variants(cs->key, &variants)" not in compute or compute.index("loaded_variants(") > compute.index("const size_t had"):
        raise SystemExit("seed_compute does not count the variants read in already as kept")
    print("PASS: the seed's prepare leaves out programs read in already, as it does those listed on disk")


if __name__ == "__main__":
    main()
