"""The Insert menu's Audio tab: Volume and Mute in background.

host/nn_audio.c's audio_apply_gain is compiled from the source and run: full volume leaves the samples alone, a change
ramps over one frame (no click), the frame ends at the gain asked for, nothing clips, and every channel gets the same
gain. The mixer applies it to each frame before the output. The Volume row's curve is squared (50% is -12 dB), and Mute
in background's foreground check lets an overlay (a toast, a tray flyout) count as the game's only while the game was
the last normal window in front, as host/nn_hid.c's game_in_front does. The option ids the host reads (HOS_OPT_VOLUME and
HOS_OPT_MUTE_BACKGROUND) are checked against the renderer's option table (gpu/vk/vk_replay.cpp) and the menu's rows and
defaults.

    python -I -B tests/test_audio_volume.py [--cc gcc]
"""
import argparse
import os
import re
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cc", "gcc"]

ROOT = Path(__file__).resolve().parents[1]


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def block(text, at):
    """text from at to the end of the first {...} after it"""
    start = text.index("{", at)
    depth = 0
    for i in range(start, len(text)):
        depth += text[i] == "{"
        depth -= text[i] == "}"
        if depth == 0:
            return text[at:i + 1]
    raise SystemExit("no end for the block at %d" % at)


FIXTURE = r"""
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL %%d %%s\n", __LINE__, #x); exit(1); } } while (0)
%s
static void fill(int16_t *pcm, int n, int16_t v) { for (int i = 0; i < n; i++) pcm[i] = (int16_t)(i & 1 ? -v : v); }
int main(void) {
    enum { FRAMES = 240, CH = 2 };
    static int16_t pcm[FRAMES * CH];
    /* full volume: the samples as they were, the extremes too */
    fill(pcm, FRAMES * CH, 32767);
    pcm[1] = -32768;
    CHECK(audio_apply_gain(pcm, FRAMES, CH, 1.0f, 1.0f) == 1.0f);
    CHECK(pcm[0] == 32767 && pcm[1] == -32768 && pcm[2] == 32767);
    /* 100%% to 0: a ramp down over the frame (no jump at its start), silent at its end */
    fill(pcm, FRAMES * CH, 20000);
    CHECK(audio_apply_gain(pcm, FRAMES, CH, 1.0f, 0.0f) == 0.0f);
    CHECK(pcm[0] > 19800);
    CHECK(pcm[(FRAMES - 1) * CH] == 0 && pcm[(FRAMES - 1) * CH + 1] == 0);
    for (int i = 1; i < FRAMES; i++) CHECK(pcm[i * CH] <= pcm[(i - 1) * CH]);
    /* both channels get one gain (left positive, right negative here) */
    for (int i = 0; i < FRAMES; i++) CHECK(pcm[i * CH] == -pcm[i * CH + 1]);
    /* held at 50%%: every sample halved */
    fill(pcm, FRAMES * CH, 20000);
    CHECK(audio_apply_gain(pcm, FRAMES, CH, 0.5f, 0.5f) == 0.5f);
    for (int i = 0; i < FRAMES * CH; i++) CHECK(abs(pcm[i]) == 10000);
    /* 0 back up to 100%%: no sample past what it was (gains up to 1: nothing clips) */
    fill(pcm, FRAMES * CH, -32768);
    CHECK(audio_apply_gain(pcm, FRAMES, CH, 0.0f, 1.0f) == 1.0f);
    for (int i = 0; i < FRAMES * CH; i++) CHECK(pcm[i] >= -32768 && pcm[i] <= 32767);
    CHECK(pcm[(FRAMES - 1) * CH] == -32768);
    /* six channels: the same */
    static int16_t six[FRAMES * 6];
    fill(six, FRAMES * 6, 1000);
    audio_apply_gain(six, FRAMES, 6, 0.25f, 0.25f);
    for (int i = 0; i < FRAMES * 6; i++) CHECK(abs(six[i]) == 250);
    /* the Volume row's curve: squared, 50%% a quarter (-12 dB), held to 0..100, rising */
    CHECK(audio_volume_curve(100) == 1.0f && audio_volume_curve(0) == 0.0f);
    CHECK(fabsf(audio_volume_curve(50) - 0.25f) < 1e-6f);
    CHECK(audio_volume_curve(150) == 1.0f && audio_volume_curve(-5) == 0.0f);
    for (int v = 5; v <= 100; v += 5) CHECK(audio_volume_curve(v) > audio_volume_curve(v - 5));
    /* in front: the game's window yes, another normal window no; an overlay (a toast, a tray flyout, Steam's) only while
       the last normal window in front was the game's */
    int last = 1;
    CHECK(audio_front_decide(1, 0, &last) == 1 && last == 1);
    CHECK(audio_front_decide(0, 1, &last) == 1);   /* (Steam's overlay over the game) */
    CHECK(audio_front_decide(0, 0, &last) == 0 && last == 0);   /* (alt-tab to a browser) */
    CHECK(audio_front_decide(0, 1, &last) == 0);   /* (a toast while the game is behind: still muted) */
    CHECK(audio_front_decide(1, 0, &last) == 1 && last == 1);   /* (back to the game) */
    return 0;
}
"""


def source_checks():
    audio = read("host", "nn_audio.c")
    loop = audio[audio.index("static DWORD WINAPI renderer_main"):audio.index("/* ---- renderer lifecycle")]
    gain_at, out_at = loop.find("audio_apply_gain("), loop.find("output_frame(pcm)")
    if gain_at < 0 or out_at < 0 or gain_at > out_at:
        raise SystemExit("nn_audio.c: the mixer no longer applies the player's volume before the output")
    player = block(audio, audio.index("static float audio_player_gain(void)"))
    if "rx_option(HOS_OPT_VOLUME, 100)" not in player or "rx_option(HOS_OPT_MUTE_BACKGROUND, 0)" not in player:
        raise SystemExit("nn_audio.c: the volume is not read as HOS_OPT_VOLUME (default 100) and HOS_OPT_MUTE_BACKGROUND (off)")
    replay, api = read("gpu", "vk", "vk_replay.cpp"), read("gpu", "vk", "vk_api.h")
    value = {}   # (every HOS_OPT_* enum: the cheats', the motion rows', the Audio tab's, and one-name ones as Text size's)
    for first, start, rest in re.findall(r"enum \{ (HOS_OPT_\w+) = (\d+)([^}]*)\}", api):
        names = [first] + [n.strip() for n in rest.split(",") if n.strip()]
        value.update({n: int(start) + i for i, n in enumerate(names)})
    table = block(replay, replay.index("t.option = [](int id) -> int {"))
    ids = [int(n) if n.isdigit() else value[n] for n in re.findall(r"\bid == (\w+)", table)]
    if len(ids) != len(set(ids)):
        raise SystemExit("vk_replay.cpp: an option id is read twice: %s" % sorted(ids))
    for name, field in (("HOS_OPT_VOLUME", "volume"), ("HOS_OPT_MUTE_BACKGROUND", "mute_background")):
        if not re.search(r"\bid == %s(\) return | \? )opts\.%s\b" % (name, field), table):
            raise SystemExit("vk_replay.cpp: %s is not the menu's opts.%s" % (name, field))
    header, menu = read("gpu", "vk", "vk_menu.h"), read("gpu", "vk", "vk_menu.cpp")
    for default in ("int volume = 100;", "int mute_background = 0;"):
        if default not in header:
            raise SystemExit("vk_menu.h: out of the box the Audio tab is not 100% and not muted in background")
    if not re.search(r'\{TAB_AUDIO, "Volume", &opts\.volume, 0, 100, 5, tx_percent,', menu):
        raise SystemExit("vk_menu.cpp: the Audio tab lost its Volume row (0 to 100%, steps of 5)")
    if not re.search(r'\{TAB_AUDIO, "Mute in background", &opts\.mute_background, 0, 1, 1, tx_onoff,', menu):
        raise SystemExit("vk_menu.cpp: the Audio tab lost its Mute in background row")
    titles = re.search(r"tab_titles\[TAB_COUNT\] = \{([^}]*)\}", menu).group(1)
    if '"Audio"' not in titles:
        raise SystemExit("vk_menu.cpp: the tab strip has no Audio title")
    for name in ("HOS_OPT_VOLUME", "HOS_OPT_MUTE_BACKGROUND"):
        users = []
        for folder in ("host", "gpu"):
            for path in (ROOT / folder).rglob("*.c*"):
                text = path.read_text(encoding="utf-8", errors="replace")
                if re.search(r"\brx_option(_set)?\(\s*(%s|%d)\s*," % (name, value[name]), text):
                    users.append(path.relative_to(ROOT).as_posix())
        if users != ["host/nn_audio.c"]:
            raise SystemExit("%s is read or set outside host/nn_audio.c: %s" % (name, users))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default=os.environ.get("CC", "gcc"))
    args = parser.parse_args()
    source_checks()
    audio = read("host", "nn_audio.c")
    fn = "\n".join(block(audio, audio.index(head)) for head in (
        "static float audio_apply_gain(", "static float audio_volume_curve(", "static int audio_front_decide("))
    with tempfile.TemporaryDirectory(prefix="audio-volume-") as tmp:
        src, exe = Path(tmp) / "audio_volume.c", Path(tmp) / "audio_volume"
        src.write_text(FIXTURE % fn, encoding="utf-8")
        subprocess.run([args.cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(src), "-o", str(exe), "-lm"], check=True)
        subprocess.run([str(exe)], check=True)
    print("PASS: the volume ramps over a frame without clipping on a squared curve, a toast behind the game does not "
          "unmute it, and the Audio tab's options are its own")


if __name__ == "__main__":
    main()
