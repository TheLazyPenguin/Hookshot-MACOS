"""Run production PNG flash sampling and its cell/region detector without a GPU."""
import argparse
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=ROOT)
    p.add_argument("--cxx", default="g++")
    p.add_argument("--case", choices=["all", "constant", "partition", "detector"], default="all")
    a = p.parse_args()
    source = (a.source / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    start = source.index("                constexpr uint32_t W = 64, H = 36;")
    sampling = source[start:source.index("                static std::shared_ptr<std::vector<uint8_t>> sa, sb, pa, pb;", start)]
    start = source.index("                    static const int fl_diff =", start)
    detector = source[start:source.index("                    if (region_hits && flashes_left > 0)", start)]
    decision = source[source.index("if (((hits >= fl_cells", start):].split(" {", 1)[0]
    condition = decision[len("if ("):-1]
    template = (ROOT / "tests/flash_sampling_test.cpp").read_text(encoding="utf-8")
    fixture = template.replace("/* SAMPLING */", sampling).replace("/* DETECTOR */", detector).replace("/* DECISION */", condition)
    with tempfile.TemporaryDirectory(prefix="flash-sampling-") as temp:
        cpp, exe = Path(temp) / "fixture.cpp", Path(temp) / "fixture.exe"
        cpp.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++17", "-O1", str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe), a.case], check=True, timeout=40)


if __name__ == "__main__":
    main()
