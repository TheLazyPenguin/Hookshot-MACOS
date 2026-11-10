"""The Insert menu's rows under the mouse stay put when the mouse chooses one (gpu/vk/vk_menu.cpp).

scroll_rows brings a new selection into view with a row of context above and below it, as the keys and the pad want. A
row chosen by the mouse is under the cursor, so in view already: scrolled to it, the top row slid down under a cursor
that had not moved, and the next click landed on the row above. On the Graphics tab that is the Output resolution, above
the Upscaler: picking DLSS changed the Output resolution, and closing the menu asked to restart for it.

scroll_rows is compiled from the source with stubs and run: the keys' selection scrolls, the mouse's (marked scrolled to,
as menu_tick does) does not. menu_tick is checked for that mark.

    python -I -B tests/test_menu_mouse_scroll.py [--cxx g++]
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FIXTURE = r"""
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <utility>
enum { TAB_MOTION = 4 };
float scroll_at[TAB_MOTION + 2];
int wheel_rows[TAB_MOTION + 2];
int scrolled_to[TAB_MOTION + 2] = {-1, -1, -1, -1, -1, -1};
float scroll_want[TAB_MOTION + 2];
float ease_step = 1;
%(scroll_rows)s
#define CHECK(name, c) do { if (!(c)) { std::fprintf(stderr, "FAIL %%s at line %%d\n", name, __LINE__); return 1; } } while (0)
int main() {
    // (30 rows, 10 fit: rows from top 0 to bottom 100, 10 apart. The Upscaler right below the Output resolution)
    const int kOutput = 11, kUpscaler = 12, kSharpness = 16;
    int shown = 0;
    // the keys: a new selection is brought into view with a row of context
    float first = scroll_rows(0, 30, 25, 0, 100, 10, &shown);
    CHECK("ten fit", shown == 10);
    CHECK("the keys keep a row of context below the selection", (int)first == 25 + 2 - 10);
    // the rows scrolled (the wheel) so the Upscaler is the top one shown; Sharpness, further down, is selected
    for (int mark = 0; mark < 2; mark++) {
        scroll_at[0] = scroll_want[0] = kUpscaler, scrolled_to[0] = kSharpness;
        first = scroll_rows(0, 30, kSharpness, 0, 100, 10, &shown);
        CHECK("the Upscaler on top", (int)first == kUpscaler);
        // the cursor goes to the top row: the mouse chooses the Upscaler (menu_tick marks it scrolled to; before, it did not)
        if (mark) scrolled_to[0] = kUpscaler;
        first = scroll_rows(0, 30, kUpscaler, 0, 100, 10, &shown);
        const int under_cursor = (int)first;   // (the top row's place)
        if (mark) CHECK("the mouse's choice stays under the cursor", under_cursor == kUpscaler);
        else CHECK("unmarked: the list slides down a row, the Output resolution under the cursor", under_cursor == kOutput);
    }
    std::puts("PASS: a row chosen by the mouse stays under the cursor");
    return 0;
}
"""


def function(source, start):
    at = source.find(start)
    if at < 0:
        raise SystemExit("vk_menu.cpp: %s is missing" % start)
    body = source[at:]
    return body[:body.index("\n}\n") + 3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    menu = (ROOT / "gpu" / "vk" / "vk_menu.cpp").read_text(encoding="utf-8")
    tick = function(menu, "void menu_tick() {")
    if "sel = hit.index, scrolled_to[cur_tab] = sel, changed = true;" not in tick:
        raise SystemExit("menu_tick: a row chosen by the mouse is scrolled to as the keys' choice is (the rows slide under "
                         "the cursor, and the next click lands on another row)")
    if "scroll_rows(cur_tab, " not in menu:
        raise SystemExit("draw_menu: the options' rows do not scroll by the tab's slot (scrolled_to[cur_tab] would not match)")
    with tempfile.TemporaryDirectory(prefix="menu-mouse-scroll-") as tmp:
        src, exe = Path(tmp) / "fixture.cpp", Path(tmp) / "fixture"
        src.write_text(FIXTURE % {"scroll_rows": function(menu, "float scroll_rows(")}, encoding="utf-8")
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", str(src), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
