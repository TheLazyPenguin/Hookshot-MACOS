"""FrameLog samples use the host clock, preserving sequence/kind and record layout."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]
WITNESS = "PASS: three capture samples use the host clock; metadata preserved"
FIXTURE = r'''
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL: %s\n", #x); return 1; } } while (0)
static int64_t host_ns;
static uint64_t profiler_ns;
static unsigned host_reads, profiler_reads;
int64_t now_ns() { ++host_reads; return host_ns; }
uint64_t prof_now() { ++profiler_reads; return profiler_ns; }
struct Host { int64_t (*now_ns)(); } host_object{now_ns};
Host* host = &host_object;
struct LogSlot { bool used = false; uint64_t at = 0; uint32_t seq = 0, kind = 0; };
int main() {
    LogSlot l;
    uint32_t seq = 0;
    std::atomic<uint32_t> present_kind{0};
    for (unsigned i = 0; i < 3; ++i) {
        host_ns = 1000000000000LL + i * 16666667LL;
        profiler_ns = 9000000000000000ULL + i * 16660000ULL; // Deliberately different epoch and rate.
        present_kind.store(i & 1);
        l.used = false;
        @@SAMPLE@@
        CHECK(l.used && l.at == (uint64_t)host_ns);
        CHECK(l.seq == i && l.kind == (i & 1));
    }
    CHECK(seq == 3 && host_reads == 3 && profiler_reads == 0);
    std::puts("PASS: three capture samples use the host clock; metadata preserved");
}
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cxx', default='g++')
    ap.add_argument('--source', type=Path, default=ROOT)
    args = ap.parse_args()
    text = (args.source / 'gpu/vk/vk_replay.cpp').read_text(encoding='utf-8')
    start = text.find('if (src && framelog_on()) {')
    if start < 0:
        raise SystemExit('FAIL: FrameLog capture block not found: if (src && framelog_on())')
    capture = re.sub(r'/\*.*?\*/|//[^\n]*', '', text[start:], flags=re.S)
    pos, depth = capture.index('{') + 1, 1
    while pos < len(capture) and depth:
        depth += (capture[pos] == '{') - (capture[pos] == '}')
        pos += 1
    if depth:
        raise SystemExit('FAIL: unclosed FrameLog capture block')
    samples = re.findall(r'(?m)^\s*l\.used = true, l\.at = [^;]+;', capture[:pos])
    if len(samples) != 1:
        raise SystemExit('FAIL: expected one FrameLog metadata sample (l.used = true, l.at = ...)')
    with tempfile.TemporaryDirectory(prefix='framelog-clock-') as tmp:
        src, exe = Path(tmp) / 'fixture.cpp', Path(tmp) / 'fixture.exe'
        src.write_text(FIXTURE.replace('@@SAMPLE@@', samples[0]), encoding='utf-8')
        result = subprocess.run([args.cxx, '-std=c++17', '-O1', str(src), '-o', str(exe)],
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise SystemExit(result.stdout + result.stderr)
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
        if result.returncode or result.stdout.strip() != WITNESS:
            raise SystemExit('FAIL: capture clock fixture\n' + result.stdout + result.stderr)
    print(WITNESS)


if __name__ == '__main__':
    main()
