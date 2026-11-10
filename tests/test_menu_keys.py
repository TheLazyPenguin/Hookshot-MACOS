"""The Insert menu's confirm and back on a controller: the buttons the Switch's A and B are bound to (gpu/vk/vk_menu_keys.h),
so A opens a page and B goes back as in the game. A Pro Controller's A (the right face button, the Nintendo layout's default)
went back instead of opening the debug tools, Motion or Controls.

The mapping is compiled and run for each layout preset's A and B (host/nn_hid.c's defaults: Nintendo, Xbox / PC, Swap Face)
and for bindings the menu cannot use. Then gpu/vk/vk_menu.cpp is checked for how menu_tick uses it: the pad's confirm and back
are those positions (press[7], press[5]), RX_VK_MENU_SCRIPT's PADS/PADE/PADW/PADN go through the same mapping, and every page
link answers to confirm (Enter, A, a click) and back (Esc, B): Motion, Controls, and the debug tools' rows on the Debug tab,
whose Teleport and Inventory open the map list and the inventory, which go back to the tab. The prompts light the same buttons.
The real keyboard polling block is also compiled to exercise both shortcut keys with queued presses and with polling.

    python -I -B tests/test_menu_keys.py [--cxx g++]
"""
import argparse
import re
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]

FIXTURE = r'''#include "gpu/vk/vk_menu_keys.h"
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL:%d %s\n", __LINE__, #x); std::exit(1); } } while (0)
using namespace mkwvk::menu_keys;
static void expect(int a, int b, int confirm, int back, int line) {
    int c = -9, k = -9;
    confirm_back(a, b, &c, &k);
    if (c != confirm || k != back) {
        std::fprintf(stderr, "FAIL:%d A at %d, B at %d: confirm %d back %d, wanted %d and %d\n", line, a, b, c, k, confirm, back);
        std::exit(1);
    }
}
// KEYBOARD_FIXTURE
int main() {
    test_keyboard();
    expect(kEast, kSouth, kEast, kSouth, __LINE__);    // (Nintendo, the default: A right, B bottom)
    expect(kSouth, kEast, kSouth, kEast, __LINE__);    // (Xbox / PC)
    expect(kWest, kNorth, kWest, kNorth, __LINE__);    // (bound by hand elsewhere on the face)
    expect(-1, -1, kSouth, kEast, __LINE__);           // (none: the bottom confirms, the right goes back)
    expect(9, 10, kSouth, kEast, __LINE__);            // (shoulders: the menu's own tabs, not usable)
    expect(kEast, -1, kEast, kSouth, __LINE__);        // (A usable alone: B the other of the two)
    expect(-1, kSouth, kSouth, kEast, __LINE__);       // (B on the default confirm: moved off it)
    expect(kNorth, kNorth, kNorth, kEast, __LINE__);   // (both on one button: B moved off it)
    for (int a = -1; a < 12; a++)
        for (int b = -1; b < 12; b++) {
            int c, k;
            confirm_back(a, b, &c, &k);
            CHECK(c >= kSouth && c <= kNorth && k >= kSouth && k <= kNorth && c != k);
        }
    CHECK(dot(kSouth) == 3 && dot(kEast) == 1 && dot(kWest) == 2 && dot(kNorth) == 0);
    std::printf("PASS: confirm and back follow A and B\n");
}
'''


KEYBOARD = r'''
enum {
    VK_INSERT = 0x2d, VK_UP = 0x26, VK_DOWN = 0x28, VK_LEFT = 0x25, VK_RIGHT = 0x27,
    VK_ESCAPE = 0x1b, VK_F1 = 0x70, VK_RETURN = 0x0d, VK_DELETE = 0x2e, VK_BACK = 8,
    VK_TAB = 9, VK_PRIOR = 0x21, VK_NEXT = 0x22, VK_HOME = 0x24, VK_END = 0x23
};
using HWND = int;
using DWORD = unsigned;
static int down_key, queued_key;
static bool focused, pad_last;
static struct { int menu_shortcut; } opts;
static HWND GetForegroundWindow() { return 1; }
static DWORD GetCurrentProcessId() { return 1; }
static void GetWindowThreadProcessId(HWND, DWORD* pid) { *pid = focused ? 1 : 2; }
static int GetAsyncKeyState(int key) { return key == down_key ? 0x8000 : 0; }
static bool take_key_press(int key) {
    if (key != queued_key) return false;
    queued_key = 0;
    return true;
}
static struct { bool (*take_key_press)(int); } queue_host{take_key_press}, *host;

static bool keyboard_toggle(int mode, int key, bool queued, bool has_focus = true) {
    opts.menu_shortcut = mode;
    focused = has_focus;
    pad_last = true;
    host = queued ? &queue_host : nullptr;
    down_key = queued ? 0 : key;
    queued_key = queued ? key : 0;
    // KEY_POLL
    CHECK(!queued_key);   // Disabled keys still have to be consumed from the host queue.
    const bool toggle = press[0] || press[6];
    CHECK(pad_last != toggle);
    return toggle;
}

static void test_keyboard() {
    for (bool queued : {false, true}) {
        for (int mode = 0; mode <= 1; mode++) {
            CHECK(!keyboard_toggle(mode, 0, queued));
            CHECK(keyboard_toggle(mode, VK_INSERT, queued) == (mode == 0));
            CHECK(!keyboard_toggle(mode, VK_INSERT, queued, false));
            CHECK(keyboard_toggle(mode, VK_F1, queued));   // (F1 always opens the menu)
            CHECK(!keyboard_toggle(mode, VK_F1, queued, false));
        }
    }
    CHECK(!keyboard_toggle(1, VK_INSERT, false));
    CHECK(!keyboard_toggle(0, VK_INSERT, false));   // A held key still needs a new press after re-enabling it.
    CHECK(!keyboard_toggle(0, 0, false));
    CHECK(keyboard_toggle(0, VK_INSERT, false));
    std::puts("PASS: menu shortcuts respect the saved mode, focus and key edges");
}
'''


def need(text, pattern, what):
    if not re.search(pattern, text, re.S):
        raise SystemExit("FAIL: vk_menu.cpp: " + what)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default="g++")
    a = p.parse_args()
    menu = (ROOT / "gpu/vk/vk_menu.cpp").read_text(encoding="utf-8")
    tick = menu[menu.index("void menu_tick() {"):]
    key_poll = tick[tick.index("    enum { K_N ="):tick.index("    // (hookshot) the gamepads")]
    fixture = FIXTURE.replace("// KEYBOARD_FIXTURE", KEYBOARD.replace("    // KEY_POLL", key_poll))
    with tempfile.TemporaryDirectory(prefix="menu-keys-") as tmp:
        cpp, exe = Path(tmp) / "fixture.cpp", Path(tmp) / "fixture"
        cpp.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT), str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)

    need(menu, r'\{TAB_CONTROLS, "Menu shortcut", &opts\.menu_shortcut, 0, 1, 1, tx_menu_shortcut,[^}]*nullptr, false, true\}',
         "the shortcut choice must be saved in Controls and exempt from presets")
    header = (ROOT / "gpu/vk/vk_menu.h").read_text(encoding="utf-8")
    if "int menu_shortcut = 0;" not in header:
        raise SystemExit("FAIL: existing options must keep both shortcuts")
    # (the pad: confirm and back from A's and B's bindings, every tick, not fixed positions)
    need(tick, r"menu_keys::confirm_back\(host->binding\(HOS_BIND_PAD, HOS_SW_A, 0\), host->binding\(HOS_BIND_PAD, HOS_SW_B, 0\)",
         "confirm and back are not taken from A's and B's bindings")
    need(tick, r"press\[5\] \|= pad\(pad_back\)", "the pad's back is not B's button")
    need(tick, r"press\[7\] \|= pad\(pad_confirm\)", "the pad's confirm is not A's button")
    if re.search(r"press\[[57]\] \|= pad\(HOS_PAD_(SOUTH|EAST)\)", tick):
        raise SystemExit("FAIL: vk_menu.cpp: a fixed face button still confirms or goes back")
    need(tick, r'"PADS", "PADE", "PADW", "PADN".*?press\[5\] \|= p == pad_back, press\[7\] \|= p == pad_confirm',
         "RX_VK_MENU_SCRIPT's pad presses do not go through the same mapping")
    # (the page links on the tabs: confirm opens them)
    need(tick, r"else if \(r\.cheat >= 0\) cheat_press\(r\.cheat, press, changed\)", "the debug tools' rows do not act on the Debug tab")
    need(tick, r"press\[7\] && is_motion_row\(r\)\) cur_tab = TAB_MOTION", "Motion does not open on confirm")
    need(tick, r"press\[7\] && !r\.value && can_bind\(\)\) page = 1", "Controls does not open on confirm")
    need(tick, r"press\[5\] && cur_tab == TAB_MOTION\) cur_tab = TAB_CONTROLS", "back does not leave the Motion page")
    # (a click on a link row is confirm)
    need(tick, r"else if \(!d\.value\) press\[7\] = true;", "a click on a page row does not open it")
    # (the debug tools, rows of the Debug tab: confirm on Teleport opens its list, on Inventory the editor; the list pages go
    # back to the tab, which kept its selection; no page of their own any more)
    cheats = menu[menu.index("void cheat_press(int i,"):menu.index("void menu_tick() {")]
    need(cheats, r"press\[7\] && i == 8\) page = 3", "confirm on Teleport does not open the map list")
    need(cheats, r"press\[7\] && i == 10\) page = 4", "confirm on Inventory does not open the editor")
    if "page == 2" in tick or "page = 2" in tick:
        raise SystemExit("FAIL: vk_menu.cpp: the debug tools' old page is still reached")
    for page in ("4", "3"):
        block = tick[tick.index("open_now.load() && page == %s" % page):]
        need(block[:1500], r"if \(press\[5\]\) page = 0", "back from page %s does not return to the Debug tab" % page)
    need(menu, r'\{TAB_DEBUG, "Developer", nullptr, 0, 0, 0, nullptr, nullptr, nullptr, false, true, -1, true\}',
         "the Debug tab has no Developer heading")
    for name in ("Descriptor reuse", "Sampler cache"):
        need(menu, r'\{TAB_DEBUG, "%s"' % name, name + " is not on the Debug tab")
    need(tick, r"while \(heading_at\(selected\)\)", "the selection does not step over a heading")
    # (the prompts: the buttons lit are the same ones, and the rows say what confirm does)
    need(menu, r"c\.confirm_dot = menu_keys::dot\(pad_confirm\), c\.back_dot = menu_keys::dot\(pad_back\)",
         "the prompts do not light A's and B's buttons")
    need(menu, r'"Open list"', "the Teleport row's prompt does not say it opens the list")
    print("PASS: A and B, Enter and Esc, and clicks open and leave every page")


if __name__ == "__main__":
    main()
