"""The Insert menu's Text size scales the text of dialogue, Navi and signs, and only when the player asks for it.

nx2/oot_patches.py calls hos_oot_text_pane (host/oot_text_size.c) from f_80b1e140, a LetterAnimControl's step, with the
control in x19. The host scales the 2D scale of the control's pane wrapper (+0x28 x, +0x38 y) by the menu's choice, from the
game's own value: never twice, again from the game's value whenever the game writes it, and back to it at Original.

python -I -B tests/test_text_size.py [--cc gcc]
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cc", "gcc"]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nx2"))
import oot_patches  # noqa: E402

# (the host file with a guest memory of its own: a flat buffer from BASE, and the menu's choice in a variable)
FIXTURE_HEAD = r'''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL:%d %s\n", __LINE__, #x); exit(1); } } while (0)
typedef struct { int unused; } Ctx;
enum { HOS_OPT_TEXT_SIZE = 10 };
#define BASE 0x10000000ull
static unsigned char mem[0x40000];
static int writes, menu = 0;
static uint64_t recomp_load64(Ctx *c, uint64_t a) { uint64_t v; (void)c; memcpy(&v, mem + (a - BASE), 8); return v; }
static uint64_t recomp_load32(Ctx *c, uint64_t a) { uint32_t v; (void)c; memcpy(&v, mem + (a - BASE), 4); return v; }
static void recomp_store32(Ctx *c, uint64_t a, uint32_t v) { (void)c; memcpy(mem + (a - BASE), &v, 4); writes++; }
int rx_option(int id, int otherwise) { return id == HOS_OPT_TEXT_SIZE ? menu : otherwise; }
'''

FIXTURE_MAIN = r'''
static void put64(uint64_t a, uint64_t v) { memcpy(mem + (a - BASE), &v, 8); }
static void putf(uint64_t a, float v) { memcpy(mem + (a - BASE), &v, 4); }
static float getf(uint64_t a) { float v; memcpy(&v, mem + (a - BASE), 4); return v; }
/* a control at anim, its wrapper and pane after it, the game's scale g */
static uint64_t pane_at(uint64_t anim, float g) {
    const uint64_t wrapper = anim + 0x100, pane = anim + 0x200;
    put64(anim + 0x28, wrapper), put64(wrapper + 8, pane), putf(wrapper + 0x28, g), putf(wrapper + 0x38, g);
    return wrapper;
}
static int near(float a, float b) { return a > b - 1e-5f && a < b + 1e-5f; }
int main(void) {
    Ctx c;
    const uint64_t anim = BASE + 0x1000, w = pane_at(anim, 0.8f);

    hos_oot_text_pane(&c, anim);   /* Original: nothing written */
    CHECK(writes == 0 && getf(w + 0x28) == 0.8f && getf(w + 0x38) == 0.8f);

    menu = 4;   /* 175%: both fields, once, from the game's value */
    hos_oot_text_pane(&c, anim);
    CHECK(near(getf(w + 0x28), 1.4f) && near(getf(w + 0x38), 1.4f));
    const int after = writes;
    hos_oot_text_pane(&c, anim);
    hos_oot_text_pane(&c, anim);
    CHECK(writes == after && near(getf(w + 0x28), 1.4f));   /* not again on the next steps */

    putf(w + 0x28, 0.5f);   /* the game writes its own value again */
    hos_oot_text_pane(&c, anim);
    CHECK(near(getf(w + 0x28), 0.875f) && near(getf(w + 0x38), 1.4f));

    menu = 2;   /* another choice: from the game's value, not the scaled one */
    hos_oot_text_pane(&c, anim);
    CHECK(near(getf(w + 0x28), 0.625f) && near(getf(w + 0x38), 1.0f));

    menu = 0;   /* back to Original: the game's own values */
    hos_oot_text_pane(&c, anim);
    CHECK(getf(w + 0x28) == 0.5f && getf(w + 0x38) == 0.8f);

    menu = 99;   /* out of range: Original */
    hos_oot_text_pane(&c, anim);
    CHECK(getf(w + 0x28) == 0.5f);

    menu = 3;   /* no control, no wrapper, no pane: nothing read past them, nothing written */
    writes = 0;
    hos_oot_text_pane(&c, 0);
    put64(BASE + 0x9000 + 0x28, 0);
    hos_oot_text_pane(&c, BASE + 0x9000);
    const uint64_t bare = pane_at(BASE + 0xa000, 0.8f);
    put64(bare + 8, 0);
    hos_oot_text_pane(&c, BASE + 0xa000);
    CHECK(writes == 0 && getf(bare + 0x28) == 0.8f);

    /* more panes than the host keeps: each new one is still scaled, and the one on screen keeps its own value */
    for (int i = 0; i < 200; i++) {
        const uint64_t a = BASE + 0x10000 + (uint64_t)i * 0x300, wi = pane_at(a, 0.8f);
        hos_oot_text_pane(&c, a);
        hos_oot_text_pane(&c, anim);
        CHECK(near(getf(wi + 0x28), 1.2f) && near(getf(w + 0x38), 1.2f));
    }
    hos_oot_text_pane(&c, anim);
    CHECK(near(getf(w + 0x38), 1.2f));

    printf("PASS: text size scales the text pane's 2D scale from the game's own value\n");
    return 0;
}
'''


def check(cond, what):
    if not cond:
        raise SystemExit("FAIL: " + what)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cc", default="gcc")
    a = p.parse_args()

    host = (ROOT / "host" / "oot_text_size.c").read_text(encoding="utf-8")
    replay = (ROOT / "gpu" / "vk" / "vk_replay.cpp").read_text(encoding="utf-8")
    menu = (ROOT / "gpu" / "vk" / "vk_menu.cpp").read_text(encoding="utf-8")
    api = (ROOT / "gpu" / "vk" / "vk_api.h").read_text(encoding="utf-8")
    option = replay[replay.index("t.option = "):]
    option = option[:option.index("};") + 2]

    check("enum { HOS_OPT_TEXT_SIZE = 10 };" in api, "no option id for Text size")
    check(re.search(r"id == 10\b", option) is None, "option 10 is answered by another row too")
    check("if (id == HOS_OPT_TEXT_SIZE) return opts.text_size;" in option, "the host cannot see the Text size row")
    check('"Text size", &opts.text_size, 0, 4, 1, tx_text_size' in menu, "the Insert menu has no Text size row")
    check("rx_option(HOS_OPT_TEXT_SIZE, 0)" in host, "the host does not read the menu's row")
    check('getenv("HOS_TEXT_SIZE")' in host, "no HOS_TEXT_SIZE switch")

    snippet = oot_patches.TEXT_NEW[len(oot_patches.TEXT_OLD):]
    check(snippet.count("hos_oot_text_pane(c, c->x[19]);") == 1, "the letters' block does not call the text size hook")
    check("extern void hos_oot_text_pane(Ctx *c, uint64_t anim);" in oot_patches.TEXT_DECL,
          "the lifted file does not declare the hook")
    check("void hos_oot_text_pane(Ctx *c, uint64_t anim)" in host, "the host's hook has another signature")

    body = "".join(line for line in host.splitlines(keepends=True) if not line.startswith("#include"))
    body = body.replace("int rx_option(int id, int otherwise);\n", "", 1)
    with tempfile.TemporaryDirectory(prefix="text-size-") as tmp:
        c = Path(tmp) / "fixture.c"
        exe = Path(tmp) / "fixture"
        c.write_text(FIXTURE_HEAD + body + FIXTURE_MAIN, encoding="utf-8")
        subprocess.run([a.cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", str(c), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    print("PASS: the Insert menu's Text size row reaches the text panes")


if __name__ == "__main__":
    main()
