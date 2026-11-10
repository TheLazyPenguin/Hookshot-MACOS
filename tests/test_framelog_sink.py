"""Execute frame-log startup rollback and a real CPU worker with controlled IO failures."""
import argparse
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}", "--headers", "{vulkan_headers}"]

ROOT = Path(__file__).resolve().parents[1]


def block(text, marker):
    start = text.index(marker)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=ROOT)
    p.add_argument("--headers", type=Path, required=True)
    p.add_argument("--cxx", default="g++")
    p.add_argument("--case")
    a = p.parse_args()
    source = (a.source / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    ready = block(source, "bool framelog_ready() {")
    # Only the thread factory is replaced; run the production startup/catch/rollback code.
    ready = ready.replace("std::thread(", "FakeThread(")
    drop = block(source, "void framelog_resources_drop() {") if "void framelog_resources_drop() {" in source else "void framelog_resources_drop() {}"
    if "void framelog_write(FILE* f) {" in source:
        writer = block(source, "void framelog_write(FILE* f) {")
    else:
        begin = ready.index("FakeThread([] {") + len("FakeThread([] {")
        end = ready.index("    }).detach();", begin)
        writer = "void framelog_write(FILE*) {" + ready[begin:end] + "\n}"
    if "void framelog_enqueue(std::vector<uint8_t> rec) {" in source:
        enqueue = block(source, "void framelog_enqueue(std::vector<uint8_t> rec) {")
    else:
        collect = block(source, "void framelog_collect(int slot) {")
        begin = collect.rindex("    std::lock_guard lk(log_mu);")
        enqueue = "void framelog_enqueue(std::vector<uint8_t> rec) {\n" + collect[begin:]
    fixture = (ROOT / "tests/framelog_sink_test.cpp").read_text(encoding="utf-8")
    fixture = fixture.replace("/* DROP */", drop).replace("/* WRITER */", writer).replace("/* ENQUEUE */", enqueue).replace("/* READY */", ready)
    cases = ["healthy", "image", "buffer0", "buffer1", "buffer2", "map0", "map1", "map2", "file", "thread",
             "write1", "write3", "flush1", "flush3", "queue"]
    with tempfile.TemporaryDirectory(prefix="framelog-sink-") as temp:
        cpp, exe = Path(temp) / "fixture.cpp", Path(temp) / "fixture.exe"
        cpp.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-missing-field-initializers",
                        "-pthread", "-I" + str(a.headers), str(cpp), "-o", str(exe)], check=True)
        for case in ([a.case] if a.case else cases):
            subprocess.run([str(exe), case], check=True, timeout=15)


if __name__ == "__main__":
    main()
