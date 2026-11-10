"""Compile the complete production window procedure with portable, authored Win32 API mocks."""
import argparse
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cc", "gcc"]


ROOT = Path(__file__).resolve().parents[1]


def wndproc(source):
    start = source.index("static LRESULT CALLBACK wndproc(")
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="gcc")
    parser.add_argument("--source", type=Path, default=ROOT / "host/display.c")
    args = parser.parse_args()
    procedure = wndproc(args.source.read_text(encoding="utf-8"))
    template = (ROOT / "tests/screensaver_test.c").read_text(encoding="utf-8")
    assert template.count("/* ACTUAL_WNDPROC */") == 1
    with tempfile.TemporaryDirectory(prefix="hookshot-screensaver-") as temp:
        source, executable = Path(temp) / "fixture.c", Path(temp) / "fixture.exe"
        source.write_text(template.replace("/* ACTUAL_WNDPROC */", procedure), encoding="utf-8")
        priority = {"creationflags": getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)}
        subprocess.run([args.cc, "-std=c11", "-O0", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(executable)],
                       check=True, **priority)
        subprocess.run([str(executable)], check=True, **priority)


if __name__ == "__main__":
    main()
