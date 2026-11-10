"""Defensive failure injection against actual mesh argument initialization; no Vulkan/game required."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]
CASES = ("allocation_failure", "allocation_failure_outputs", "null_mapping",
         "zero_address", "success_reuse")


def actual_initializer(source):
    start = source.index("constexpr uint32_t kMeshArgs =")
    first = source.index("{", source.index("bool mesh_args_ready()", start))
    depth, at = 1, first + 1
    while depth:
        if source[at] == "{":
            depth += 1
        elif source[at] == "}":
            depth -= 1
        at += 1
    return source[start:at]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default=os.environ.get("CXX", "clang++"), help="GCC/Clang C++ compiler")
    parser.add_argument("--source", type=Path, default=ROOT / "gpu/vk/vk_draw.cpp",
                        help="Public vk_draw.cpp override for an original-source negative control")
    parser.add_argument("--case", action="append", choices=CASES)
    args = parser.parse_args()
    cxx = shutil.which(args.cxx)
    if not cxx:
        raise SystemExit("C++ compiler not found: " + args.cxx)
    actual = actual_initializer(args.source.read_text(encoding="utf-8"))
    flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 0
    env = dict(os.environ)
    env["PATH"] = str(Path(cxx).parent) + os.pathsep + env.get("PATH", "")
    with tempfile.TemporaryDirectory(prefix="hookshot-mesh-args-") as folder:
        tmp = Path(folder)
        (tmp / "mesh_args_actual.inc").write_text(actual + "\n", encoding="utf-8")
        exe = tmp / ("mesh_args.exe" if os.name == "nt" else "mesh_args")
        command = [cxx, "-std=c++20", "-O0", "-Wall", "-Wextra", "-Werror", "-I" + str(tmp),
                   str(ROOT / "tests/mesh_args_cleanup_test.cpp"), "-o", str(exe)]
        result = subprocess.run(command, cwd=tmp, env=env, capture_output=True, text=True, timeout=60,
                                creationflags=flags)
        if result.returncode:
            print(result.stdout + result.stderr)
            return result.returncode
        failed = 0
        for case in args.case or CASES:
            # The production function caches its result forever: each case gets a fresh process.
            result = subprocess.run([str(exe), case], cwd=tmp, env=env, capture_output=True, text=True,
                                    timeout=10, creationflags=flags)
            print((result.stdout + result.stderr).strip())
            failed += result.returncode != 0
        print("mesh argument initialization: %d cases, %d failed" % (len(args.case or CASES), failed))
        return int(failed != 0)


if __name__ == "__main__":
    raise SystemExit(main())
