"""Run production capture reads against separate device bytes and a stale CPU cache."""
import argparse
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}", "--headers", "{vulkan_headers}"]

ROOT = Path(__file__).resolve().parents[1]


def block(source, marker):
    start = source.index(marker)
    at = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[at] == "{") - (source[at] == "}")
        at += 1
    return source[start:at]


def producer(source, marker, end):
    at = source.index(marker)
    start = source.rfind("const VkBufferImageCopy c", 0, at)
    return source[start:source.index(end, at)]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default="g++")
    p.add_argument("--headers", type=Path, required=True)
    p.add_argument("--source", type=Path, default=ROOT)
    p.add_argument("--phase", choices=["all", "normal", "owned", "made", "log"], default="all")
    p.add_argument("--visibility", choices=["all", "implicit", "explicit"], default="all")
    p.add_argument("--cache", choices=["all", "coherent", "noncoherent"], default="all")
    a = p.parse_args()
    source = (a.source / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    start = source.index("        auto take = [&](uint64_t at_value, int64_t at_present) {")
    end = source.index("            // (RX_VK_DUMP_BLACK", start)
    take = source[start:end] + "\n(void)at_present; return px; };\n"
    helper_start = source.index("std::shared_ptr<std::vector<uint8_t>> shot_pixels(")
    helper_end = source.index("void do_present(", helper_start)
    helper = source[helper_start:helper_end]
    start = source.index("        if (shot && made_src && made_map) {")
    end = source.index("        } else if (shot)", start)
    made = source[start:end] + "\n}\n"
    start = source.index("void framelog_collect(int slot) {")
    end = source.index("    {   // (a picture blown out", start)
    collect = source[start:end] + "\ncaptured = std::move(rec); }\n"
    call = source.index("vkWaitForFences(dev.device, 1, &f.done, VK_TRUE, UINT64_MAX)", source.index("void present_image("))
    start = source.rfind("\n", 0, call) + 1
    end = source.index("    uint32_t index = 0;", start)
    fence = source[start:end]
    host = block(source, "void capture_host_read_barrier(") if "void capture_host_read_barrier(" in source else ""
    normal_copy = producer(source, "vkCmdCopyImageToBuffer(r.cmd, shot_image,", "\n            }")
    made_copy = producer(source, "vkCmdCopyImageToBuffer(r.cmd, made_image,", "\n            }")
    log_copy = producer(source, "vkCmdCopyImageToBuffer(f.cmd, log_image,", "        l.used =")
    template = (ROOT / "tests/capture_readback_visibility_test.cpp").read_text(encoding="utf-8")
    fixture = template.replace("/* SHOT_PIXELS */", helper).replace("/* TAKE */", take).replace("/* MADE */", made).replace("/* COLLECT */", collect).replace("/* FENCE */", fence)
    fixture = fixture.replace("/* HOST_BARRIER */", host).replace("/* NORMAL_COPY */", normal_copy).replace("/* MADE_COPY */", made_copy).replace("/* LOG_COPY */", log_copy)
    with tempfile.TemporaryDirectory(prefix="capture-visibility-") as temp:
        cpp, exe = Path(temp) / "fixture.cpp", Path(temp) / "fixture.exe"
        cpp.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I" + str(a.headers),
                        str(cpp), "-o", str(exe)], check=True)
        for phase in (["normal", "owned", "made", "log"] if a.phase == "all" else [a.phase]):
            for cache in (["noncoherent", "coherent"] if a.cache == "all" else [a.cache]):
                for visibility in (["implicit", "explicit"] if a.visibility == "all" else [a.visibility]):
                    subprocess.run([str(exe), phase, cache, visibility], check=True, timeout=30)


if __name__ == "__main__":
    main()
