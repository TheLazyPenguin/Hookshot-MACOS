"""The native NVN layer keeps its host pointers in host tables, and checks guest ranges against the guest window.

Compiles the real functions from host/nvn_native.c and host/hos.h (the guest window range check, the command
buffers' slot table, the recording handle set) against a small guest window of test memory, with the real object
layouts of gpu/render/rx_nvn.h. Checks:

- a guest range is accepted only inside the window, including ranges that wrap around;
- a command buffer's recording buffer is found through its own slot only: a slot number another object owns, or one
  out of range, gets the object a new slot and never another object's buffer;
- Finalize gives the slot back, and Initialize again without Finalize reuses nothing of another object;
- a recording handle is live only while it is in the set (added, found, removed with others still found after the
  removal moved them);
- ReadTexels / WriteTexels' buffer extent covers every row and image the renderer walks, and huge strides that would
  wrap around give 0 (refused).

No game or GPU is involved.

python -I -B tests/test_nvn_host_tables.py [--cc gcc]
"""
import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cc", "gcc"]

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="clang")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("null_pool_fixture", ROOT / "tests/test_nvn_null_pool.py")
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    block = helpers.block
    nvn = (ROOT / "host/nvn_native.c").read_text(encoding="utf-8")
    hos = (ROOT / "host/hos.h").read_text(encoding="utf-8")
    start = nvn.index("typedef struct { uint64_t owner; uint8_t *seg, *cur, *end; } cmd_rec;")
    table_decls = nvn[start:nvn.index("static cmd_rec *cmd_slot(", start)]
    live_decls_start = nvn.index("static uint64_t *live_handles;")
    live_decls = nvn[live_decls_start:nvn.index("static void live_handle_add(", live_decls_start)]
    pieces = [
        block(hos, "static inline void *hos_guest_range("),
        block(nvn, "static void *gw("),
        block(nvn, "static const void *in_window("),
        table_decls,
        block(nvn, "static cmd_rec *cmd_slot("),
        block(nvn, "static cmd_rec *cmd_adopt("),
        block(nvn, "static cmd_rec *cmd_host("),
        "static volatile LONG64 seg_bytes, seg_count;",
        block(nvn, "static void cmd_release("),
        live_decls,
        block(nvn, "static void live_handle_add("),
        block(nvn, "static int live_handle_has("),
        block(nvn, "static void live_handle_remove("),
        block(nvn, "static uint64_t texels_extent("),
    ]
    fixture = r'''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <setjmp.h>
#include "rx_nvn.h"

#define WINDOW (1u << 20)
static uint8_t *A64_MEM;
#define GP(a) ((void *)(A64_MEM + (uint64_t)(a)))
#define HOS_SPACE_END ((uint64_t)WINDOW)
typedef int SRWLOCK;
typedef long LONG;
typedef long long LONG64;
#define SRWLOCK_INIT 0
static void AcquireSRWLockExclusive(SRWLOCK *l) { (void)l; }
static void ReleaseSRWLockExclusive(SRWLOCK *l) { (void)l; }
static LONG InterlockedIncrement(volatile LONG *v) { return ++*v; }
static LONG64 InterlockedAdd64(volatile LONG64 *v, LONG64 d) { return *v += d; }
static LONG64 InterlockedIncrement64(volatile LONG64 *v) { return ++*v; }
static LONG64 InterlockedDecrement64(volatile LONG64 *v) { return --*v; }
static void hos_log(const char *f, ...) { (void)f; }
static jmp_buf died;
static int dying;
static void die(const char *fmt, ...) { (void)fmt; if (dying) longjmp(died, 1); fprintf(stderr, "unexpected die\n"); exit(3); }
static uint64_t h2g(const void *p) { return p ? (uint64_t)((const uint8_t *)p - A64_MEM) : 0; }
#define POOL_MAX 26
static int pool_off(void) { return 0; }
static unsigned pool_class(size_t n) { (void)n; return 0; }
static int puts_count;
static void pool_put(void *b, unsigned c) { (void)c; free(b); puts_count++; }
''' + "\n".join(pieces) + r'''
static void require(int ok, const char *m) { if (!ok) { fprintf(stderr, "FAIL: %s\n", m); exit(1); } }
static int dies(void *(*f)(uint64_t, uint64_t), uint64_t a, uint64_t n) {
    dying = 1;
    if (setjmp(died)) { dying = 0; return 1; }
    f(a, n);
    dying = 0;
    return 0;
}
int main(void) {
    A64_MEM = calloc(1, WINDOW);
    require(A64_MEM != NULL, "test window");
    /* the guest window */
    require(hos_guest_range(0x1000, 16) == A64_MEM + 0x1000, "a range inside the window");
    require(hos_guest_range(WINDOW - 16, 16) != NULL, "a range ending at the window's end");
    require(hos_guest_range(WINDOW - 16, 17) == NULL, "a range past the window's end");
    require(hos_guest_range(WINDOW, 0) == NULL, "an address at the window's end");
    require(hos_guest_range(~0ull - 8, 16) == NULL, "a range that wraps around");
    require(hos_guest_range(0x1000, ~0ull) == NULL, "a size that wraps around");
    require(dies(gw, ~0ull - 0x100, 8), "gw accepted an address below the window");
    require(!dies(gw, 0x2000, 8), "gw refused a range inside the window");
    require(in_window(A64_MEM + 0x100, 8) == A64_MEM + 0x100, "in_window refused an object in the window");
    dying = 1;
    if (!setjmp(died)) { in_window(A64_MEM - 64, 8); require(0, "in_window accepted a pointer below the window"); }
    dying = 0;

    /* command buffers: a slot names its object */
    nvn_cmd *a = (nvn_cmd *)GP(0x4000), *b = (nvn_cmd *)GP(0x5000);
    cmd_rec *ra = cmd_adopt(a), *rb = cmd_adopt(b);
    require(ra != rb && a->slot && b->slot && a->slot != b->slot, "two command buffers share a slot");
    ra->seg = ra->cur = malloc(64), ra->end = ra->seg + 64;
    require(cmd_host(a) == ra, "a command buffer lost its own slot");
    const uint32_t a_slot = a->slot;
    b->slot = a_slot;   /* b's memory names a's slot */
    cmd_rec *forged = cmd_host(b);
    require(forged != ra && b->slot != a_slot && forged->seg == NULL, "a command buffer got another one's recording buffer");
    a->slot = 0x7fffffffu;   /* out of range */
    cmd_rec *fresh = cmd_host(a);
    require(fresh != ra && fresh->seg == NULL, "an out-of-range slot was used");
    a->slot = a_slot;
    require(cmd_host(a) == ra, "the object's own slot was not found again");
    puts_count = 0;
    cmd_release(a);
    require(puts_count == 1 && a->slot == 0 && ra->owner == 0, "Finalize did not give the slot and buffer back");
    b->slot = a_slot;   /* a freed slot is no one's */
    require(cmd_host(b) != NULL && cmd_host(b)->seg == NULL, "a freed slot's buffer was used");

    /* recording handles */
    uint64_t h[5000];
    for (int i = 0; i < 5000; i++) { h[i] = 0x7f0000000000ull + (uint64_t)i * 0x40; live_handle_add(h[i]); }
    for (int i = 0; i < 5000; i++) require(live_handle_has(h[i]), "a live handle was not found");
    require(!live_handle_has(0x7f0000000008ull) && !live_handle_has(0) && !live_handle_has(0x1234),
            "a handle that was never made counts as live");
    for (int i = 0; i < 5000; i += 3) live_handle_remove(h[i]);
    for (int i = 0; i < 5000; i++) require(live_handle_has(h[i]) == (i % 3 != 0), "removing handles lost others");
    require(nlive == 5000 - 1667, "the live count");
    /* ReadTexels / WriteTexels: the buffer span the strides reach */
    require(texels_extent(64, 4, 1, 64, 256) == 256, "a packed 64x4 region");
    require(texels_extent(64, 4, 2, 128, 1024) == 1024 + 3 * 128 + 64, "strided rows and images");
    require(texels_extent(0, 4, 1, 0, 0) == 1 && texels_extent(64, 0, 1, 64, 0) == 1, "an empty region");
    require(texels_extent(64, 4, 1, 1ull << 63, 0) == 0, "a row stride that wraps around");
    require(texels_extent(64, 1, 3, 64, 1ull << 63) == 0, "an image stride that wraps around");
    require(!hos_guest_range(0x1000, texels_extent(64, 2, 1, WINDOW, 0)), "a row stride past the window was accepted");
    puts("PASS: guest window ranges, command buffer slots by owner, live recording handles, texel buffer extents");
    return 0;
}
'''
    cc = shutil.which(args.cc)
    if not cc:
        raise SystemExit("test_nvn_host_tables: no C compiler %r (pass --cc)" % args.cc)
    with tempfile.TemporaryDirectory(prefix="nvn-host-tables-") as temporary:
        path = Path(temporary)
        authored = path / "fixture.c"
        executable = path / "fixture.exe"
        authored.write_text(fixture, encoding="utf-8")
        subprocess.run([cc, "-std=gnu11", "-O1", "-fno-strict-aliasing", "-I", str(ROOT / "gpu/render"), str(authored),
                        "-o", str(executable)], check=True)
        result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
        print(result.stdout, end="")
        if result.returncode:
            print(result.stderr, end="")
            raise SystemExit("test_nvn_host_tables: failed (exit %d)" % result.returncode)


if __name__ == "__main__":
    main()
