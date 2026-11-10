"""Compile the actual invalidate wrapper and native vcore away/back functions with a bounded lease harness.

python -I -B tests/test_invalidate_vcore.py [--cxx clang++]
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

RUN_ALL_ARGS = ["--cxx", "g++"]

ROOT = Path(__file__).resolve().parents[1]
CASES = ("vulkan", "fallback", "immediate", "fallback-immediate", "zero", "already-away",
         "non-guest", "disabled", "producer")


def block(source, marker):
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="clang++")
    parser.add_argument("--source", type=Path, default=ROOT / "host/rx_backend.c")
    parser.add_argument("--case", choices=CASES)
    args = parser.parse_args()
    wrapper = block(args.source.read_text(encoding="utf-8"), "void rx_nvn_invalidate(")
    threads = (ROOT / "host/hos_thread.c").read_text(encoding="utf-8")
    native = "\n".join(block(threads, marker) for marker in
                       ("int hos_vcore_away(", "void hos_vcore_back("))
    compiler = shutil.which(args.cxx)
    if not compiler:
        raise SystemExit("C++ compiler not found: " + args.cxx)
    msvc = Path(compiler).name.lower() in ("cl", "cl.exe")
    env = os.environ.copy()
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
        if not msvc:
            for name in ("INCLUDE", "LIB", "LIBPATH"):
                env.pop(name, None)
            windows = Path(os.environ["SystemRoot"])
            env["PATH"] = os.pathsep.join(map(str, (Path(compiler).resolve().parent, windows / "System32", windows)))

    def run(command, timeout):
        result = subprocess.run(command, env=env, creationflags=flags, timeout=timeout,
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        result.check_returncode()

    with tempfile.TemporaryDirectory(prefix="invalidate-vcore-") as temporary:
        folder = Path(temporary)
        (folder / "actual_invalidate.inc").write_text(native + "\n" + wrapper + "\n", encoding="utf-8")
        binary = folder / "fixture.exe"
        fixture = ROOT / "tests/invalidate_vcore_test.cpp"
        if msvc:
            command = [compiler, "/nologo", "/std:c++17", "/EHsc", "/W4", "/WX", "/I" + str(ROOT),
                       "/I" + str(folder), "/Fo" + str(folder / "fixture.obj"), "/Fe" + str(binary), str(fixture)]
        else:
            command = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread", "-I" + str(ROOT),
                       "-I" + str(folder), str(fixture), "-o", str(binary)]
        run(command, 60)
        for case in ((args.case,) if args.case else CASES):
            run([str(binary), case], 10)


if __name__ == "__main__":
    main()
