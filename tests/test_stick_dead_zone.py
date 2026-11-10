"""The sticks' dead zone is the player's: the Insert menu's "Stick dead zone" row (stick_dead_zone in
hookshot_options.ini), issue 752.

Both pad paths, SDL (host/pad_sdl.c) and XInput (host/nn_hid.c), cut each axis at XInput's 7849 (~24%), a lot on a
worn or a precise stick. They now cut through one function, host/nn_hid.c's hos_stick_axis, whose threshold is the
row's (option 11): Default (7849, the same output as before for every input), 5%, 10%, 15%, 20%, 30%.
The function, pad_sdl.c's stick_value and the menu's row, label and ini parsing are compiled alone (gcc, g++) and
checked over every int16 input.

python -I -B tests/test_stick_dead_zone.py [--cc gcc] [--cxx g++]
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cc", "gcc", "--cxx", "g++"]

ROOT = Path(__file__).resolve().parents[1]
THRESHOLDS = [7849, 1638, 3277, 4915, 6553, 9830]   # (Default, then 5% ... 30% of 32767)


def block(text, marker):
    start = text.index(marker)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def check(cond, what):
    if not cond:
        raise SystemExit("FAIL: " + what)


def run(compiler, src, name, tmp, flags):
    path = Path(tmp) / name
    path.write_text(src, encoding="utf-8")
    exe = Path(tmp) / (name + ".exe")
    subprocess.run([compiler, *flags, "-Wall", "-Werror", "-o", str(exe), str(path)], check=True)
    r = subprocess.run([str(exe)], capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    check(r.returncode == 0, name + ": " + r.stderr.strip())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cc", default="gcc")
    p.add_argument("--cxx", default="g++")
    a = p.parse_args()
    hid = (ROOT / "host" / "nn_hid.c").read_text(encoding="utf-8")
    sdl = (ROOT / "host" / "pad_sdl.c").read_text(encoding="utf-8")
    api = (ROOT / "gpu" / "vk" / "vk_api.h").read_text(encoding="utf-8")
    replay = (ROOT / "gpu" / "vk" / "vk_replay.cpp").read_text(encoding="utf-8")
    menu = (ROOT / "gpu" / "vk" / "vk_menu.cpp").read_text(encoding="utf-8")
    header = (ROOT / "gpu" / "vk" / "vk_menu.h").read_text(encoding="utf-8")
    readme = (ROOT / "readme.md").read_text(encoding="utf-8")

    check(not re.search(r"HOS_OPT_\w+ = 11\b", api), "a HOS_OPT_ enum also takes option 11")
    check("int32_t hos_stick_axis(" in hid, "nn_hid.c has no hos_stick_axis")
    pads = block(hid, "static void pads_read(")
    check("rx_option(11, 0)" in pads and "hos_stick_axis(thumb[i], zone)" in pads,
          "XInput's sticks do not go through hos_stick_axis with the row's zone (option 11)")
    check("7849" not in pads, "XInput's sticks still cut at 7849 themselves")
    poll = block(sdl, "static void pads_poll")
    check("rx_option(11, 0)" in poll, "SDL's sticks do not read the row (option 11)")
    check(poll.count("stick_value(") == 4, "SDL's four axes do not all go through stick_value")
    value = block(sdl, "static int32_t stick_value(")
    check("hos_stick_axis(" in value and "7849" not in value, "pad_sdl.c's stick_value cuts on its own")
    option = replay[replay.index("t.option = "):]
    option = option[:option.index("};") + 2]
    check("if (id == 11) return opts.stick_dead_zone;" in option, "the host cannot see the menu's row (option 11)")
    check("int stick_dead_zone = 0;" in header, "the option's default is not 0 (Default)")
    row = re.search(r'\{TAB_CONTROLS, "Stick dead zone", &opts\.stick_dead_zone, 0, 5, 1, tx_stick_dead_zone,\s*"[^}]*\},',
                    menu)
    check(row is not None, "the Insert menu has no Stick dead zone row (0 to 5)")
    check(row.group(0).rstrip().endswith("nullptr, false, true},"),
          "the row is not preset_exempt: changing the dead zone would set the quality preset to Custom")
    check("| | Stick dead zone | Default (24%), 5%, 10%, 15%, 20%, 30% | Default (24%) |" in readme,
          "readme.md's option table has no Stick dead zone row")

    c = r'''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL:%d %s\n", __LINE__, #x); exit(1); } } while (0)
''' + block(hid, "int32_t hos_stick_axis(") + "\n" + block(sdl, "static int32_t stick_value(") + r'''
/* (before issue 752: nn_hid.c's XInput cut, and pad_sdl.c's, which flips first) */
static int32_t old_xinput(int16_t t) { const int a = t < -32767 ? -32767 : t; return (a > 7849 || a < -7849) ? a : 0; }
static int32_t old_sdl(int16_t v, int flip) {
    int32_t a = v < -32767 ? -32767 : v;
    if (flip) a = -a;
    return (a > 7849 || a < -7849) ? a : 0;
}
int main(void) {
    static const int32_t t[6] = {''' + ", ".join(map(str, THRESHOLDS)) + r'''};
    static const int bad[] = {-1, 6, 99, -2147483647 - 1};
    for (int32_t i = -32768; i <= 32767; i++) {
        const int16_t v = (int16_t)i;
        CHECK(hos_stick_axis(v, 0) == old_xinput(v));
        for (int k = 0; k < 4; k++) CHECK(hos_stick_axis(v, bad[k]) == old_xinput(v));   /* (out of range: Default) */
        CHECK(stick_value(v, 0, 0) == old_sdl(v, 0) && stick_value(v, 1, 0) == old_sdl(v, 1));
        for (int z = 0; z < 6; z++) {
            const int32_t a = i < -32767 ? -32767 : i, want = a > t[z] || a < -t[z] ? a : 0;
            CHECK(hos_stick_axis(v, z) == want);
            CHECK(stick_value(v, 0, z) == want && stick_value(v, 1, z) == -want);
        }
    }
    for (int z = 0; z < 6; z++)
        CHECK(hos_stick_axis(t[z], z) == 0 && hos_stick_axis(t[z] + 1, z) == t[z] + 1 && hos_stick_axis(-t[z], z) == 0 &&
              hos_stick_axis(-t[z] - 1, z) == -t[z] - 1 && hos_stick_axis(-32768, z) == -32767);
    printf("stick: Default is the old cut for all 65536 inputs, both paths; 5 other thresholds exact\n");
    return 0;
}
'''

    init = block(menu, "void menu_init(")
    loop = block(init, "for (Row& r : rows) {")
    check("ini_key(r)" in loop, "menu_init's options loop no longer reads rows by ini_key")
    cxx = r'''#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL:%d %s\n", __LINE__, #x); exit(1); } } while (0)
enum MenuTab { TAB_CONTROLS };
struct Options { int output_res = 0, resolution = 0, fps_cap = 0, upscale = 0, dlss = 0, handheld = 0, stick_dead_zone = 0; } opts;
static int parse_output(const char* text) { return atoi(text); }   // (the Output row's own parse: not what this checks)
''' + block(menu, "struct Row {") + ";\n" + block(menu, "const char* tx_stick_dead_zone(") + "\n" + \
        "Row rows[] = {" + row.group(0) + "};\n" + block(menu, "const char* ini_key(") + r'''
static int parse(const char* text) {
    opts.stick_dead_zone = 0;
    char line[80];
    snprintf(line, sizeof line, "%s", text);
    char* eq = strchr(line, '=');
    *eq = 0;
    ''' + loop + r'''
    return opts.stick_dead_zone;
}
int main() {
    CHECK(!strcmp(ini_key(rows[0]), "stick_dead_zone"));
    CHECK(rows[0].preset_exempt && !rows[0].restart);
    CHECK(parse("stick_dead_zone=0\n") == 0 && parse("stick_dead_zone=3\n") == 3 && parse("stick_dead_zone=5\n") == 5);
    CHECK(parse("stick_dead_zone=9\n") == 5 && parse("stick_dead_zone=-4\n") == 0 && parse("stick_dead_zone=x\n") == 0);
    CHECK(parse("stick_deadzone=3\n") == 0);
    static const char* want[] = {"Default (24%)", "5%", "10%", "15%", "20%", "30%"};
    for (int v = 0; v < 6; v++) CHECK(!strcmp(rows[0].text(v), want[v]));
    CHECK(!strcmp(rows[0].text(-1), want[0]) && !strcmp(rows[0].text(6), want[0]));
    (void)parse_output("0");
    printf("menu: stick_dead_zone parses and clamps to 0..5; labels Default (24%%) ... 30%%\n");
    return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix="stick-dead-zone-") as tmp:
        run(a.cc, c, "stick.c", tmp, ["-std=c11", "-O1"])
        run(a.cxx, cxx, "menu.cpp", tmp, ["-std=c++17"])
    print("ok")


if __name__ == "__main__":
    main()
