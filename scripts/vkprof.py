"""The renderer's threads from an all-thread sample (host/mkw_glue.c HOS_SAMPLE_ALL): for the threads whose name starts
with a prefix (default mkw_vk), the share of samples running, and the functions by inclusive and self share of the
running samples (leaf in hookshot_vk.dll, hookshot.exe or the driver; on Linux hookshot_vk.so, hookshot or the driver).

    python -I scripts/vkprof.py work/runs/<run>_all.txt [top 40] [prefix mkw_vk]
    (RX_MAPS=<folder>: another build's linker maps, or on Linux the game folder)
"""
import bisect, collections, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prof  # noqa: E402

top = int(sys.argv[2]) if len(sys.argv) > 2 else 40
prefix = sys.argv[3] if len(sys.argv) > 3 else "mkw_vk"
maps = prof.load_symbols()
cache = {}


def name(f):
    if f in cache:
        return cache[f]
    mod, _, off = f.rpartition("+")
    r = mod
    if mod in maps:
        a, n = maps[mod]
        i = bisect.bisect_right(a, int(off, 16)) - 1
        if i >= 0:
            r = prof.module_name(mod) + ":" + prof.demangle(n[i])[:70]
    cache[f] = r
    return r


RUN = prof.RUN_MODS + ("nvoglv64.dll",)
DRIVERS = ("libnvidia-glcore.so", "libvulkan_radeon.so", "libvulkan_intel.so")   # (Linux: the driver's file has its version after .so)
seen, running = collections.Counter(), collections.Counter()
incl, self_ = collections.Counter(), collections.Counter()
nrun = 0
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    head, _, st = line.rstrip("\n").partition("|")
    th = head.split(" ", 1)[-1]
    if not st or not th.startswith(prefix):
        continue
    frames = st.split(";")
    seen[th] += 1
    leafmod = frames[0].rpartition("+")[0]
    if leafmod not in RUN and not leafmod.startswith(DRIVERS):
        continue
    running[th] += 1
    nrun += 1
    names = [name(f) for f in frames]
    self_[names[0]] += 1
    for n in set(names):
        incl[n] += 1
print("-- running share by thread")
for th in sorted(seen, key=lambda t: -running[t]):
    print("  %5.1f%%  %s (%d samples)" % (100.0 * running[th] / seen[th], th, seen[th]))
print("-- inclusive (share of %d running samples)" % nrun)
for k, c in incl.most_common(top):
    print("  %5.1f%%  %s" % (100.0 * c / max(1, nrun), k))
print("-- self")
for k, c in self_.most_common(top):
    print("  %5.1f%%  %s" % (100.0 * c / max(1, nrun), k))
