"""Run production present route/geometry diagnostics and bounded per-kind state tracking without a GPU."""
import argparse
from pathlib import Path
import os
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default="g++")
    p.add_argument("--source", type=Path, default=ROOT)
    a = p.parse_args()
    source = (a.source / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    begin = source.index("void present_image(")
    marker = "    const PresentAspect aspect{" if "    const PresentAspect aspect{" in source[begin:] else "    const bool preserve_stretch ="
    start = source.index(marker, begin)
    end = source.index("    if (src && framelog_on())", start)
    draw = source[start:end]
    trace = ""
    if "    // Geometry trace:" in source[end:]:
        start = source.index("    // Geometry trace:", end)
        trace = source[start:source.index("    menu_record(", start)]
    fixture = (ROOT / "tests/present_geometry_trace_test.cpp").read_text(encoding="utf-8")
    fixture = fixture.replace("/* ACTUAL_DRAW */", draw).replace("/* ACTUAL_TRACE */", trace)
    with tempfile.TemporaryDirectory(prefix="present-geometry-trace-") as temp:
        cpp, exe = Path(temp) / "fixture.cpp", Path(temp) / "fixture.exe"
        cpp.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I" + str(a.source / "gpu/vk"),
                        str(cpp), "-o", str(exe)], check=True)
        for value in (None, "0", "1"):
            env = os.environ.copy()
            env.pop("RX_VK_PRESENT_LOG", None)
            if value is not None:
                env["RX_VK_PRESENT_LOG"] = value
            subprocess.run([str(exe), "1" if value == "1" else "0"], env=env, check=True, timeout=30)


if __name__ == "__main__":
    main()
