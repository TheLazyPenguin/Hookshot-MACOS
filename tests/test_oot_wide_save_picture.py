"""Compile nx2/oot_wide.py's save-picture patch (issue 952) around authored registers.

The pause menu draws the whole picture into the save's 543 x 306 JPEG through the game's viewport helper. Past 16:9 the
patch widens that one SetViewport, centred, so the middle 16:9 of the picture fills the texture; narrower than 16:9 (4:3,
16:10) it makes it taller, centred, so the picture's middle band fills the texture at its own shape; every other
viewport, and a 16:9 window, stay as the game set them. No game or image is used: the site's C is taken from the module as the
lifter would place it.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

RUN_ALL_ARGS = ["--cc", "gcc"]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nx2"))
import oot_wide  # noqa: E402

FIXTURE = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct { uint64_t x[32]; } Ctx;
volatile float hos_wide_ratio;
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL:%d %s\n", __LINE__, #x); exit(1); } } while (0)
static void site(Ctx *c) {
SITE_C
}
static Ctx viewport(uint32_t x, uint32_t y, uint32_t w, uint32_t h) {
    Ctx c;
    memset(&c, 0, sizeof c);
    c.x[1] = x, c.x[2] = y, c.x[3] = w, c.x[4] = h, c.x[8] = 0x1234;
    site(&c);
    CHECK(c.x[8] == 0x1234);   /* (the call's address, loaded just before) */
    return c;
}
static void same(uint32_t x, uint32_t y, uint32_t w, uint32_t h) {
    const Ctx c = viewport(x, y, w, h);
    CHECK(c.x[1] == x && c.x[2] == y && c.x[3] == w && c.x[4] == h);
}
/* the texture's columns 0..543 show the picture's middle 16:9: the viewport centred, the picture's ratio over 16:9 wide */
static void middle(double ratio) {
    hos_wide_ratio = (float)ratio;
    const Ctx c = viewport(0, 0, 543, 306);
    CHECK(c.x[1] >> 32 == 0 && c.x[3] >> 32 == 0);   /* (w registers) */
    const int x = (int32_t)(uint32_t)c.x[1], w = (int)c.x[3];
    CHECK(c.x[2] == 0 && c.x[4] == 306);
    const double want_w = 543.0 * ratio / (16.0 / 9.0);
    CHECK(w > 543 && w - want_w < 1.0 && want_w - w < 1.0);
    CHECK(x < 0 && x + w > 543);
    const int left = -x, right = x + w - 543;
    CHECK(left - right <= 1 && right - left <= 1);
    const double margin = (1.0 - (16.0 / 9.0) / ratio) / 2.0, seen = (double)left / w;
    CHECK(seen - margin < 0.002 && margin - seen < 0.002);
}
/* narrower than 16:9: rows 0..306 show the picture's middle band, the viewport centred, 16:9 over the ratio tall */
static void band(double ratio) {
    hos_wide_ratio = (float)ratio;
    const Ctx c = viewport(0, 0, 543, 306);
    CHECK(c.x[2] >> 32 == 0 && c.x[4] >> 32 == 0);   /* (w registers) */
    const int y = (int32_t)(uint32_t)c.x[2], h = (int)c.x[4];
    CHECK(c.x[1] == 0 && c.x[3] == 543);
    const double want_h = 306.0 * (16.0 / 9.0) / ratio;
    CHECK(h > 306 && h - want_h < 1.0 && want_h - h < 1.0);
    CHECK(y < 0 && y + h > 306);
    const int top = -y, bottom = y + h - 306;
    CHECK(top - bottom <= 1 && bottom - top <= 1);
    const double shape = 543.0 / h;   /* (the picture's own ratio, as the texture shows it) */
    CHECK(shape - ratio * (543.0 / 306.0) / (16.0 / 9.0) < 0.01 && ratio * (543.0 / 306.0) / (16.0 / 9.0) - shape < 0.01);
}
int main(void) {
    hos_wide_ratio = 0;   /* a 16:9 window: the game's own */
    same(0, 0, 543, 306);
    middle(3440.0 / 1440.0);
    middle(5120.0 / 1440.0);
    middle(2560.0 / 1080.0);
    band(1920.0 / 1440.0);   /* 4:3 */
    band(2304.0 / 1440.0);   /* 16:10 */
    band(1800.0 / 1440.0);   /* 5:4 */
    hos_wide_ratio = (float)(1920.0 / 1440.0);   /* every other viewport as the game set it, narrower too */
    same(0, 0, 1920, 1440);
    same(0, 0, 543, 305);
    hos_wide_ratio = (float)(3440.0 / 1440.0);
    same(0, 0, 3440, 1440);
    same(0, 0, 2584, 1080);
    same(0, 0, 256, 256);
    same(0, 0, 543, 305);
    same(0, 0, 542, 306);
    same(1, 0, 543, 306);
    same(0, 1, 543, 306);
    puts("PASS: oot_wide's save-picture viewport: the middle 16:9 past 16:9, the middle band below it, the game's own otherwise");
    return 0;
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="gcc")
    args = parser.parse_args()
    sites = [s for s in oot_wide.SITES if s[2] is oot_wide.THUMB]
    assert sites == [(0x284824, 0xf9400108, oot_wide.THUMB)], sites
    flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 0
    with tempfile.TemporaryDirectory(prefix="oot-wide-save-picture-") as temporary:
        folder = Path(temporary)
        source = folder / "fixture.c"
        source.write_text(FIXTURE.replace("SITE_C", oot_wide.THUMB), encoding="utf-8")
        executable = folder / "fixture.exe"
        for command in ([args.cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(executable)],
                        [str(executable)]):
            result = subprocess.run(command, creationflags=flags, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=30)
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
            if result.returncode:
                raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
