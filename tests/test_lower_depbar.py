"""Every DEPBAR form lowers, to nothing: the Ampere -> Maxwell lowering rejected the scoreboard waits OoT's programs
use ("native dependency barrier mode"), so their programs never ran. Compiles tests/lower_depbar_test.cpp against the
real lowering header; no game, GPU or SDK.

python -I -B tests/test_lower_depbar.py [--cxx clang++]
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "clang++"]

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default="clang++")
    a = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="lower-depbar-") as tmp:
        exe = Path(tmp) / "lower_depbar_test"
        # (the lowering header is not warning-clean; nx2/lower_test.py builds it with -Wno-everything as well)
        subprocess.run([a.cxx, "-std=c++20", "-O1", "-w",
                        "-I" + str(ROOT / "gpu/vk/eden"), "-I" + str(ROOT / "gpu/vk/compat"),
                        str(ROOT / "tests/lower_depbar_test.cpp"), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
