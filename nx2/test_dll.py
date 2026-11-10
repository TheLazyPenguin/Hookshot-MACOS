"""The production build against Unicorn: random functions run from work/build/hookshot_game.dll itself.

test_leaf.py compiles the functions it picks into its own harness. This test picks the same way (self-contained
functions, or with --calls whole call trees) and checks them in the real game library instead: built by
nx2/build.py from the full lift, every chunk at -O1 with the loop-header polls on, reached only through the DLL's
emulator ABI (nx2/rt/mkw_host.h: mkw_recomp_attach, mkw_recomp_lookup), the way Eglantine's ArmRecomp uses it.

The host program maps the image and the scratch area at the DLL's guest window (MkwGameInfo::mem_base), attaches a
host whose poll counts and whose trap raises an exception the case loop catches, sets every case's poll flag (so the
first loop header of each function calls the host), and writes the same results as test_leaf's harness.

Usage:  python -I nx2/test_dll.py [--count 2000] [--states 3] [--seed 7] [--calls]   (after build.py --dll)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # (python -I leaves the script folder off)
import kit
import test_leaf
import toolchain

# (the game: this runs the lifted code of a real dump against Unicorn)
RUN_ALL_SKIP = {
    "linux": "needs a full game build (work/build/hookshot_game.dll) and Unicorn",
    "windows": "needs a full game build (work/build/hookshot_game.dll) and Unicorn",
}

DLL = os.path.join(kit.WORK, "build", "hookshot_game.dll")

HOST = r"""
#include "a64.h"
#include "mkw_host.h"
#include <stdio.h>
#include <stdlib.h>
#include <windows.h>
static const uint64_t roots[] = {%(roots)s};
#define IMG_BASE %(img_base)dULL
#define IMG_SIZE %(img_size)dULL
#define SCR_BASE %(scratch_base)dULL
#define SCR_SIZE %(scratch)dULL
static const uint64_t regions[][2] = {%(regions)s};
#define NREG (sizeof regions / sizeof regions[0])
static uint8_t *p_img, *p_scr;
static uint64_t polls, traps;
static void h_svc(void *u, struct GuestContext *c, uint32_t imm) { (void)u; ((Ctx *)c)->halted = 11; RaiseException(0xE0000002, 0, 0, NULL); }
static void h_poll(void *u, struct GuestContext *c) { (void)u; (void)c; polls++; }
static void h_trap(void *u, struct GuestContext *c, uint64_t pc, uint32_t insn, const char *why) {
    (void)u; (void)pc; (void)insn; (void)why; ((Ctx *)c)->halted = 9; traps++; RaiseException(0xE0000001, 0, 0, NULL);
}
static int h_miss(void *u, struct GuestContext *c, uint64_t t) { (void)u; (void)c; (void)t; return 0; }
static uint64_t h_cntpct(void *u) { (void)u; return 0; }
static uint8_t *pristine(uint64_t a) { return a >= SCR_BASE ? p_scr + (a - SCR_BASE) : p_img + (a - IMG_BASE); }
static uint64_t page_hash(const uint8_t *p) {
    const uint64_t *w = (const uint64_t *)p; uint64_t a = 0, b = 0;
    for (uint64_t i = 0; i < 512; i++) { a += w[i] * (2 * i + 1); b += w[i] ^ (i * 0x9E3779B97F4A7C15ULL); }
    return a ^ b;
}
static void make_scratch(uint64_t seed, uint64_t *out) {
    for (uint64_t i = 0; i < SCR_SIZE / 8; i++) {
        uint64_t z = seed + (i + 1) * 0x9E3779B97F4A7C15ULL;
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL; z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL; z ^= z >> 31;
        out[i] = (z & 3) == 0 ? ((SCR_BASE + (z >> 12) %% (SCR_SIZE - 256)) & ~7ULL) : z;
    }
}
static int run(MkwFn f, Ctx *c) {
    __try { f((struct GuestContext *)c); } __except (EXCEPTION_EXECUTE_HANDLER) {
        DWORD code = GetExceptionCode(); return code == 0xE0000001 || code == 0xE0000002 ? 0 : (int)code; }
    return 0;
}
int main(int argc, char **argv) {
    HMODULE dll = LoadLibraryA(argv[4]);
    if (!dll) { fprintf(stderr, "cannot load %%s\n", argv[4]); return 6; }
    PFN_mkw_recomp_attach attach = (PFN_mkw_recomp_attach)GetProcAddress(dll, "mkw_recomp_attach");
    PFN_mkw_recomp_lookup lookup = (PFN_mkw_recomp_lookup)GetProcAddress(dll, "mkw_recomp_lookup");
    MkwHost host = {MKW_HOST_VERSION, sizeof(MkwGuestContext), NULL, h_svc, h_poll, h_trap, h_miss, h_cntpct};
    MkwGameInfo info;
    if (!attach || !lookup || attach(&host, &info)) { fprintf(stderr, "attach failed\n"); return 7; }
    fprintf(stderr, "dll: %%u functions, image %%#llx, guest window %%#llx, polls %%u, main %%s\n", info.functions,
            (unsigned long long)info.image_base, (unsigned long long)info.mem_base, info.polls, info.main_build_id);
    if (info.mem_base != (uint64_t)(uintptr_t)A64_MEM || info.image_base != IMG_BASE) return 8;
    FILE *img = fopen(argv[1], "rb"), *in = fopen(argv[2], "rb"), *out = fopen(argv[3], "wb");
    if (VirtualAlloc(A64_PTR(IMG_BASE), IMG_SIZE, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE) != A64_PTR(IMG_BASE)) return 3;
    if (VirtualAlloc(A64_PTR(SCR_BASE), SCR_SIZE, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE) != A64_PTR(SCR_BASE)) return 4;
    if (fread(A64_PTR(IMG_BASE), 1, IMG_SIZE, img) != IMG_SIZE) return 5;
    p_img = malloc(IMG_SIZE); p_scr = malloc(SCR_SIZE);
    memcpy(p_img, A64_PTR(IMG_BASE), IMG_SIZE);
    static uint8_t state[%(state)d];
    unsigned idx; uint64_t seed;
    while (fread(&idx, 4, 1, in) == 1 && fread(&seed, 8, 1, in) == 1 && fread(state, sizeof state, 1, in) == 1) {
        make_scratch(seed, (uint64_t *)p_scr);
        memcpy(A64_PTR(SCR_BASE), p_scr, SCR_SIZE);
        Ctx c; memset(&c, 0, sizeof c);
        memcpy(c.x, state, 256); memcpy(&c.n, state + 256, 4);
        memcpy(&c.fpcr, state + 264, 8); memcpy(&c.fpsr, state + 272, 8); memcpy(c.vreg, state + 280, 512);
        memcpy(&c.tpidr_el0, state + 792, 8); memcpy(&c.tpidrro_el0, state + 800, 8);
        c.poll = 1;
        MkwFn f = lookup(roots[idx]);
        int fault = f ? run(f, &c) : -1;
        memcpy(state, c.x, 256); memcpy(state + 256, &c.n, 4);
        memcpy(state + 264, &c.fpcr, 8); memcpy(state + 272, &c.fpsr, 8); memcpy(state + 280, c.vreg, 512);
        fwrite(&c.halted, 4, 1, out); fwrite(&fault, 4, 1, out); fwrite(state, sizeof state, 1, out);
        uint32_t ndiff = 0; static uint64_t diff[2 * 8192];
        for (size_t r = 0; r < NREG; r++)
            for (uint64_t a = regions[r][0]; a < regions[r][1]; a += 4096)
                if (memcmp(A64_PTR(a), pristine(a), 4096)) {
                    if (ndiff < 8192) { diff[2 * ndiff] = a; diff[2 * ndiff + 1] = page_hash(A64_PTR(a)); }
                    ndiff++;
                    memcpy(A64_PTR(a), pristine(a), 4096);
                }
        fwrite(&ndiff, 4, 1, out); fwrite(diff, 16, ndiff < 8192 ? ndiff : 8192, out);
    }
    fclose(out);
    fprintf(stderr, "host: polls %%llu, traps %%llu\n", (unsigned long long)polls, (unsigned long long)traps);
    return 0;
}
"""


def build_host(tmp, P, roots, funcs, meta, img_size, addr64):
    """(replaces test_leaf.build) a host program for the DLL instead of a harness with the functions compiled in"""
    rt64 = os.path.join(kit.WORK, "build", "rt64")
    gen = os.path.join(kit.WORK, "gen")
    src = HOST % {
        "roots": ",".join("%#xULL" % e for _, e, _ in roots),
        "regions": ",".join("{%#xULL,%#xULL}" % r for r in test_leaf.writable_regions(meta)),
        "scratch": test_leaf.SCRATCH_SIZE, "scratch_base": test_leaf.SCRATCH, "img_base": meta["base"],
        "img_size": img_size, "state": test_leaf.STATE.size}
    path = os.path.join(tmp, "host.c")
    open(path, "w", newline="\n").write(src)
    exe = os.path.join(tmp, "host.exe")
    cmd = [toolchain.need(toolchain.find("clang"))] + toolchain.native_target() + toolchain.native_link() + \
          ["-O1", "-g0", "-mcx16", "-Wno-everything", "-I" + rt64, "-I" + gen, "-I" + os.path.join(kit.HERE, "rt"),
           path, "-o", exe]
    subprocess.run(cmd, check=True)
    # the host takes the DLL as its fourth argument: wrap it
    bat = os.path.join(tmp, "host.bat")
    open(bat, "w").write('@"%s" %%1 %%2 %%3 "%s"\n' % (exe, DLL))
    return bat


def main():
    if not os.path.exists(DLL):
        raise SystemExit("no %s: run nx2/build.py --dll first" % DLL)
    if "--seed" not in sys.argv:
        sys.argv += ["--seed", "7"]   # (other functions than test_leaf's default)
    test_leaf.build = build_host
    test_leaf.Picker.emit_only = True
    return test_leaf.main()


if __name__ == "__main__":
    sys.exit(main())
