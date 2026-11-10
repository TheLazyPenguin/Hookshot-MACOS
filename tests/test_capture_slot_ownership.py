"""Execute the normal-shot producer/read/consume statements with a queued GPU model.

A pending frame2 can survive a non-shot frame3 while the GPU is behind. A new
frame4 copy reuses its slot. Both immediate and delayed completion are legal;
the pending capture must still receive frame2 bytes and metadata. No GPU/game.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]


def block(text, marker):
    start = text.index(marker)
    at = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[at] == "{") - (text[at] == "}")
        at += 1
    return text[start:at]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=ROOT)
    p.add_argument("--cxx", default="g++")
    a = p.parse_args()
    source = (a.source / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    present = source[source.index("void do_present("):]
    copy = next(line.strip() for line in present.splitlines() if "vkCmdCopyImageToBuffer(r.cmd, shot_image," in line)
    consume = next(line.strip() for line in present.splitlines() if "if (pending.on &&" in line and "completed()" in line)
    rearm = next(line.strip() for line in present.splitlines() if "pending = {true, value, presents" in line)
    read_at = present.index("auto take = [&]")
    read = present[read_at:present.index("// (RX_VK_DUMP_BLACK", read_at)]
    copy_at, submit_at, consume_at = present.index(copy), present.index("submit_recording(r);"), present.index(consume)
    assert copy_at < submit_at < read_at < consume_at
    state = "struct PendingShot { bool on=false; uint64_t value=0; int64_t presents=0; std::shared_ptr<std::vector<uint8_t>> pixels{}; };"
    helper = ""
    protect = ""
    if "struct PendingShot {" in source:
        state = block(source, "struct PendingShot {") + ";"
        helper = block(source, "std::shared_ptr<std::vector<uint8_t>> shot_pixels(")
    marker = "if (pending.on && (pending.presents & 1)"
    actions = [(copy_at, copy), (submit_at, "submit_recording(r);")]
    if marker in present:
        at = present.index(marker)
        assignment = "pending.pixels = shot_pixels(pending.value, pending.presents);"
        end = present.index(assignment, at) + len(assignment)
        protect = present[at:end].strip()
        assert at < read_at, "slot protection must occur in the producer, before the consumer"
        actions.append((at, protect))
    producer = "\n".join(text for _, text in sorted(actions))
    template = (ROOT / "tests/capture_slot_ownership_test.cpp").read_text(encoding="utf-8")
    fixture = template.replace("/* STATE */", state).replace("/* READ_HELPER */", helper)
    fixture = fixture.replace("/* TAKE */", read).replace("/* PRODUCER */", producer).replace("/* CONSUME */", consume).replace("/* REARM */", rearm)
    with tempfile.TemporaryDirectory(prefix="capture-slot-") as temp:
        cpp, exe = Path(temp) / "fixture.cpp", Path(temp) / "fixture.exe"
        cpp.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=20)


if __name__ == "__main__":
    main()
