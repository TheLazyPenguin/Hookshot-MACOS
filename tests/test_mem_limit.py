"""HOOKSHOT_MEM_LIMIT_GB, the builder's Build memory choice (nx2/build.py MemoryGate): compiles start by the sum of their needs against
that limit, whatever is free, above the same floor as without it, and without it the free-memory policy is what it was.

python -I -B tests/test_mem_limit.py
"""
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nx2"))
import build  # noqa: E402

NEED = 2000


def check(what, ok):
    if not ok:
        raise SystemExit("FAIL: " + what)


def gate_with(limit):
    if limit is None:
        os.environ.pop("HOOKSHOT_MEM_LIMIT_GB", None)
    else:
        os.environ["HOOKSHOT_MEM_LIMIT_GB"] = limit
    return build.MemoryGate()


def main():
    saved_env = os.environ.get("HOOKSHOT_MEM_LIMIT_GB")
    saved_need, saved_free = build.mem_need, build.free_mb
    build.mem_need = lambda src: NEED
    try:
        automatic = gate_with(None)
        check("automatic keeps the free-memory policy", automatic.limit is None)
        floor = max(1, min(4, (os.cpu_count() or 2) // 2)) if os.name == "nt" else 1
        check("automatic keeps its floor", automatic.floor == floor)
        for raw in ("", "many", "0", "-4", "nan", "inf", "-inf", "1e309"):
            check("%r is not a limit" % raw, gate_with(raw).limit is None)

        def no_free_reading():
            raise SystemExit("FAIL: a limit does not read the free memory")
        build.free_mb = no_free_reading

        gate = gate_with("6.5")
        check("6.5 GB in MB", gate.limit == 6656)
        check("a limit keeps automatic's floor", gate.floor == floor)
        check("the countdown expects what the limit holds", gate.expected(24) == max(floor, 4))
        check("the countdown expects the floor at the least", gate_with("1").expected(24) == floor)
        gate.floor = 1
        held = [gate.enter(s) for s in ("a", "b", "c")]
        check("three needs of 2 GB fit in 6.5 GB", len(gate.running) == 3)
        got = []
        t = threading.Thread(target=lambda: got.append(gate.enter("d")))
        t.start()
        time.sleep(1.5)
        check("the fourth waits", not got)
        gate.leave(held.pop())
        t.join(5)
        check("the fourth starts when one ends", len(got) == 1)
        for lease in held + got:
            gate.leave(lease)
        check("nothing left running", not gate.running)

        small = gate_with("1")
        under = [small.enter(s) for s in "efgh"[:floor]]
        check("the floor's compiles start over the limit", len(small.running) == floor)
        for lease in under:
            small.leave(lease)
    finally:
        build.mem_need, build.free_mb = saved_need, saved_free
        if saved_env is None:
            os.environ.pop("HOOKSHOT_MEM_LIMIT_GB", None)
        else:
            os.environ["HOOKSHOT_MEM_LIMIT_GB"] = saved_env
    print("ok")


if __name__ == "__main__":
    main()
