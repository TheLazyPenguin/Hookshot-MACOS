"""Compile host/hos_motion.h with synthetic SDL readings and check the Switch six-axis state it makes.

python -I -B tests/test_motion.py [--cc clang]
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

RUN_ALL_ARGS = ["--cc", "gcc"]

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="cc")
    args = parser.parse_args()
    process_flags = (subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS) if os.name == "nt" else 0

    def run(command):
        result = subprocess.run(command, creationflags=process_flags, capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        result.check_returncode()

    temporary = tempfile.TemporaryDirectory(prefix="motion-")
    folder = Path(temporary.name).resolve()
    try:
        executable = folder / "fixture.exe"
        run([args.cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "host"),
             str(ROOT / "tests/motion_test.c"), "-o", str(executable), "-lm"])
        run([str(executable)])
    finally:
        temporary.cleanup()


if __name__ == "__main__":
    main()
