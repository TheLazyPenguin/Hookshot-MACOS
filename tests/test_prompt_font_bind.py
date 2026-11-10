"""Game-free: the button prompts' font patch at run time (host/prompts.c cmap4_glyph, cmap4_bind) on a cmap made the way the
build makes it (nx2/prompt_assets.py cmap4): a bound Switch button's code point gets its pad input's icon, an unbound one keeps
its own, and the pad icons stay. Also the faces' order: host/prompts.c faces[], gpu/vk/vk_api.h HOS_PROMPT_* and
nx2/prompt_faces.py FACES (after the Switch).

python -I -B tests/test_prompt_font_bind.py [--cc gcc]
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
import prompt_assets  # noqa: E402
import prompt_faces  # noqa: E402

# (the Switch buttons bound in the test: A to the bottom face button, B to the right shoulder; the rest unbound)
BIND = {0: 0, 1: 10}


def check(cond, what):
    if not cond:
        raise SystemExit("FAIL: " + what)


def block(text, marker):
    start = text.index(marker)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cc", default="gcc")
    a = p.parse_args()
    src = (ROOT / "host" / "prompts.c").read_text(encoding="utf-8")
    api = (ROOT / "gpu" / "vk" / "vk_api.h").read_text(encoding="utf-8")

    faces = re.search(r"faces\[HOS_PROMPT_N\] = \{([^}]*)\}", src)
    check(faces is not None, "host/prompts.c has no faces[HOS_PROMPT_N]")
    names = re.findall(r'"([a-z0-9]+)"', faces.group(1))
    check(names == ["switch"] + list(prompt_faces.FACES), "faces[] %s is not the Switch then prompt_faces.FACES" % names)
    enum = re.search(r"enum \{ (HOS_PROMPT_SWITCH[^}]*)\}", api)
    check(enum is not None, "gpu/vk/vk_api.h has no HOS_PROMPT_* enum")
    ids = [e.strip() for e in enum.group(1).split(",") if e.strip()]
    check(ids == ["HOS_PROMPT_" + n.upper() for n in names] + ["HOS_PROMPT_N"], "HOS_PROMPT_* %s is not faces[]" % ids)

    # the codes: the Switch buttons on glyphs 100.., the pad icons on 200.. (as face_font: each Switch code a segment of its own)
    mapping = {c: 100 + b for b, c in enumerate(prompt_assets.SWITCH)}
    mapping.update({prompt_assets.PAD_BASE + i: 200 + i for i in range(len(prompt_assets.PADS))})
    cmap = prompt_assets.cmap4(mapping, set(prompt_assets.SWITCH))
    sub = cmap[20:]   # (one format 4 subtable, after the cmap's header and its two records)
    codes = list(prompt_assets.SWITCH) + [prompt_assets.PAD_BASE + i for i in range(len(prompt_assets.PADS))]

    harness = "\n".join([
        "#include <stdio.h>", "#include <stdlib.h>", "#include <string.h>", '#include "gpu/vk/vk_api.h"',
        "#define PAD_BASE 0xF700",
        "static int hos_binding(int set, int button, int slot) {",
        "    (void)slot;",
        "    if (set != HOS_BIND_PAD) return -1;",
        *("    if (button == %d) return %d;" % kv for kv in BIND.items()),
        "    return -1;",
        "}",
        re.search(r"static const uint16_t switch_code\[HOS_SW_N\] = \{[^}]*\};", src).group(0),
        re.search(r"static unsigned rd16\(.*", src).group(0),
        re.search(r"static uint32_t rd32\(.*", src).group(0),
        re.search(r"static void wr16\(.*", src).group(0),
        block(src, "static unsigned cmap4_glyph("),
        block(src, "static int cmap4_bind("),
        block(src, "static int bind_font("),
        "int main(int argc, char **argv) {",
        "    FILE *f = fopen(argv[1], \"rb\");",
        "    static unsigned char st[65536];",
        "    const size_t n = fread(st, 1, sizeof st, f);",
        "    fclose(f);",
        "    if (argc > 2 && !strcmp(argv[2], \"font\")) { printf(\"%d\\n\", bind_font(st, n)); return 0; }",
        "    printf(\"%d\\n\", cmap4_bind(st, n));",
        "    for (int i = 2; i < argc; i++) printf(\"%u\\n\", cmap4_glyph(st, n, (unsigned)strtoul(argv[i], NULL, 0)));",
        "    return 0;",
        "}", ""])
    with tempfile.TemporaryDirectory() as tmp:
        c, exe, bin_ = Path(tmp) / "bind.c", Path(tmp) / "bind", Path(tmp) / "cmap4.bin"
        c.write_text(harness, encoding="utf-8")
        bin_.write_bytes(sub)
        subprocess.run([a.cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT), str(c), "-o", str(exe)], check=True)
        out = subprocess.run([str(exe), str(bin_)] + [str(x) for x in codes], check=True, capture_output=True,
                             text=True).stdout.split()
        # (a font whose cmap names a subtable at 0xFFFFFFF4: offset + 14 wrapped, and the check read 4 GB past the font)
        font = Path(tmp) / "wrap.otf"
        cmap_table = (0).to_bytes(2, "big") + (1).to_bytes(2, "big") + bytes(4) + (0xFFFFFFF4).to_bytes(4, "big")
        font.write_bytes(bytes(4) + (1).to_bytes(2, "big") + bytes(6) + b"cmap" + bytes(4) + (28).to_bytes(4, "big") +
                         len(cmap_table).to_bytes(4, "big") + cmap_table)
        wrapped = subprocess.run([str(exe), str(font), "font"], capture_output=True, text=True)
        check(wrapped.returncode == 0 and wrapped.stdout.split() == ["0"],
              "a cmap subtable offset that wraps: exit %d, %r" % (wrapped.returncode, wrapped.stdout))
    done, got = int(out[0]), [int(x) for x in out[1:]]
    check(done == len(BIND), "%d buttons bound, not %d" % (done, len(BIND)))
    for b, code in enumerate(prompt_assets.SWITCH):
        want = 200 + BIND[b] if b in BIND else 100 + b
        check(got[b] == want, "Switch button %d (U+%04X): glyph %d, not %d" % (b, code, got[b], want))
    for i in range(len(prompt_assets.PADS)):
        check(got[len(prompt_assets.SWITCH) + i] == 200 + i, "pad icon %d moved" % i)
    print("ok: %d of %d Switch buttons pointed at their pad icons, the rest and the pad icons kept"
          % (done, len(prompt_assets.SWITCH)))


if __name__ == "__main__":
    main()
