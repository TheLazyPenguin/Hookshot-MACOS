#!/bin/bash
# Game-free: a player's build started from what the AppImage carries, not from the repository. CI's AppImage job packages
# the builder but never builds a game with it, so a file the AppImage leaves out was found by every player instead: #1459
# made nx2/build.py write the menu's fonts from third_party/fonts at every build start, the AppImage does not carry that
# folder, and every Linux build stopped at LibertinusSans-Regular.ttf while CI stayed green (2026-11-10, #1567).
#
#   scripts/linux/check_player_build.sh [<Hookshot-...-x86_64.AppImage>]   (default: the newest in build-linux/)
#
# The image is extracted, as its runtime does, and run with AppRun's own environment (the AppImage's Python, compiler,
# sysroot, FFmpeg and the prebuilt Vulkan back end, HOOKSHOT_VK_PREBUILT) in an otherwise empty one, so nothing of the
# checkout or of CI's caches stands in for what the image lacks:
#   - AppRun --cli --help: nx2/make_game.py, as the builder window starts it;
#   - nx2/build.py --standalone --dry-run, as make_game.py runs it: its whole start-up up to the compile, which is where
#     the game's lifted code is first needed. Every other file the compile would read must be in the image.
# Neither may write into the image's tree: on a player's PC it is read-only.
set -euo pipefail
cd "$(dirname "$0")/../.."
IMAGE=${1:-$(ls -t build-linux/Hookshot-*-x86_64.AppImage 2>/dev/null | head -1 || true)}
[ -n "$IMAGE" ] && [ -f "$IMAGE" ] || { echo "no AppImage to check (scripts/linux/appimage.sh makes one)"; exit 1; }
IMAGE=$(readlink -f "$IMAGE")
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
(cd "$TMP" && "$IMAGE" --appimage-extract >/dev/null)
R=$TMP/squashfs-root
T=$R/usr/share/hookshot
mkdir -p "$TMP/home" "$TMP/work"
# (AppRun's environment, from AppRun itself: its lines before it starts Python, sourced with $0 naming it, so HERE is the image)
sed '/^PY=/,$d' "$R/AppRun" > "$TMP/apprun-env.sh"
in_image() {
    env -i PATH=/usr/bin:/bin HOME="$TMP/home" LANG=C.UTF-8 bash -c '. "$1"; shift; exec "$@"' "$R/AppRun" "$TMP/apprun-env.sh" "$@"
}
touch "$TMP/before"
sleep 1   # (so a file written below is newer than the stamp)

echo "== the pipeline state list (assets/pipeline_states.bin.xz: nx2/make_game.py unpacks it beside the game)"
(cd "$T" && in_image "$R/usr/python/bin/python3" -I -B nx2/pipeline_states.py --check assets/pipeline_states.bin.xz) ||
    { echo "the AppImage carries no readable assets/pipeline_states.bin.xz: a new install's first field load would be drawn white"; exit 1; }

echo "== AppRun --cli --help"
in_image "$R/AppRun" --cli --help > "$TMP/help.txt"
grep -q -- "--nup" "$TMP/help.txt" || { cat "$TMP/help.txt"; echo "nx2/make_game.py did not start"; exit 1; }

echo "== nx2/build.py --standalone --dry-run (as nx2/make_game.py runs it, with no game)"
# (-B: no __pycache__ written into the image's tree. make_game.py's other settings: nx2/make_game.py, the compile's run())
(cd "$T" && in_image env OOT_WORK="$TMP/work" RX_RELEASE=1 A64_HOT_CHUNK=1 PYTHONIOENCODING=utf-8 \
    "$R/usr/python/bin/python3" -I -B -u -X utf8 nx2/build.py --standalone --jobs 1 --dry-run)

# (Python's own __pycache__ aside: AppRun runs Python with -I, which writes it where it can, and does without where it cannot)
written=$(find "$R" -type f -newer "$TMP/before" ! -path "*/__pycache__/*" -print)
if [ -n "$written" ]; then
    echo "a player's build wrote into the AppImage's tree, which is read-only on a player's PC:"
    echo "$written" | head -20
    exit 1
fi
echo "a player's build starts from the AppImage's tree"
