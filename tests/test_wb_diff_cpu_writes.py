"""The write-back diff's shadows hear of every CPU write of guest memory (gpu/vk/vk_memory.cpp, "the write-back's diff").

A shadow page the diff knows must equal guest memory: a CPU write it never heard of left the CPU's value where the whole copy
wrote the GPU's, whenever the GPU's result equalled the shadow's old word (PR 1109's review: an in-stream clear of a counter the
game's conditions read, counted to last frame's value again, stayed cleared). These checks read the sources:

- every host->gpu_write in gpu/vk is guest_cpu_write's own, or marked "shadows hear of" with a guest_cpu_wrote after it
- guest_cpu_write writes and reports; guest_cpu_wrote reports into the replay's list, which shadows_forget_written reads
- memory_collect_written reports every page it collects (the only report of the game's writes with RX_VK_CAPTURE=0)
- the in-stream clear (NOP_CLEAR_BUF) and the report words write through guest_cpu_write
- a written binding given the guest buffer of a mirrored pool forgets its pages (shadow_forget)

tests/test_wb_diff_stale_shadow.py runs the sequence itself.

python -I -B tests/test_wb_diff_cpu_writes.py
"""
from pathlib import Path
import re
import unittest

VK = Path(__file__).resolve().parents[1] / "gpu" / "vk"


def body(text, signature):
    """The braces' contents of the first function or block opening after `signature`"""
    start = text.index(signature)
    i = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[i] == "{") - (text[i] == "}")
        i += 1
    return text[start:i]


class ShadowReports(unittest.TestCase):
    def setUp(self):
        self.memory = (VK / "vk_memory.cpp").read_text(encoding="utf-8")
        self.replay = (VK / "vk_replay.cpp").read_text(encoding="utf-8")

    def test_every_raw_guest_write_is_reported(self):
        wrapper = body(self.memory, "int guest_cpu_write(")
        for path in sorted(VK.glob("*.cpp")):
            text = path.read_text(encoding="utf-8")
            for m in re.finditer(r"host->gpu_write\(", text):
                line_start = text.rfind("\n", 0, m.start()) + 1
                line = text[line_start:text.find("\n", m.start())]
                if path.name == "vk_memory.cpp" and wrapper.find(line.strip()) >= 0:
                    continue
                where = "%s:%d" % (path.name, text.count("\n", 0, m.start()) + 1)
                self.assertIn("shadows hear of", line, where + ": a CPU write of guest memory the write-back diff's shadows "
                              "never hear of; write it through guest_cpu_write")
                self.assertIn("guest_cpu_wrote(", text[m.start():m.start() + 4000], where + ": marked, but no guest_cpu_wrote after it")

    def test_the_wrapper_writes_and_reports(self):
        wrapper = body(self.memory, "int guest_cpu_write(")
        self.assertIn("host->gpu_write(", wrapper)
        self.assertIn("guest_cpu_wrote(", wrapper)
        reports = body(self.memory, "void guest_cpu_wrote(")
        self.assertIn("shadow_written_by_replay", reports)
        self.assertIn("host->gpu_guest(", reports)   # (by GPU address: each page's guest page)
        forget = body(self.memory, "void shadows_forget_written(")
        self.assertIn("shadow_written_by_replay", forget)
        self.assertIn("shadow_written_pages", forget)
        self.assertIn("shadow_written_collected_list", forget)

    def test_the_collection_reports_every_page(self):
        collect = body(self.memory, "void memory_collect_written(")
        self.assertRegex(collect, r"shadow_written_collected\(pages, n\)")

    def test_a_written_binding_past_the_mirror_forgets_its_pages(self):
        bind = body(self.memory, "BufferRef gpu_buffer_bind(uint64_t gpu, uint64_t size, bool written) {")
        direct = bind[bind.index("p->mstate == Pool::MIRROR_REFUSED) {"):]
        direct = direct[:direct.index("return remember(")]
        self.assertIn("if (written) shadow_forget(*p, off,", direct)   # (the GPU writes guest memory itself there)

    def test_the_replays_own_writes_go_through_the_wrapper(self):
        clear = body(self.replay, "case NOP_CLEAR_BUF:")
        self.assertIn("guest_cpu_write(c0.dst, words, ", clear)   # (the in-stream clear of the conditions' counters)
        self.assertNotIn("host->gpu_write(", clear)
        self.assertRegex(self.replay, r"guest_cpu_write\(c\.addr, rec, sizeof rec\)")   # (the report words)


if __name__ == "__main__":
    unittest.main()
