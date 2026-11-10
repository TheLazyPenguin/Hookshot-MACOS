"""A waited-for job still in the queue runs on the waiting thread at once (gpu/vk/vk_jobs.cpp jobs_wait; no game/GPU).

vk_jobs.cpp is compiled beside stand-ins for vk_internal.h and vk_draw.h (logging, the thread calls, ub_thread_off) and
run with every worker held in a job: the draw's pipeline job, queued behind them, must run on the thread that waits.
python -I -B tests/test_jobs_wait_runs_queued.py
"""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STUB_INTERNAL = """#pragma once
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <thread>
using HANDLE = void*;
constexpr int THREAD_PRIORITY_BELOW_NORMAL = -1;
inline HANDLE GetCurrentThread() { return nullptr; }
inline int SetThreadPriority(HANDLE, int) { return 1; }
inline long SetThreadDescription(HANDLE, const wchar_t*) { return 0; }
namespace mkwvk {
inline void logf(const char*, ...) {}
}
"""

STUB_DRAW = """#pragma once
namespace mkwvk {
inline void ub_thread_off() {}
}
"""


def check_source():
    """The pipeline and translation jobs a draw waits for are pushed with their flags, and jobs_wait still looks for them in the queue"""
    draw = (ROOT / "gpu/vk/vk_draw.cpp").read_text(encoding="utf-8")
    if "}, false, &e->ready," not in draw:
        raise SystemExit("graphics_pipeline's build job is pushed without its ready flag")
    shader = (ROOT / "gpu/vk/vk_shader.cpp").read_text(encoding="utf-8")
    if shader.count("&raw->ready,") < 2:
        raise SystemExit("a graphics or mesh translation job is pushed without its ready flag")
    jobs = (ROOT / "gpu/vk/vk_jobs.cpp").read_text(encoding="utf-8")
    wait = jobs[jobs.index("void jobs_wait("):]
    wait = wait[:wait.index("\n}\n")]
    if "it->flag == &flag" not in wait or 'getenv("RX_VK_JOB_STEAL")' not in wait:
        raise SystemExit("jobs_wait no longer runs a queued job it waits for")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    check_source()
    with tempfile.TemporaryDirectory(prefix="jobs-wait-") as tmp:
        tmp = Path(tmp)
        for name in ("vk_jobs.cpp", "vk_jobs.h"):
            shutil.copy(ROOT / "gpu/vk" / name, tmp / name)
        (tmp / "vk_internal.h").write_text(STUB_INTERNAL, encoding="utf-8")
        (tmp / "vk_draw.h").write_text(STUB_DRAW, encoding="utf-8")
        exe = tmp / "jobs-wait"
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-pthread", "-I", str(tmp),
                        str(tmp / "vk_jobs.cpp"), str(ROOT / "tests/test_jobs_wait_runs_queued.cpp"), "-o", str(exe)],
                       check=True)
        subprocess.run([str(exe)], check=True, timeout=60)


if __name__ == "__main__":
    main()
