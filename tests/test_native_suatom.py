"""Authored direct SUATOM fields exercise the real production lowering; no GPU or shader dump.

The same C++ cases also run through Maxwell/IR/SPIR-V in tests/native_suatom/CMakeLists.txt.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "clang++"]

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="clang++")
    args = parser.parse_args()
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS) if os.name == "nt" else 0
    def run(command):
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, creationflags=flags)
        print(result.stdout, end="", flush=True)
        result.check_returncode()

    with tempfile.TemporaryDirectory(prefix="native-suatom-") as tmp:
        exe = Path(tmp) / "fixture.exe"
        run([args.cxx, "-std=c++20", "-O1", "-DSUATOM_LOWERING_ONLY",
                        "-I" + str(ROOT / "gpu/vk/compat"), "-I" + str(ROOT / "gpu/vk/eden"),
                        str(ROOT / "tests/native_suatom.cpp"), "-o", str(exe)])
        run([str(exe)])


if __name__ == "__main__":
    main()
