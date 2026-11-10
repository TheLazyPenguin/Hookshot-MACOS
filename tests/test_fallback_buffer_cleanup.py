"""Authored failure injection against actual fallback buffer initialization; no Vulkan/game required."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]
CASES = ("initial_allocation_failure", "payload_allocation_failure", "records_address_zero",
         "records_only_address_zero", "payload_address_zero", "records_only_success", "task_success",
         "invalid_program", "program_isolation")


def block(source, signature, semicolon=False):
    start = source.index(signature)
    first = source.index("{", start)
    depth = 1
    at = first + 1
    while depth:
        if source[at] == "{":
            depth += 1
        elif source[at] == "}":
            depth -= 1
        at += 1
    if semicolon:
        assert source[at] == ";"
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
    source = args.source.read_text(encoding="utf-8")
    tls_start = source.index("struct TlsOwned {")
    tls_macro = source.index("#define TLS_OBJECT(", tls_start)
    tls_end = source.index("\n\n", tls_macro)
    actual = "\n\n".join((source[tls_start:tls_end], block(source, "struct FallbackBuffers {", True),
        next(line for line in source.splitlines() if line.startswith("TLS_OBJECT(fallback_buffers,")),
        block(source, "uint64_t fallback_buffer_address("), block(source, "bool fallback_buffers_of(")))
    flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 0
    env = dict(os.environ)
    env["PATH"] = str(Path(cxx).parent) + os.pathsep + env.get("PATH", "")
    with tempfile.TemporaryDirectory(prefix="hookshot-fallback-init-") as folder:
        tmp = Path(folder)
        (tmp / "fallback_actual.inc").write_text(actual + "\n", encoding="utf-8")
        exe = tmp / ("fallback.exe" if os.name == "nt" else "fallback")
        command = [cxx, "-std=c++20", "-O0", "-Wall", "-Wextra", "-Werror", "-I" + str(tmp),
                   str(ROOT / "tests/fallback_buffer_cleanup_test.cpp"), "-o", str(exe)]
        result = subprocess.run(command, cwd=tmp, env=env, capture_output=True, text=True, timeout=60,
                                creationflags=flags)
        if result.returncode:
            print(result.stdout + result.stderr)
            return result.returncode
        failed = 0
        for case in args.case or CASES:
            result = subprocess.run([str(exe), case], cwd=tmp, env=env, capture_output=True, text=True,
                                    timeout=10, creationflags=flags)
            print((result.stdout + result.stderr).strip())
            failed += result.returncode != 0
        print("fallback initialization: %d cases, %d failed" % (len(args.case or CASES), failed))
        return int(failed != 0)


if __name__ == "__main__":
    raise SystemExit(main())
