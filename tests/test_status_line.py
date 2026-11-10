"""The renderer's status line (gpu/vk/status_line.h, vk_replay.cpp status_tick): its video-memory text, the warning past
the driver's allowance (once, again only after dropping back under) and its advice for DLSS and DLAA; and that the
renderer uses them: one line every 600 frames, DLSS's details in it rather than a line of their own. No game or GPU.

python -I -B tests/test_status_line.py [--cxx g++]
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    vk = ROOT / "gpu" / "vk"
    replay = (vk / "vk_replay.cpp").read_text(encoding="utf-8")
    tick = replay[replay.index("void status_tick() {"):]
    tick = tick[:tick.index("\n}\n")]
    for use in ("vram_usage_now(", "sl::crossed(", "sl::over_text(", "sl::vram_text(", "temporal_status(", "sl::kEvery"):
        if use not in tick:
            raise SystemExit("status_tick does not use %s" % use)
    present = replay[replay.index("void do_present("):]
    if "status_tick();" not in present[:present.index("\n}\n")]:
        raise SystemExit("do_present does not call status_tick: no status line")
    for name in ("vk_dlss.cpp", "vk_fsr4.cpp", "vk_temporal.cpp"):
        if "frames drawn; this one's jitter" in (vk / name).read_text(encoding="utf-8"):
            raise SystemExit("%s still logs an upscaler's own 600-frame line beside the status line" % name)
    with tempfile.TemporaryDirectory(prefix="status-line-") as tmp:
        exe = Path(tmp) / "status-line"
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", str(ROOT / "tests" / "test_status_line.cpp"),
                        "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    print("PASS: the status line and its video-memory warning")


if __name__ == "__main__":
    main()
