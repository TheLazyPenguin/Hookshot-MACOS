"""A compute program's local memory size is read from its NVN2 control section (+0x68, bytes a thread).

It was never read: the Env gave compute programs 0, the SPIR-V back end then declared no local array, and the first
local load of a compute program that spills (LDL/STL) aborted the game in Sirit's OpAccessChain (EmitLoadLocal). Two of
OoT's largest compute programs (0xd80 bytes a thread; +0x50 holds the same times 32) reached it once they lowered.
python -I -B tests/test_compute_local_memory.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / "gpu" / "vk" / "vk_shader.cpp").read_text(encoding="utf-8")
fail = []
if "uint32_t local_memory = 0;" not in src.split("struct Code {", 1)[1].split("bool ok = false;", 1)[0]:
    fail.append("Code has no local_memory field")
compute = re.search(r"if \(!graphics\) \{(.*?)\n    \}", src, re.S)
if not compute or "std::memcpy(&c.local_memory, ctl + 0x68, 4);" not in compute.group(1):
    fail.append("parse_code does not read the compute local memory size from ctl + 0x68")
env = src.split("class Env final", 1)[1].split("u64 ReadInstruction", 1)[0]
if not re.search(r"else \{\s*local_memory = nvn\.local_memory;", env):
    fail.append("the Env does not give a compute program its control section's local memory")
if compute and "* 32 != warp_local" not in compute.group(1):
    fail.append("the size is not checked against +0x50 (a warp's)")
if fail:
    print("FAIL: " + "; ".join(fail))
    sys.exit(1)
print("PASS: compute programs get their control section's local memory size")
