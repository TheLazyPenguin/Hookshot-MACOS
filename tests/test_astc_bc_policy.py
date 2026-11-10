"""Compile and run the rule for the cards that keep every large ASTC texture as BC3 (gpu/vk/astc_bc_policy.h; no game/GPU)."""
import argparse
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "g++"]

ROOT = Path(__file__).resolve().parents[1]


def check_source():
    """The texture setup still asks the rule, and the switch that overrides it is still read"""
    src = (ROOT / "gpu/vk/vk_texture.cpp").read_text(encoding="utf-8")
    for needle in ('#include "astc_bc_policy.h"', "astc_bc_policy::all_by_vram(allowed)", 'getenv("RX_VK_ASTC_BC_ALL")',
                   "(bw * bh >= 36 || all) ? low : 64ull << 20"):
        if needle not in src:
            raise SystemExit("vk_texture.cpp no longer has: " + needle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    check_source()
    with tempfile.TemporaryDirectory(prefix="astc-bc-policy-") as tmp:
        exe = Path(tmp) / "astc-bc-policy"
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "tests/test_astc_bc_policy.cpp"), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
