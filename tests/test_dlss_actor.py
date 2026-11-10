"""NVIDIA DLSS's actor motion (gpu/vk/vk_dlss.cpp, gpu/vk/dlss_actor.h): the CPU side's draw names and index addresses
(tests/test_dlss_actor.cpp), the push constants of shaders/dlss_actor.vert and .frag against dlss_actor::Push, and the
SPIR-V headers of the DLSS shaders made from their sources as they are now (when glslangValidator is here). No game or GPU.

python -I -B tests/test_dlss_actor.py [--cxx g++]
"""
import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHADERS = ROOT / "gpu" / "vk" / "shaders"


def fields(text, start, end):
    """The field names of a block: uint a, b[2]; -> ['a', 'b[2]']"""
    body = text[text.index(start) + len(start):]
    body = body[:body.index(end)]
    body = re.sub(r"//[^\n]*", "", body)
    out = []
    for decl in body.split(";"):
        decl = decl.strip()
        if not decl:
            continue
        names = re.sub(r"^\s*(uint64_t|uint32_t|int32_t|uint|int)\s+", "", decl)
        out += [n.strip() for n in names.split(",")]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    header = (ROOT / "gpu" / "vk" / "dlss_actor.h").read_text(encoding="utf-8")
    want = fields(header, "struct Push {", "};")
    if len(want) != 16:
        raise SystemExit("dlss_actor::Push: %d fields read: %s" % (len(want), want))
    for name in ("dlss_actor.vert", "dlss_actor.frag"):
        got = fields((SHADERS / name).read_text(encoding="utf-8"), "uniform P {", "} pc;")
        if got != want:
            raise SystemExit("%s: its push constants %s are not dlss_actor::Push's %s" % (name, got, want))
    chain = (ROOT / "gpu" / "vk" / "vk_temporal.cpp").read_text(encoding="utf-8")
    if "using ActorPush = dlss_actor::Push;" not in chain or "dlss_actor::index_start(" not in chain:
        raise SystemExit("vk_temporal.cpp does not use dlss_actor.h")
    glslang = shutil.which("glslangValidator")
    with tempfile.TemporaryDirectory(prefix="dlss-actor-") as tmp:
        if glslang:
            for src in ("dlss_actor.vert", "dlss_actor.frag", "dlss_prep.comp", "dlss_out.comp"):
                var = src.replace(".", "_").upper() + "_SPV"
                out = Path(tmp) / (src.replace(".", "_") + "_spv.h")
                subprocess.run([glslang, "-V", "--target-env", "vulkan1.3", "--vn", var, "-o", str(out), str(SHADERS / src)],
                               check=True, capture_output=True)
                words = lambda t: re.findall(r"0x[0-9a-f]{8}", t)
                if words(out.read_text()) != words((SHADERS / out.name).read_text()):
                    raise SystemExit("shaders/%s is not made from %s as it is now (glslangValidator -V --target-env vulkan1.3 "
                                     "--vn %s -o %s %s)" % (out.name, src, var, out.name, src))
        else:
            print("glslangValidator not found: the SPIR-V headers not checked")
        exe = Path(tmp) / "dlss-actor"
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", str(ROOT / "tests" / "test_dlss_actor.cpp"),
                        "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
