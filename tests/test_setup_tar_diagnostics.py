"""Exercise the actual setup process helper and tar-failure call site with authored inputs only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cc", "gcc"]

ROOT = Path(__file__).resolve().parents[1]
CASES = ("failure", "launch", "long", "success", "warning", "pipe_fallback", "inherit_fallback", "null_fallback", "empty", "high_exit", "query",
         "capture_error", "max_paths", "missing", "missing_max_paths", "child_exit_2")


def extract(source):
    marker = "static RunResult run_wait(" if "static RunResult run_wait(" in source else "static int run_wait("
    start = source.index(marker)
    end = source.index("\nstatic void mkdirs(", start)
    if marker.startswith("static RunResult"):
        start = source.rindex("typedef struct {", 0, start)
    call_start = source.index("            GetSystemDirectoryW(sys, MAX_PATH);")
    call_end = source.index('            if (strcmp(p->from, "-")', call_start)
    return source[start:end], source[call_start:call_end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="gcc")
    parser.add_argument("--source", type=Path, default=ROOT / "builder/setup/setup.c")
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    production = args.source.read_text(encoding="utf-8")
    helper, call = extract(production)
    template = (ROOT / "tests/setup_tar_diagnostics_test.c").read_text(encoding="utf-8")
    assert template.count("/* ACTUAL_HELPER */") == template.count("/* ACTUAL_CALL */") == 1
    code = template.replace("/* ACTUAL_HELPER */", helper).replace("/* ACTUAL_CALL */", call)
    priority = {"creationflags": (getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0))}
    rows = []
    with tempfile.TemporaryDirectory(prefix="hookshot-tar-diagnostics-") as temporary:
        folder = Path(temporary)
        source, executable = folder / "fixture.c", folder / "fixture.exe"
        source.write_text(code, encoding="utf-8")
        # Win32's incumbent {sizeof struct} initialization intentionally zeroes remaining fields.
        flags = ["-std=c11", "-O0", "-Wall", "-Wextra", "-Werror", "-Wno-missing-field-initializers", "-D_CRT_SECURE_NO_WARNINGS"]
        subprocess.run([args.cc, *flags, str(source), "-o", str(executable)], check=True, **priority)
        for case in CASES:
            result = subprocess.run([str(executable), case], capture_output=True, text=True, timeout=15, **priority)
            rows.append(dict(case=case, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
        if os.name == "nt":
            real = folder / "real-fixture.exe"
            subprocess.run([args.cc, *flags, "-DREAL_CHILD", str(source), "-o", str(real)], check=True, **priority)
            result = subprocess.run([str(real), str(folder), "missing"], capture_output=True, text=True, timeout=15, **priority)
            rows.append(dict(case="real_missing_executable", returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
            result = subprocess.run([str(real), str(folder)], capture_output=True, text=True, timeout=15, **priority)
            rows.append(dict(case="real_child_no_standard_handles", returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
    receipt = dict(source=str(args.source), source_sha256=hashlib.sha256(production.encode()).hexdigest(),
                   fixture_sha256=hashlib.sha256(template.encode()).hexdigest(), cases=rows,
                   passed=sum(row["returncode"] == 0 for row in rows), failed=sum(row["returncode"] != 0 for row in rows),
                   actual_helper_and_call_site_extracted=True, real_archive_or_symlink_used=False)
    if args.result:
        args.result.parent.mkdir(parents=True, exist_ok=True)
        with args.result.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2)
            stream.write("\n")
    for row in rows:
        print(("PASS " if row["returncode"] == 0 else "FAIL ") + row["case"])
        if row["returncode"] != 0:
            print((row["stdout"] + row["stderr"])[:2048])
    print(f"{receipt['passed']} passed, {receipt['failed']} failed")
    return bool(receipt["failed"])


if __name__ == "__main__":
    raise SystemExit(main())
