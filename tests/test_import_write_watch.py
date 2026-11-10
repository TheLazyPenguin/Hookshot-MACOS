"""Pool commits keep Windows CPU write watches armed; ordinary imports keep the fast path.

Compiles the real commit block and uses a tiny reservation, a read-only page and
a vectored handler. No Vulkan or game data. Other platforms skip the Windows test.
python -I -B tests/test_import_write_watch.py [--cxx g++]
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]
WATCHES = {"RX_NVN_WATCH_TEX": "64x64", "RX_NVN_WATCH_TEXELS_SRC": "64x64",
           "RX_VK_WATCH_CPU": "0:1000", "RX_VK_VERIFY_DIM": "64x64"}

CPP = r"""
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
static int queries, allocations, forced, faults, bad;
static bool fail_full;
static uint8_t* base;
static SIZE_T page;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); bad++; } } while (0)
static LPVOID tracked_alloc(LPVOID p, SIZE_T n, DWORD type, DWORD protect) {
    allocations++;
    if (fail_full && p == base && n == page * 2 && type == MEM_COMMIT) {
        fail_full = false; forced++; SetLastError(ERROR_NOT_ENOUGH_MEMORY); return nullptr;
    }
    return VirtualAlloc(p, n, type, protect);
}
static SIZE_T tracked_query(LPCVOID p, PMEMORY_BASIC_INFORMATION info, SIZE_T n) {
    queries++; return VirtualQuery(p, info, n);
}
#define VirtualAlloc tracked_alloc
#define VirtualQuery tracked_query
static void commit(uint8_t* ptr, uint64_t bytes) {
COMMIT
}
#undef VirtualAlloc
#undef VirtualQuery
static LONG CALLBACK writer(EXCEPTION_POINTERS* e) {
    const auto* r = e->ExceptionRecord;
    if (r->ExceptionCode != EXCEPTION_ACCESS_VIOLATION || r->ExceptionInformation[0] != 1) return EXCEPTION_CONTINUE_SEARCH;
    const auto a = (uintptr_t)r->ExceptionInformation[1];
    if (a < (uintptr_t)base || a >= (uintptr_t)base + page) return EXCEPTION_CONTINUE_SEARCH;
    DWORD old;
    if (!VirtualProtect(base, page, PAGE_READWRITE, &old)) return EXCEPTION_CONTINUE_SEARCH;
    faults++; return EXCEPTION_CONTINUE_EXECUTION;
}
int main(int argc, char** argv) {
    const bool watch = argc > 1 && !strcmp(argv[1], "watch");
    const bool fallback = argc > 1 && !strcmp(argv[1], "fallback");
    SYSTEM_INFO si{}; GetSystemInfo(&si); page = si.dwPageSize;
    base = (uint8_t*)VirtualAlloc(nullptr, page * 4, MEM_RESERVE, PAGE_NOACCESS);
    if (!base) return 2;
    if (VirtualAlloc(base, page, MEM_COMMIT, PAGE_READWRITE) != base) { VirtualFree(base, 0, MEM_RELEASE); return 2; }
    memset(base, 0x5a, page);
    DWORD old;
    if (watch && !VirtualProtect(base, page, PAGE_READONLY, &old)) { VirtualFree(base, 0, MEM_RELEASE); return 2; }
    fail_full = fallback;
    commit(base, page * 2);
    MEMORY_BASIC_INFORMATION a{}, b{}, outside{};
    CHECK(VirtualQuery(base, &a, sizeof a) == sizeof a);
    CHECK(VirtualQuery(base + page, &b, sizeof b) == sizeof b);
    CHECK(VirtualQuery(base + page * 2, &outside, sizeof outside) == sizeof outside);
    CHECK(a.State == MEM_COMMIT && b.State == MEM_COMMIT && outside.State == MEM_RESERVE);
    for (SIZE_T i = 0; i < page; i++) if (base[i] != 0x5a) { CHECK(false); break; }
    if (watch) {
        CHECK(a.Protect == PAGE_READONLY);
        CHECK(queries > 0 && forced == 0);
        void* handler = AddVectoredExceptionHandler(1, writer);
        CHECK(handler != nullptr);
        if (handler) {
            *(volatile uint8_t*)base = 0x6b;
            CHECK(faults == 1 && base[0] == 0x6b);
            RemoveVectoredExceptionHandler(handler);
        }
    } else {
        CHECK(a.Protect == PAGE_READWRITE);
        CHECK(fallback ? queries > 0 && forced == 1 : queries == 0 && allocations == 1);
    }
    printf("queries=%d allocations=%d forced=%d faults=%d failures=%d\n", queries, allocations, forced, faults, bad);
    VirtualFree(base, 0, MEM_RELEASE);
    return bad ? 1 : 0;
}
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cxx", default="g++")
    ap.add_argument("--source", type=Path, default=ROOT / "gpu/vk/vk_memory.cpp")
    args = ap.parse_args()
    if os.name != "nt":
        print("SKIP: requires real Windows memory protection and exception handling")
        return
    source = args.source.read_text(encoding="utf-8")
    start = source.index("    // (pages the game has not touched yet may be only reserved:")
    commit = source[start:source.index("#ifdef __linux__", start)]
    with tempfile.TemporaryDirectory(prefix="import-write-watch-") as tmp:
        tmp = Path(tmp)
        cpp, exe = tmp / "test.cpp", tmp / "test.exe"
        cpp.write_text(CPP.replace("COMMIT\n}", commit + "\n}"), encoding="utf-8")
        subprocess.run([args.cxx, "-std=c++20", "-O1", "-w", str(cpp), "-o", str(exe)], check=True, timeout=120)
        clean = {k: v for k, v in os.environ.items() if k not in WATCHES}
        cases = [("default", [], clean), ("fallback", ["fallback"], clean)]
        cases += [(key, ["watch"], clean | {key: value}) for key, value in WATCHES.items()]
        failed = []
        for name, argv, env in cases:
            result = subprocess.run([str(exe), *argv], env=env, capture_output=True, text=True, timeout=10)
            print(name + ":", result.stdout.strip(), result.stderr.strip())
            if result.returncode:
                failed.append(name)
        if failed:
            raise SystemExit("FAIL: " + ", ".join(failed))
    print("PASS: four write watches survive import; default avoids queries; commit failure uses the old walk")


if __name__ == "__main__":
    main()
