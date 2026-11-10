"""Compile the actual NVN buffer-map functions against authored memory only.

ca58d6c gives a pool-less buffer writable scratch instead of address zero. The
memory-pool accessor fixture does not call nvnBufferMap. Here newly allocated
scratch must be zeroed and large enough, repeated maps retain their contents,
and ordinary pooled mappings and null inputs keep their separate behavior.

--source accepts the released a598 version as a negative control: it compiles,
then fails the first pool-less mapping invariant. No game or GPU is involved.
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
    parser.add_argument("--source", type=Path, default=ROOT / "host/nvn_native.c")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("null_pool_fixture", ROOT / "tests/test_nvn_null_pool.py")
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    source = args.source.read_text(encoding="utf-8")
    try:
        scratch = helpers.block(source, "static uint64_t scratch_map(")
    except ValueError:
        scratch = ""  # The released negative has no helper; its real map body still compiles.
    mapping = helpers.block(source, "NV(nvnBufferMap)")
    fixture = r'''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { uint64_t x[32]; } Ctx;
typedef struct {
    uint32_t magic, flags;
    uint64_t mem;
    uint64_t size, gpu;
    uint64_t reserved;
} nvn_pool;
typedef struct { uint32_t magic; nvn_pool *pool; int64_t off; uint64_t size; } nvn_buffer;
#define GP(a) ((void *)(uintptr_t)(a))
#define P(i) ((void *)(c->x[i] ? GP(c->x[i]) : NULL))
#define RET(v) (c->x[0] = (uint64_t)(v))
#define RETP(p) RET((uint64_t)(uintptr_t)(p))
#define POOL(p) ((const nvn_pool *)(p))
#define NV(name) static void n_##name(Ctx *c, void *u_)

/* Single-threaded fixture: the host lock and allocator are stand-ins, not tested implementations. */
typedef int SRWLOCK;
#define SRWLOCK_INIT 0
static void AcquireSRWLockExclusive(SRWLOCK *lock) { (void)lock; }
static void ReleaseSRWLockExclusive(SRWLOCK *lock) { (void)lock; }
static void hos_log(const char *format, ...) { (void)format; }
static void *allocations[4];
static unsigned allocation_count;
static uint64_t allocation_size;
static uint64_t hos_sys_alloc(uint64_t size, uint64_t alignment) {
    (void)alignment;
    if (!size || size > 1024 * 1024 || allocation_count == 4) exit(2);
    void *p = calloc(1, (size_t)size);
    if (!p) exit(2);
    allocations[allocation_count++] = p;
    allocation_size = size;
    return (uint64_t)(uintptr_t)p;
}
''' + scratch + "\n" + mapping + r'''
static void require(int ok, const char *message) {
    if (!ok) { fprintf(stderr, "FAIL: %s\n", message); exit(1); }
}
static uint8_t *map(nvn_buffer *buffer) {
    Ctx c = {0};
    c.x[0] = (uint64_t)(uintptr_t)buffer;
    c.x[30] = 0x1234;
    n_nvnBufferMap(&c, NULL);
    return (uint8_t *)(uintptr_t)c.x[0];
}
static uint8_t *fresh_scratch(nvn_buffer *buffer, uint64_t required) {
    uint8_t *p = map(buffer);
    require(p != NULL, "pool-less buffer map returned zero");
    require(allocation_count && p == allocations[allocation_count - 1] && allocation_size >= required,
            "pool-less buffer map did not provide the required storage");
    for (uint64_t i = 0; i < required; i++) require(p[i] == 0, "new scratch was not zeroed");
    p[0] = 0x2a;
    p[required - 1] = 0x7d;
    require(p[0] == 0x2a && p[required - 1] == 0x7d, "scratch endpoints were not writable");
    return p;
}
int main(int argc, char **argv) {
    (void)argv;
    nvn_buffer buffer = {0};
    if (argc > 1) {
        fresh_scratch(&buffer, 0x1000);  /* Fresh process: size zero must bootstrap a usable map. */
        puts("PASS: a zero-size pool-less buffer gets writable initial scratch");
    } else {
        buffer.size = 0x3d0;
        uint8_t *first = fresh_scratch(&buffer, buffer.size);
        require(map(&buffer) == first && first[0] == 0x2a && first[buffer.size - 1] == 0x7d,
                "mapping the same buffer discarded its pointer or contents");
        buffer.size = 0x20001;
        fresh_scratch(&buffer, buffer.size);
        require(first[0] == 0x2a && first[0x3cf] == 0x7d, "growing scratch invalidated the earlier map");
        unsigned before = allocation_count;
        uint8_t memory[32] = {0};
        nvn_pool pool = {0};
        pool.mem = (uint64_t)(uintptr_t)memory;
        buffer.pool = &pool;
        buffer.off = 7;
        buffer.size = 8;
        require(map(&buffer) == memory + 7, "a pooled map changed its pointer or offset");
        pool.mem = 0;
        require(map(&buffer) == NULL, "a pool without CPU memory must remain unmapped");
        require(map(NULL) == NULL, "a null buffer object must remain unmapped");
        require(allocation_count == before, "pooled or null inputs allocated scratch");
        puts("PASS: pool-less scratch size, contents and lifetime; pooled identity and null inputs");
    }
    for (unsigned i = 0; i < allocation_count; i++) free(allocations[i]);
    return 0;
}
'''
    cc = shutil.which(args.cc)
    if not cc:
        raise SystemExit("test_nvn_buffer_map: no C compiler %r (pass --cc)" % args.cc)
    with tempfile.TemporaryDirectory(prefix="nvn-buffer-map-") as temporary:
        path = Path(temporary)
        authored = path / "fixture.c"
        executable = path / "fixture.exe"
        authored.write_text(fixture, encoding="utf-8")
        subprocess.run([cc, "-std=c11", "-O2", "-fno-strict-aliasing", str(authored), "-o", str(executable)], check=True)
        for mode in ([], ["zero-size"]):
            result = subprocess.run([str(executable), *mode], capture_output=True, text=True, timeout=10)
            print(result.stdout, end="")
            if result.returncode:
                print(result.stderr, end="")
                raise SystemExit("test_nvn_buffer_map: actual mapping contract failed (exit %d)" % result.returncode)


if __name__ == "__main__":
    main()
