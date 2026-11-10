"""Execute native presentation's actual Vulkan result-routing sites without a GPU.

The existing test_device_lost_exit.py checks the shared report-once/log-flush/exit
contract. This check injects device loss into each WSI call site, including both
present queues, and checks that execution cannot pass the loss unreported.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

RUN_ALL_ARGS = ['--cxx', '{cxx}']

ROOT = Path(__file__).resolve().parents[1]
CALLS = ("vkWaitForFences", "vkAcquireNextImageKHR", "vkResetFences", "vkResetCommandPool",
         "vkBeginCommandBuffer", "vkEndCommandBuffer", "vkQueueSubmit2", "vkQueuePresentKHR")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=ROOT)
    p.add_argument("--cxx", default="g++")
    a = p.parse_args()
    text = (a.source / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    present = text[text.index("void present_image("):]
    present = present[:present.index("\nnamespace {")]
    lines = present.splitlines()
    sites = []
    for call in CALLS:
        found = [i for i, line in enumerate(lines) if re.search(r"\b" + call + r"\(", line)]
        if len(found) != (2 if call == "vkQueuePresentKHR" else 1):
            raise SystemExit("FAIL: presentation call sites changed: " + call)
        for i in found:
            snippet = lines[i].strip()
            if "device_lost();" not in snippet:
                following = lines[i + 1:]
                if call == "vkQueuePresentKHR":
                    following = following[:following.index("    reflex_presented();")]
                else:
                    following = following[:1]
                snippet += "\n" + "\n".join(line for line in following
                                                  if line.strip() == "if (res == VK_ERROR_DEVICE_LOST) device_lost();")
            if "VkResult res =" not in snippet:
                snippet = "VkResult res = VK_SUCCESS; (void)res;\n" + snippet
            sites.append((call, snippet))

    fixture = r'''
#include <cstdint>
#include <cstdio>
using VkResult = int;
enum { VK_SUCCESS=0, VK_ERROR_DEVICE_LOST=-4, VK_TRUE=1, VK_NULL_HANDLE=0 };
struct { int device=1, queue=2, present_queue=3, swapchain=4; } dev;
struct { int done=5, acquired=6, pool=7, cmd=8; } f;
int bi=0, si=0, pi=0, index=0;
uint64_t acquire_timeout=UINT64_MAX;
int result=VK_SUCCESS, calls=0, reports=0, continued=0;
struct Lost {};
[[noreturn]] void device_lost() { ++reports; throw Lost{}; }
'''
    for call in CALLS:
        fixture += "template<class... A> VkResult " + call + "(A...) { ++calls; return result; }\n"
    for i, (_, snippet) in enumerate(sites):
        fixture += "void site_%d() {\n%s\n(void)res; ++continued;\n}\n" % (i, snippet)
    fixture += "int main() {\nint failed=0;\n"
    for i, (name, _) in enumerate(sites):
        for result in (0, -4, -1, 2, 1000001003, -1000001004):
            fixture += ("result=%d; calls=reports=continued=0; try { site_%d(); } catch (const Lost&) {}\n"
                        "if (calls!=1 || reports!=%d || continued!=%d) { "
                        "std::printf(\"FAIL: %s site%d result%%d reports%%d continued%%d\\n\",result,reports,continued); ++failed; }\n"
                        % (result, i, int(result == -4), int(result != -4), name, i))
    fixture += 'if (!failed) { std::puts("PASS: all nine native WSI sites route device loss before continuing; other results preserved"); }\nreturn failed ? 1 : 0;\n}\n'
    with tempfile.TemporaryDirectory(prefix="present-device-loss-") as temp:
        cpp, exe = Path(temp) / "fixture.cpp", Path(temp) / "fixture.exe"
        cpp.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=10)


if __name__ == "__main__":
    main()
