"""Compile real reprojection math and both upscalers' history decisions and reset sinks; no SDK or GPU."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]


def decision(text, signature):
    text = text[text.index(signature):]
    return text[re.search(r"\b(?:const )?bool reset =", text).start():
                text.index("    pc.jitter[0]")]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=ROOT)
    p.add_argument("--cxx", default="g++")
    a = p.parse_args()
    chain = (a.source / "gpu/vk/vk_temporal.cpp").read_text(encoding="utf-8")
    dlss = (a.source / "gpu/vk/vk_dlss.cpp").read_text(encoding="utf-8")
    fsr4 = (a.source / "gpu/vk/vk_fsr4.cpp").read_text(encoding="utf-8")
    fsr = (a.source / "gpu/vk/vk_fsr3_inputs.cpp").read_text(encoding="utf-8")
    fixture = (ROOT / "tests/temporal_history_test.cpp").read_text(encoding="utf-8")
    assert "engine.e->evaluate(cmd, f)" in chain, "the shared frame must reach the selected engine"
    chain_sink = re.search(r"f\.reset = [^;]+;", chain).group()
    dlss_sink = re.search(r"ep\.InReset = [^;]+;", dlss).group()
    fsr4_sink = re.search(r"d\.reset = [^;]+;", fsr4).group()
    fsr_sink = re.search(r"f\.reset = [^;]+;", fsr).group()
    for tag, value in [("/* CHAIN_POLICY */", decision(chain, "bool temporal_upscale(")),
                       ("/* FSR_POLICY */", decision(fsr, "bool prepare(")),
                       ("/* CHAIN_SINK */", chain_sink), ("/* DLSS_SINK */", dlss_sink),
                       ("/* FSR4_SINK */", fsr4_sink), ("/* FSR_SINK */", fsr_sink)]:
        fixture = fixture.replace(tag, value)
    with tempfile.TemporaryDirectory(prefix="temporal-history-") as folder:
        cpp, exe = Path(folder) / "fixture.cpp", Path(folder) / "fixture.exe"
        cpp.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
                        "-I" + str(a.source), str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=30)


if __name__ == "__main__":
    main()
