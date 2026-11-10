"""code_hot.c in pieces that compile side by side: 83 MB in one file took 79 minutes on one core, and every full build waited for it.

    python -I nx2/split_hot.py [gen folder] [pieces, default 8]

Functions that call each other stay together, heaviest calls first, so what used to inline still can. The pieces cost about the
same to compile (chunks.fn_cost). code_hot.c stays as it was, renamed code_hot.c.whole, and build.py compiles code_hot_*.c at the
hot flags. A profile from the whole file fits the pieces: its counters go by function name and shape.
"""
import collections
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # (python -I leaves the script folder off)
import kit  # noqa: E402,F401  (a64-kit on the path, for chunks)
import chunks  # noqa: E402
import lifted_c  # noqa: E402

HEAD = lifted_c.HEAD
CALL = re.compile(r"\b(f_[0-9a-f]{8})\(c\)")


def split(gen, pieces):
    path = os.path.join(gen, "code_hot.c")
    whole = path + ".whole"
    if os.path.exists(path):
        os.replace(path, whole)
    for old in glob.glob(os.path.join(glob.escape(gen), "code_hot_*.c")):
        os.remove(old)
    with open(whole, encoding="utf-8", newline="") as f:
        text = f.read()
    marks = list(HEAD.finditer(text))
    if not marks:
        raise SystemExit("split_hot: no functions in %s" % whole)
    preamble = text[:marks[0].start()]
    bodies = {m.group(1): text[m.start():(marks[i + 1].start() if i + 1 < len(marks) else len(text))] for i, m in enumerate(marks)}

    # (groups joined along the calls: small callees first, those are what the optimiser inlines)
    limit = sum(len(b) for b in bodies.values()) * 1.1 / pieces
    parent = {f: f for f in bodies}
    size = {f: len(b) for f, b in bodies.items()}

    def root(f):
        while parent[f] != f:
            parent[f] = parent[parent[f]]
            f = parent[f]
        return f
    edges = collections.Counter()
    for f, b in bodies.items():
        for callee in CALL.findall(b):
            if callee in bodies and callee != f:
                edges[(f, callee)] += 1
    for (f, callee), n in sorted(edges.items(), key=lambda e: (len(bodies[e[0][1]]) / e[1], e[0])):
        a, b = root(f), root(callee)
        if a != b and size[a] + size[b] <= limit:
            parent[b] = a
            size[a] += size[b]

    groups = collections.defaultdict(list)
    for f in bodies:
        groups[root(f)].append(f)
    # (the groups dealt out by their compile cost, not their size: a piece's time goes with the square of its functions' sizes, and by
    # size one piece took 333 s and another 60)
    cost = {f: chunks.fn_cost(len(b)) for f, b in bodies.items()}
    bins = [[0, []] for _ in range(pieces)]
    for g in sorted(groups.values(), key=lambda g: (-sum(cost[f] for f in g), min(g))):
        b = min(bins, key=lambda x: x[0])
        b[0] += sum(cost[f] for f in g)
        b[1].extend(g)
    costs = {}
    for i, (c, names) in enumerate(bins):
        with open(os.path.join(gen, "code_hot_%d.c" % i), "w", encoding="utf-8", newline="") as f:
            f.write(preamble)
            for name in sorted(names):
                f.write(bodies[name])
        costs["code_hot_%d.c" % i] = len(preamble) + c
        print("split_hot: piece %d: %d functions, %d MB, cost %d MB" % (i, len(names), sum(len(bodies[f]) for f in names) >> 20, c >> 20))
    chunks.write_costs(gen, costs)
    kept = sum(n for (f, c), n in edges.items() if root(f) == root(c))
    print("split_hot: %d of %d calls stay in one group" % (kept, sum(edges.values())))


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    split(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "..", "work", "sa", "gen"), int(sys.argv[2]) if len(sys.argv) > 2 else 8)
