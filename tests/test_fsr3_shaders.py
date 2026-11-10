"""The checked-in FSR 3.1 pass shaders still match the FidelityFX SDK sources they came from.

gpu/vk/shaders/fsr3_*_comp_spv.h are generated from third_party/fidelityfx-sdk by
scripts/fsr3_shaders.py and checked in like every other shader here, so a clone builds without
glslang. That only stays true if the headers and their sources cannot drift apart, which is what
this check is for: it recompiles every variant and compares. It also validates each module, so a
pass that compiles but is not valid SPIR-V is caught here rather than on a device.

python -I -B tests/test_fsr3_shaders.py [--glslang glslangValidator] [--spirv-val spirv-val]
"""
import argparse
import subprocess
import sys
from pathlib import Path

RUN_ALL_ARGS = ["--glslang", "{glslang}", "--spirv-val", "{spirv_val}"]
# (glslang: a Linux runner package. The headers it checks are SPIR-V, the same on every platform)
RUN_ALL_SKIP = {"windows": "needs glslang: checked on Linux"}

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--glslang")
    p.add_argument("--spirv-val")
    a = p.parse_args()
    cmd = [sys.executable, "-I", "-B", str(ROOT / "scripts/fsr3_shaders.py"), "--check"]
    if a.glslang:
        cmd += ["--glslang", a.glslang]
    if a.spirv_val:
        cmd += ["--spirv-val", a.spirv_val]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
