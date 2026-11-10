"""Hot lifted functions from an all-thread sample (HOS_SAMPLE_ALL, scripts/crit.py): for each sample of a game thread
running in hookshot.exe (on Linux hookshot), the innermost lifted function (f_...) is charged. Writes the functions that make up the
first <share> of those samples, hottest first, one a line, for the lift's A64_HOT_FUNCS (their FP ops call the
helpers' inline fast paths; with A64_HOT_CHUNK=1 they are compiled together in code_hot.c).

    python -I scripts/hotlist.py work/runs/<run>_all.txt <out> [share 0.85] [max 1500]
"""
import bisect, collections, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prof  # noqa: E402

maps = prof.load_symbols()
game = next((m for m in prof.GAME_MODS if m in maps), None)
if not game:
    sys.exit("no hookshot.map (Windows) or hookshot binary (Linux) in %s: set RX_MAPS" % os.environ.get("RX_MAPS", prof.BUILD))
addrs, names = maps[game]
share = float(sys.argv[3]) if len(sys.argv) > 3 else 0.85
cap = int(sys.argv[4]) if len(sys.argv) > 4 else 1500
c = collections.Counter()
total = 0
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    head, _, st = line.rstrip("\n").partition("|")
    if not st or head.split(" ", 1)[-1].startswith("mkw_vk"):
        continue
    frames = st.split(";")
    if not frames[0].startswith(game + "+"):
        continue
    for f in frames:
        mod, _, off = f.rpartition("+")
        if mod != game:
            continue
        i = bisect.bisect_right(addrs, int(off, 16)) - 1
        n = names[i] if i >= 0 else ""
        if n.startswith("f_"):
            c[n] += 1
            total += 1
            break
out, acc = [], 0
for n, k in c.most_common():
    if acc >= share * total or len(out) >= cap:
        break
    out.append(n)
    acc += k
# (the game's Zstd decoder: the job loop's f_80115bf0 -> f_80115c80 tree. It runs while areas load and stream, which a play
# profile seldom samples, so it fell to the cold -O1 chunks. At the hot flags a whole decode takes 16% less time and the
# code is no bigger; the functions match Unicorn on every register and written page either way. Listed whatever the profile says)
ZSTD_DECODER = ("f_80115c80 f_80109790 f_80113880 f_80116490 f_801099a0 f_8010b160 f_8010ffc0 f_801102e0 f_80110860 "
                "f_801117a0 f_80112880 f_80113080 f_801156e0 f_80115880 f_8010ad60 f_834ab610 f_834abda0 f_834ab4a0 "
                "f_834ac0b0 f_834ac110 f_834ac2a0 f_8572f040").split()
out += [n for n in ZSTD_DECODER if n not in out]
open(sys.argv[2], "w").write("".join(n + "\n" for n in out))
print("%d samples in %d functions; %d functions cover %.0f%%" % (total, len(c), len(out), 100.0 * acc / max(1, total)))
