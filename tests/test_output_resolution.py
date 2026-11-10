"""Exercise the host and menu's docked output sizes without a game dump: output_res as a size, the numbers saved before, a size
of the player's own, and what the menu saves."""
import argparse
import os
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()

    host = (ROOT / "host/nn_applet.c").read_text(encoding="utf-8")
    menu = (ROOT / "gpu/vk/vk_menu.cpp").read_text(encoding="utf-8")
    fixture = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iterator>

using DWORD = unsigned long;
constexpr int MAX_PATH = 260;
DWORD hos_game_path_a(char *path, int size) { return snprintf(path, size, "./hookshot.exe"); }
void hos_log(const char *, ...) {}
volatile uint64_t hos_wide_out = 0;   // (host/hos_main.c: the widescreen picture, 0 = none; nn_applet.c reads it)
struct { int handheld, output_res; } opts;
namespace mkwvk {
int up_now = 0;   // (the Upscaler shown: 0 the game's own, 1 DLSS, 2 DLAA)
int upscaler() { return up_now; }
}
#include "gpu/vk/upscaler_rows.h"
using namespace mkwvk;
namespace ur = upscaler_rows;
''' + host[host.index("int hos_ini_option(const char *key, int otherwise);"):host.index("HLE(_ZN2nn2oe16GetOperationModeEv)")] + menu[
        menu.index("struct Out {"):menu.index("/// The Render resolution: the value chosen")] + menu[
        menu.index("const char* tx_output_res("):menu.index("const char* tx_speed(")] + r'''
int main(int argc, char **argv) {
    assert(argc == 7);
    const int mode = atoi(argv[1]), pool = atoi(argv[5]);   // (mode: the menu's choice, 5 the player's own size)
    const unsigned w = atoi(argv[2]), h = atoi(argv[3]);
    assert(output_mode() == (mode != 0));
    assert(hos_output_size(0) == w && hos_output_size(1) == h);
    assert(hos_rt_pool_size(305ull << 20) == ((uint64_t)pool << 20));   // (512 MB at least, 900 MB at most above 4K: nn_applet.c)
    // (the menu reads the same text: the ini's, or HOS_OUTPUT_RES over it)
    const char* e = getenv("HOS_OUTPUT_RES");
    char text[80] = "";
    if (!e && !ini_text("output_res", text, sizeof text)) strcpy(text, "0");
    opts.handheld = handheld();
    opts.output_res = opts.handheld ? 0 : parse_output(e ? e : text);
    if (!opts.handheld) assert(opts.output_res == mode);
    assert(kLastOutput == 6 && kCustomOutput == 6);
    assert(output_choice(-1) == 0 && output_choice(5) == 5 && output_choice(7) == 0);
    assert(output_choice(6) == (custom_output.w ? 6 : 0));
    // (smallest to largest, by width then height: 1920x1080, 2048x1152, 2560x1440, 3840x2160, 5120x1440, the player's own in its
    // place; each step goes to the next, and stops at the ends)
    int order[8], n = 0;
    for (int id : {3, 0, 1, 2, 4, 5}) {
        if (custom_output.w && n == (int)std::count_if(std::begin(kOutputs), std::end(kOutputs), [&](const Out& p) {
                return p.w < custom_output.w || (p.w == custom_output.w && p.h < custom_output.h); }))
            order[n++] = 6;
        order[n++] = id;
    }
    if (custom_output.w && n == 6) order[n++] = 6;
    assert(n == (custom_output.w ? 7 : 6));
    for (int i = 0; i < n; i++) {
        assert(step_output_choice(order[i], -1) == order[i ? i - 1 : 0]);
        assert(step_output_choice(order[i], 1) == order[i + 1 < n ? i + 1 : i]);
    }
    if (!custom_output.w) assert(step_output_choice(2, 1) == 4 && step_output_choice(4, 1) == 5 && step_output_choice(5, 1) == 5);   // (4K, 5120x1440, 5K)
    assert(strcmp(tx_output_res(opts.output_res), argv[4]) == 0);
    // (what the menu saves: the size, which both sides read back as the same choice)
    const Out o = output_at(opts.output_res);
    char saved[32];
    snprintf(saved, sizeof saved, "%ux%u", o.w, o.h);
    assert(strcmp(saved, argv[6]) == 0);
    uint32_t sw = 0, sh = 0;
    assert(hos_output_parse(saved, &sw, &sh) == (opts.output_res != 0));
    if (opts.output_res) assert(sw == o.w && sh == o.h);
    assert(parse_output(saved) == opts.output_res);
    unsigned scene_w, scene_h;
    game_size(1.0f, scene_w, scene_h);
    assert(scene_w == (opts.handheld ? 1536 : mode ? w : 2048));
    assert(scene_h == (opts.handheld ? 864 : mode ? h : 1152));
    if (mode == 3) assert(strcmp(tx_resolution(2), "75% (1440x810)") == 0);
    if (mode == 3) {   // (DLSS at 1080p: its modes' render sizes, each a twelfth of the output, exact; DLAA the full size)
        up_now = ur::DLSS;
        assert(strcmp(tx_resolution(3), "Quality (67%)") == 0 && strcmp(tx_resolution(6), "Ultra Performance (33%)") == 0);
        const unsigned want[][3] = {{3, 1280, 720}, {5, 1120, 630}, {4, 960, 540}, {6, 640, 360}};
        for (const auto& m : want) {
            game_size(ur::percent(m[0]) / 100.0f, scene_w, scene_h);
            assert(scene_w == m[1] && scene_h == m[2] && scene_w * 1080 == scene_h * 1920);
        }
        up_now = ur::DLAA;
        assert(strcmp(tx_resolution(1), "Native (DLAA)") == 0);
        up_now = ur::GAME;
    }
}
'''
    # (saved, handheld, HOS_OUTPUT_RES, the menu's choice, the size, its label, the pool for 305 MB, what the menu saves)
    cases = (
        ("0", 0, None, 0, 2560, 1440, "2048x1152 (game's)", 512, "2048x1152"),   # (the numbers saved before)
        ("1", 0, None, 1, 2560, 1440, "2560x1440", 512, "2560x1440"),
        ("2", 0, None, 2, 3840, 2160, "3840x2160", 687, "3840x2160"),
        ("3", 0, None, 3, 1920, 1080, "1920x1080", 512, "1920x1080"),
        ("4", 0, None, 4, 5120, 1440, "5120x1440", 610, "5120x1440"),
        ("5", 0, None, 5, 5120, 2880, "5120x2880", 900, "5120x2880"),   # (#1670's 5K)
        ("6", 0, None, 0, 2560, 1440, "2048x1152 (game's)", 512, "2048x1152"),
        ("1", 0, "3", 3, 1920, 1080, "1920x1080", 512, "1920x1080"),
        ("3", 1, "3", 0, 2560, 1440, "2048x1152 (game's)", 512, "2048x1152"),   # (handheld: the game's own)
        ("4", 1, None, 0, 2560, 1440, "2048x1152 (game's)", 512, "2048x1152"),
        ("2048x1152", 0, None, 0, 2560, 1440, "2048x1152 (game's)", 512, "2048x1152"),   # (sizes)
        ("1920x1080", 0, None, 3, 1920, 1080, "1920x1080", 512, "1920x1080"),
        ("3840x2160", 0, None, 2, 3840, 2160, "3840x2160", 687, "3840x2160"),
        ("5120X1440", 0, None, 4, 5120, 1440, "5120x1440", 610, "5120x1440"),
        ("5120x2880", 0, None, 5, 5120, 2880, "5120x2880", 900, "5120x2880"),
        ("3440x1440", 0, None, 6, 3440, 1440, "3440x1440", 512, "3440x1440"),   # (the player's own)
        ("1366x768", 0, None, 6, 1360, 768, "1360x768", 512, "1360x768"),   # (a multiple of 8, rounded down)
        ("5120x2160", 0, None, 6, 5120, 2160, "5120x2160", 900, "5120x2160"),   # (between the two 5120s)
        ("0", 0, "5120x2880", 5, 5120, 2880, "5120x2880", 900, "5120x2880"),
        ("2560x1080", 0, None, 6, 2560, 1080, "2560x1080", 512, "2560x1080"),   # (2560 wide, not 1440 high)
        ("2560x1600", 0, None, 6, 2560, 1600, "2560x1600", 512, "2560x1600"),
        ("320x200", 0, None, 0, 2560, 1440, "2048x1152 (game's)", 512, "2048x1152"),   # (out of range: the game's own)
        ("9999x9999", 0, None, 0, 2560, 1440, "2048x1152 (game's)", 512, "2048x1152"),
        ("7680x4320", 0, None, 0, 2560, 1440, "2048x1152 (game's)", 512, "2048x1152"),   # (more than 5120x2880's pixels)
        ("6144x2560", 0, None, 0, 2560, 1440, "2048x1152 (game's)", 512, "2048x1152"),
        ("640x4320", 0, None, 0, 2560, 1440, "2048x1152 (game's)", 512, "2048x1152"),   # (narrower than 5:4)
        ("5120x1080", 0, None, 0, 2560, 1440, "2048x1152 (game's)", 512, "2048x1152"),   # (wider than 32:9)
        ("3840 x 2160", 0, None, 0, 2560, 1440, "2048x1152 (game's)", 512, "2048x1152"),   # (not a size)
        ("abc", 0, None, 0, 2560, 1440, "2048x1152 (game's)", 512, "2048x1152"),
        ("5120x2880", 1, None, 0, 2560, 1440, "2048x1152 (game's)", 512, "2048x1152"),
    )
    with tempfile.TemporaryDirectory(prefix="output-resolution-") as tmp:
        work = Path(tmp)
        source, exe = work / "fixture.cpp", work / "fixture.exe"
        source.write_text(fixture, encoding="utf-8")
        subprocess.run([args.cxx, "-std=c++17", "-I", str(ROOT), str(source), "-o", str(exe)], check=True)
        for saved, handheld, override, mode, w, h, label, pool, writes in cases:
            (work / "hookshot_options.ini").write_text(f"output_res={saved}\nhandheld_profile={handheld}\n", encoding="ascii")
            env = os.environ.copy()
            for key in ("HOS_OUTPUT_RES", "HOS_HANDHELD", "HOS_RT_POOL_MB"):
                env.pop(key, None)
            if override is not None:
                env["HOS_OUTPUT_RES"] = override
            subprocess.run([str(exe), str(mode), str(w), str(h), label, str(pool), writes], cwd=work, env=env, check=True)
    print("PASS: output sizes and the numbers saved before, sizes of the player's own, menu order, what the menu saves, 1080p "
          "override, handheld, render-target budgets and DLSS sizes at 1080p")


if __name__ == "__main__":
    main()
