"""Renaming markers must not alias any original operand of a native instruction.

Compiles a synthetic FFMA fixture against the actual Ampere lowering. No game, GPU or SDK.
    python -I -B tests/test_lower_register_markers.py [--cxx clang++]
"""
import argparse
import os
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "clang++"]

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="clang++")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="lower-register-markers-") as tmp:
        exe = Path(tmp) / ("lower_register_markers.exe" if os.name == "nt" else "lower_register_markers")
        subprocess.run([args.cxx, "-std=c++20", "-O1", "-w",
                        "-I" + str(ROOT / "gpu/vk/eden"), "-I" + str(ROOT / "gpu/vk/compat"),
                        str(ROOT / "tests/lower_register_markers_test.cpp"), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
