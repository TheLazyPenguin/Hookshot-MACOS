"""Check actual replay frame-wait parsing and ordering with authored values; no Vulkan/game required."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]
CASES = ("unset", "empty", "zero", "negative", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "prefix",
         "malformed", "int_max", "positive_overflow", "negative_overflow")


def actual_block(source):
    start = source.index("{   // (RX_VK_WAIT_GPU=<frames>:")
    depth, at = 1, start + 1
    while depth:
        if source[at] == "{":
            depth += 1
        elif source[at] == "}":
            depth -= 1
        at += 1
    block = source[start:at]
    # Observe the actual parsed setting BEFORE any production indexing. This lets
    # original-source negatives reject an out-of-range count without executing UB.
    marker = "if (ahead > 0)"
    assert block.count(marker) == 1
    return block.replace(marker, "check_ahead(ahead, sizeof(values) / sizeof(values[0]));\n" + marker, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default=os.environ.get("CXX", "clang++"), help="GCC/Clang C++ compiler")
    parser.add_argument("--source", type=Path, default=ROOT / "gpu/vk/vk_replay.cpp",
                        help="Public vk_replay.cpp override for an original-source negative control")
    parser.add_argument("--case", action="append", choices=CASES)
    args = parser.parse_args()
    cxx = shutil.which(args.cxx)
    if not cxx:
        raise SystemExit("C++ compiler not found: " + args.cxx)
    actual = actual_block(args.source.read_text(encoding="utf-8"))
    flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 0
    env = dict(os.environ)
    env["PATH"] = str(Path(cxx).parent) + os.pathsep + env.get("PATH", "")
    with tempfile.TemporaryDirectory(prefix="hookshot-frame-wait-") as folder:
        tmp = Path(folder)
        (tmp / "frame_wait_actual.inc").write_text(actual + "\n", encoding="utf-8")
        exe = tmp / ("frame_wait.exe" if os.name == "nt" else "frame_wait")
        command = [cxx, "-std=c++20", "-O0", "-Wall", "-Wextra", "-Werror", "-D_CRT_SECURE_NO_WARNINGS", "-I" + str(tmp),
                   str(ROOT / "tests/frame_wait_bounds_test.cpp"), "-o", str(exe)]
        result = subprocess.run(command, cwd=tmp, env=env, capture_output=True, text=True, timeout=60,
                                creationflags=flags)
        if result.returncode:
            print(result.stdout + result.stderr)
            return result.returncode
        failed = 0
        for case in args.case or CASES:
            # The actual initializer is static/read-once: every input gets a fresh process.
            result = subprocess.run([str(exe), case], cwd=tmp, env=env, capture_output=True, text=True,
                                    timeout=10, creationflags=flags)
            print((result.stdout + result.stderr).strip())
            failed += result.returncode != 0
        print("frame wait bounds: %d cases, %d failed" % (len(args.case or CASES), failed))
        return int(failed != 0)


if __name__ == "__main__":
    raise SystemExit(main())
