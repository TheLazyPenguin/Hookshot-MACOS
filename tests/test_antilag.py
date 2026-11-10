"""AMD Anti-Lag 2 (gpu/vk/vk_antilag.cpp): compiles its actual frame calls against the Vulkan headers with a recording
vkAntiLagUpdateAMD, and checks that the device and the present path call them. No GPU or driver required.

python -I -B tests/test_antilag.py --headers <Vulkan-Headers/include> [--cxx g++]
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}", "--headers", "{vulkan_headers}"]

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--headers", type=Path, required=True)
p.add_argument("--cxx", default="g++")
a = p.parse_args()
source = (ROOT / "gpu" / "vk" / "vk_antilag.cpp").read_text(encoding="utf-8")


def block(text, marker):
    """From marker to the brace closing its first one"""
    start = text.index(marker)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


# the wiring: the device asks for the extension and its feature, the present gives the present stage before
# vkQueuePresentKHR, and the input stage comes after the present (with Reflex's sleep)
main = (ROOT / "gpu" / "vk" / "vk_main.cpp").read_text(encoding="utf-8")
for call in ("antilag_device_extensions(want, exts);", "antilag_device_features(tail);", "antilag_device_created();"):
    if call not in main:
        raise SystemExit("vk_main.cpp no longer calls " + call)
if main.index("antilag_device_features(tail);") > main.index("vkGetPhysicalDeviceFeatures2(dev.physical, &f);"):
    raise SystemExit("vk_main.cpp: Anti-Lag 2's feature joins the chain after the features were queried")
replay = (ROOT / "gpu" / "vk" / "vk_replay.cpp").read_text(encoding="utf-8")
# (present ahead, #1720: present_image's present is its end, present_out, which present_commit also runs)
present = block(replay, "static void present_out(uint32_t index, std::unique_lock<std::mutex>& qk) {")
if "antilag_present();" not in present or present.index("antilag_present();") > present.index("vkQueuePresentKHR("):
    raise SystemExit("present_out: Anti-Lag 2's present stage is not given before vkQueuePresentKHR")
if "reflex_sleep(); antilag_input();" not in block(replay, "void do_present("):
    raise SystemExit("do_present: Anti-Lag 2's input stage is not given after the present")

functions = "\n".join(block(source, m) + (";" if m.startswith("struct") else "") for m in (
    "struct AntiLag {", "AntiLag& al()", "void update(", "bool on()", "void stage(", "void antilag_present()",
    "void antilag_input()"))
fixture = r'''
#include <vulkan/vulkan_core.h>
#include <cstdio>
#include <mutex>
#include <vector>
struct {VkDevice device=VK_NULL_HANDLE;} dev;
bool fg=false;int want=1;
bool framegen_on(){return fg;}
bool wanted(){return want>0;}
template<class... T> void logf(const char*,T...){}
struct Call{VkAntiLagModeAMD mode;int stage;uint64_t frame;};
std::vector<Call> calls;
void VKAPI_CALL record(VkDevice,const VkAntiLagDataAMD* d){
    calls.push_back({d->mode,d->pPresentationInfo?(int)d->pPresentationInfo->stage:-1,
                     d->pPresentationInfo?d->pPresentationInfo->frameIndex:0});
}
''' + functions + r'''
#define CHECK(c) do{if(!(c)){std::printf("FAIL line %d: %s\n",__LINE__,#c);return 1;}}while(0)
int main(){
    // not available: nothing is ever called
    antilag_input();antilag_present();CHECK(calls.empty());
    al().ready=true;al().update=record;
    // a present before the first input stage gives nothing
    antilag_present();CHECK(calls.empty());
    // a frame: its input stage, then its present stage, with one index, mode On
    antilag_input();antilag_present();
    CHECK(calls.size()==2&&calls[0].stage==VK_ANTI_LAG_STAGE_INPUT_AMD&&calls[1].stage==VK_ANTI_LAG_STAGE_PRESENT_AMD);
    CHECK(calls[0].frame==calls[1].frame&&calls[0].mode==VK_ANTI_LAG_MODE_ON_AMD&&calls[1].mode==VK_ANTI_LAG_MODE_ON_AMD);
    antilag_input();CHECK(calls.size()==3&&calls[2].frame==calls[0].frame+1);
    // frame generation on: the driver told Off once, then nothing
    calls.clear();fg=true;antilag_input();antilag_present();antilag_input();
    CHECK(calls.size()==1&&calls[0].mode==VK_ANTI_LAG_MODE_OFF_AMD&&calls[0].stage==-1);
    // on again: the present waits for an input stage
    calls.clear();fg=false;antilag_present();CHECK(calls.empty());
    antilag_input();antilag_present();CHECK(calls.size()==2&&calls[1].stage==VK_ANTI_LAG_STAGE_PRESENT_AMD);
    // the row off: Off once, then nothing
    calls.clear();want=0;antilag_input();antilag_present();antilag_input();
    CHECK(calls.size()==1&&calls[0].mode==VK_ANTI_LAG_MODE_OFF_AMD);
    std::puts("PASS: Anti-Lag 2's stages in order with one index a frame, Off told once, nothing while off");
}
'''
with tempfile.TemporaryDirectory(prefix="antilag-") as tmp:
    cpp, exe = Path(tmp) / "fixture.cpp", Path(tmp) / "fixture.exe"
    cpp.write_text(fixture, encoding="utf-8")
    subprocess.run([a.cxx, "-std=c++20", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-missing-field-initializers",
                    "-pthread", "-I" + str(a.headers), str(cpp), "-o", str(exe)], check=True)
    raise SystemExit(subprocess.run([str(exe)]).returncode)
