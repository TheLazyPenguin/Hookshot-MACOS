"""The Insert menu's mouse: the hit-test (gpu/vk/vk_menu_hit.h) compiled and run against positions over the controls as drawn
(tests/test_menu_hit.cpp: the options, the Controls page, a list, the restart question), and the sources checked for the rest of
the path: the window lets the mouse go while the menu is open and takes it back after (WM_APP + 8, host/display.c and
host/posix/display_sdl.c), the free mouse reaches the menu (MkwVkHost.pointer, host/rx_backend.c), and the menu records each
control it draws and tests the mouse against that record, so its picture and its hit-test cannot drift apart.

    python -I -B tests/test_menu_hit.py [--cxx g++]
"""
import argparse
import re
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "g++"]

ROOT = Path(__file__).resolve().parents[1]


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def sources():
    menu, api, backend = read("gpu", "vk", "vk_menu.cpp"), read("gpu", "vk", "vk_api.h"), read("host", "rx_backend.c")
    win, sdl = read("host", "display.c"), read("host", "posix", "display_sdl.c")
    if '#include "vk_menu_hit.h"' not in menu or "hits.at(" not in menu or "hits.clear(" not in menu or "hits.drag(" not in menu:
        raise SystemExit("the menu does not hit-test with vk_menu_hit.h's record of what it drew")
    for part in ("kTabPrev", "kTabNext", "kTab", "kRow", "kCtlRow", "kCtlCell", "kListLine", "kButton"):
        if not re.search(r"hits\.add\([^;]*menu_hit::%s\b" % part, menu):
            raise SystemExit("the menu draws a control it does not record (menu_hit::%s): the mouse cannot reach it" % part)
    # (a click on a row's name selects it and leaves its value: row_click, checked in test_menu_hit.cpp)
    if "menu_hit::row_click(" not in menu or "the right half, or the name, as Right" in menu:
        raise SystemExit("the menu does not decide a row's click with menu_hit::row_click (a click on the name would change the value)")
    if "PostMessageA(app_window(), WM_APP + 8" not in menu:
        raise SystemExit("the menu does not tell the window it opened or closed")
    if "int (*pointer)(MkwVkPointer *out);" not in api or "hos_mouse_pointer," not in backend:
        raise SystemExit("the free mouse does not reach the renderer")
    for name, src in (("display.c", win), ("display_sdl.c", sdl)):
        if "int hos_mouse_pointer(MkwVkPointer *out)" not in src:
            raise SystemExit(name + ": no hos_mouse_pointer")
        if "WM_APP + 8" not in src or "captured_before_menu" not in src:
            raise SystemExit(name + ": the menu does not release the mouse and give the capture back")
    # (a click with the menu open is the menu's: it never captures the mouse for the game)
    down = sdl[sdl.index("case HOS_SDL_EV_MOUSE_DOWN:"):]
    down = down[:down.index("break;")]
    if "if (menu_open)" not in down or "else if (renderer && !mouse_captured) mouse_capture(1);" not in down:
        raise SystemExit("display_sdl.c: a click with the menu open captures the mouse")
    down = win[win.index("case WM_LBUTTONDOWN:"):]
    down = down[:down.index("return 0;")]
    if "if (menu_open)" not in down or "else if (renderer && !mouse_captured) mouse_capture(w, 1);" not in down:
        raise SystemExit("display.c: a click with the menu open captures the mouse")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    sources()
    with tempfile.TemporaryDirectory(prefix="menu-hit-") as tmp:
        exe = Path(tmp) / "menu-hit"
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", str(ROOT / "tests" / "test_menu_hit.cpp"),
                        "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    print("PASS: the menu's mouse")


if __name__ == "__main__":
    main()
