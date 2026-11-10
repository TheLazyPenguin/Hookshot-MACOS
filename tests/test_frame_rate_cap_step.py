"""A Frame rate cap above 60 steps the game by the frames' own time, so the game is not sped up.

The engine's rate is a whole number of display intervals, 60 at most, and it puts 60 back over a higher one: with only the
rate raised, every frame above 60 fps still stepped 1/60 s. nx2/oot_patches.py puts the host's measured frame time
(hos_frame_seconds_bits) at the engine's two step divides, and host/nn_vi.c realtime_step publishes it while the cap is above
60 and the hook is in the build. At a cap of 60 the bits stay 0 and the lifted code runs as shipped; a game version whose
code differs keeps its own code and the build goes on with a warning.

python -I -B tests/test_frame_rate_cap_step.py [--cc gcc]
"""
import argparse
import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cc", "gcc"]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nx2"))
import oot_patches  # noqa: E402

# (the shape of the two lifted functions: a float divide whose result goes to v8 in the frame's step and to v0 in the global one)
DIVIDE = ("    {uint64_t _a=0,_b=0,_z,_v;memcpy(&_a,c->vreg[1],4);memcpy(&_b,c->vreg[0],4);_z=(_a^_b)&0x80000000ULL;\n"
          "    (void)_z;\n" + oot_patches.STEP_OLD + "\n")
LIFTED = ('#include "a64.h"\n'
          "void f_80706be0(Ctx *__restrict A64_NOESC c) {\n" + DIVIDE % 8 + "}\n"
          "void f_80706f00(Ctx *__restrict A64_NOESC c) {\n" + DIVIDE % 3 + "}\n"
          "void f_83b6ea90(Ctx *__restrict A64_NOESC c) {\n" + DIVIDE % 0 + "}\n"
          "void f_83b6eb30(Ctx *__restrict A64_NOESC c) {\n}\n")


def block(source, marker):
    start = source.index(marker)
    return source[start:start + re.search(r"^}", source[start:], re.M).end()]


def check(cond, what):
    if not cond:
        raise SystemExit("FAIL: " + what)


FIXTURE = r'''#define _CRT_SECURE_NO_WARNINGS
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL:%d %s\n", __LINE__, #x); exit(1); } } while (0)
static uint8_t guest[0x4000];
#define GP(a) ((void *)(guest + (a)))
#define MOD 0x1000u
static void hos_log(const char *fmt, ...) { (void)fmt; }
int rx_option(int id, int otherwise) { (void)id; return otherwise; }
int hos_ini_option(const char *key, int otherwise) { (void)key; return otherwise; }
volatile uint64_t hos_gfx_module = MOD;
volatile int hos_fixed_resolution, hos_dynres_runs;
volatile uint32_t hos_fixed_scale_bits;
volatile float hos_text_scale;
volatile uint64_t hos_step_probe, hos_res_module;
volatile uint32_t hos_frame_seconds_bits;
@HOST@
static uint64_t a64_fpx_div32_div32(void *c, uint64_t a, uint64_t b) {
    float x, y; uint32_t w;
    (void)c; memcpy(&x, &a, 4); memcpy(&y, &b, 4); x /= y; memcpy(&w, &x, 4);
    return w;
}
/* (the lifted divide with the hook: base / nominal, or base * the frame's seconds) */
static float lifted_step(float base, float nominal) {
    void *c = 0; uint64_t _a = 0, _b = 0, _v; float r;
    memcpy(&_a, &base, 4); memcpy(&_b, &nominal, 4);
@HOOK@
    memcpy(&r, &_v, 4);
    return r;
}
static int64_t now = 1000000000LL;
static float frames(int n, double seconds) {   /* (n presents that far apart: the seconds the hook is given, 0 when off) */
    float f;
    uint32_t bits;
    for (int i = 0; i < n; i++) now += (int64_t)(seconds * 1e9), realtime_step(now);
    bits = hos_frame_seconds_bits;
    memcpy(&f, &bits, 4);
    return bits ? f : 0.0f;
}
static int near(float a, double b) { return a > b * 0.999 && a < b * 1.001; }
int main(int argc, char **argv) {
    int *limit = (int *)GP(MOD + 0xfc), *rate = (int *)GP(MOD + 0x2c8);
    const char *mode = argc > 1 ? argv[1] : "";
    *limit = 60, *rate = 60;
    hos_step_probe = strcmp(mode, "no hook") ? 0x2000 : 0;   /* (the lifted code sets it when the hook is in the build) */
    realtime_step(now);
    if (!strcmp(mode, "cap 120")) {
        CHECK(near(frames(10, 1.0 / 120), 1.0 / 120) && *rate == 60 && *limit == 120);   /* (the rate stays the engine's) */
        CHECK(near(lifted_step(60.0f, (float)*rate), 0.5) && near(lifted_step(30.0f, (float)*rate), 0.25));   /* (half a 60th a frame) */
        CHECK(near(frames(10, 1.0 / 40), 1.0 / 40) && near(lifted_step(60.0f, (float)*rate), 1.5));
        CHECK(near(frames(10, 1.0 / 1000), 1.0 / 240));   /* (the shortest step) */
        CHECK(near(frames(10, 0.2), 4.0 / 60));           /* (the longest, as the rate's 15) */
    } else if (!strcmp(mode, "cap 60")) {
        CHECK(frames(10, 1.0 / 120) == 0.0f && *rate == 60 && *limit == 60);
        CHECK(frames(10, 1.0 / 40) == 0.0f && *rate == 40 && lifted_step(60.0f, (float)*rate) == 1.5f);   /* (the game's own divide) */
    } else {   /* (HOS_FPS_STEP=0, or a lift without the hook: the rate up to the cap, as before) */
        CHECK(frames(10, 1.0 / 120) == 0.0f && *rate == 120 && *limit == 120);
        CHECK(lifted_step(60.0f, 60.0f) == 1.0f);
    }
    printf("PASS: %s\n", mode);
    return 0;
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cc", default="gcc")
    a = p.parse_args()

    out, n = oot_patches.patch_frame_seconds(LIFTED)
    check(n == 2 and out.count("hos_frame_seconds_bits; if (_hs)") == 2, "the hook is not at both step divides once")
    check(out.count("hos_step_probe = c->x[19];") == 1, "the frame's step does not tell the host the hook is there")
    check(out.startswith('#include "a64.h"\n' + oot_patches.STEP_DECL), "the lifted file does not declare the host's values")
    other = out[out.index("void f_80706f00"):out.index("void f_83b6ea90")]
    check("hos_" not in other, "a function between the two was patched")
    hook = oot_patches.STEP_HOOK.split("\n")[1] + "\n"
    back = out.replace(oot_patches.STEP_DECL, "", 1).replace("\n    hos_step_probe = c->x[19];", "").replace(hook, "")
    check(back == LIFTED, "more than the hook changed")
    check(oot_patches.unpatch_frame_seconds(out) == LIFTED, "taking the hook out does not give the lift's text back")
    altered = out.replace("a64_vset64(c->vreg[8],_v);}", "a64_vset64(c->vreg[9],_v);}")   # (a hook this version does not know)
    kept = oot_patches.unpatch_frame_seconds(altered)
    check(kept.count(oot_patches.STEP_MARK) == 1 and oot_patches.STEP_DECL in kept, "a hook left in the file lost its declarations")
    check(oot_patches.patch_frame_seconds(out) == (out, 0), "a second run changed a patched file")
    one, n1 = oot_patches.patch_frame_seconds(LIFTED[:LIFTED.index("void f_83b6ea90")])   # (the other site in another chunk)
    check(n1 == 1 and one.count("hos_frame_seconds_bits; if (_hs)") == 1, "one site in a file is not patched")
    twice = LIFTED.replace("}\nvoid f_83b6eb30", DIVIDE % 0 + "}\nvoid f_83b6eb30")   # (another game version: two divides)
    check(oot_patches.patch_frame_seconds(twice)[1] == 1 and "void f_83b6ea90" in twice, "a different function was patched")
    with tempfile.TemporaryDirectory(prefix="cap-step-") as tmp:
        missing = LIFTED.replace("f_80706be0", "f_80706be4")
        (Path(tmp) / "code_000.c").write_text(missing, encoding="utf-8", newline="")
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            oot_patches.apply(tmp)
        check("WARNING: the frame's time was found at 1 of 2 step divides, none patched" in log.getvalue(),
              "no warning for a missing divide")
        check((Path(tmp) / "code_000.c").read_text(encoding="utf-8") == missing, "one divide alone was left patched")
        # (the two divides in two files, as in the game: both made. Then one file lifted again with other code and a second run,
        # which must not leave the first file's hook on its own)
        two = LIFTED.index("void f_83b6ea90")
        files = [Path(tmp) / "code_000.c", Path(tmp) / "code_001.c"]
        files[0].write_text(LIFTED[:two], encoding="utf-8", newline="")
        files[1].write_text('#include "a64.h"\n' + LIFTED[two:], encoding="utf-8", newline="")
        with contextlib.redirect_stdout(io.StringIO()):
            oot_patches.apply(tmp)
        check([f.read_text(encoding="utf-8").count(oot_patches.STEP_MARK) for f in files] == [1, 1], "apply did not patch both divides")
        files[1].write_text('#include "a64.h"\n' + LIFTED[two:].replace("vreg[0],_v);}", "vreg[2],_v);}"), encoding="utf-8", newline="")
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            oot_patches.apply(tmp)
        check("none patched" in log.getvalue() and files[0].read_text(encoding="utf-8") == LIFTED[:two],
              "a second run left one divide's hook from the first")

    vi = (ROOT / "host" / "nn_vi.c").read_text(encoding="utf-8")
    host = "\n".join(block(vi, m) for m in ("static float text_scale(", "static int fps_max(void) {", "static void realtime_step("))
    fixture = FIXTURE.replace("@HOST@", host).replace("@HOOK@", "\n".join(oot_patches.STEP_HOOK.split("\n")[:2]))
    with tempfile.TemporaryDirectory(prefix="cap-step-") as tmp:
        c = Path(tmp) / "fixture.c"
        exe = Path(tmp) / "fixture.exe"
        c.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(c), "-o", str(exe)], check=True)
        for mode, cap, step in (("cap 120", "120", None), ("cap 60", None, None), ("step off", "120", "0"), ("no hook", "120", None)):
            env = {k: v for k, v in os.environ.items() if not k.startswith("HOS_")}
            if cap:
                env["HOS_FPS_MAX"] = cap
            if step:
                env["HOS_FPS_STEP"] = step
            subprocess.run([str(exe), mode], env=env, check=True)


if __name__ == "__main__":
    main()
