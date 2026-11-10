"""Actual MemoryGate/compile_one with authored children; no compiler, game or memory stress."""
import argparse
import ast
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "nx2/build.py"


def actual_build(source):
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names = {"MemoryGate", "compile_one", "mem_need", "mem_limit_mb"}
    nodes = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
    assert {node.name for node in nodes} == names
    scope = dict(os=os, math=math, threading=threading, time=time, COMPILER_MB=1500,
                 free_mb=lambda: 1000000, rss_mb=lambda process: 0)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), scope)
    return scope


class CompileGateTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.dict(os.environ, {"HOOKSHOT_MEM_RESERVE_GB": "1.5", "HOOKSHOT_MEM_LIMIT_GB": ""}))
        self.folder = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="mem-gate-leases-")))
        self.scope = actual_build(SOURCE)
        self.gate = self.scope["MemoryGate"]()
        self.gate.floor = 2
        self.cache = self.folder / "cache"
        self.cache.mkdir()
        self.src = str(self.folder / "shared.cpp")
        Path(self.src).write_text("// Authored input, never compiled.\n", encoding="ascii")
        self.jobs = [("authored-compiler", self.src, str(self.folder / (name + ".o")),
                      ["-DAUTHORED_" + name], b"headers") for name in ("A", "B")]
        self.keys = {job[2]: str(index + 1) * 40 for index, job in enumerate(self.jobs)}
        self.cached = []
        self.scope.update(GATE=self.gate, OBJ_CACHE=str(self.cache),
                          PLANNED={(job[1], job[2]): self.keys[job[2]] for job in self.jobs},
                          no_throttle=lambda handle: None,
                          cache_put=lambda obj, key: self.cached.append((obj, key)))

    def popen(self, factory):
        self.scope["subprocess"] = SimpleNamespace(Popen=factory, PIPE=subprocess.PIPE,
                                                  CompletedProcess=subprocess.CompletedProcess)

    def overlap(self, first_status):
        # Pause B after actual enter(), but before actual started(). Let A's actual
        # finally/leave() finish, then resume B: no timing-dependent sleeps.
        a_started, b_entered, release_a, release_b = (threading.Event() for _ in range(4))
        snapshots, mapped, results, errors = {}, {}, {}, {}
        gate = self.gate

        class Child:
            def __init__(child, args, **kwargs):
                child.args = args
                child.obj = args[-1]
                child.name = Path(child.obj).stem
                child.returncode = first_status if child.name == "A" else 0

            def __enter__(child):
                if child.name == "B":
                    b_entered.set()
                    if not release_b.wait(5):
                        raise TimeoutError("B was not released")
                return child

            def __exit__(child, *args):
                return False

            def communicate(child):
                with gate.cv:
                    mapped[child.name] = sum(value[1] is child for value in gate.running.values())
                if child.name == "A":
                    a_started.set()
                    if not release_a.wait(5):
                        raise TimeoutError("A was not released")
                if child.returncode == 0:
                    Path(child.obj).write_bytes(("authored object " + child.name).encode("ascii"))
                return "", "authored compiler error" if child.returncode else ""

        def run(name, job):
            try:
                results[name] = self.scope["compile_one"](job)
            except BaseException as error:
                errors[name] = type(error).__name__

        self.popen(Child)
        a = threading.Thread(target=run, args=("A", self.jobs[0]), daemon=True)
        b = threading.Thread(target=run, args=("B", self.jobs[1]), daemon=True)
        a.start()
        try:
            self.assertTrue(a_started.wait(5), "A did not reach communicate")
            b.start()
            self.assertTrue(b_entered.wait(5), "B did not enter its reservation")
            with gate.cv:
                snapshots["both_reserved"] = len(gate.running)
            release_a.set()
            a.join(5)
            self.assertFalse(a.is_alive(), "A did not finish")
            with gate.cv:
                snapshots["after_a_left"] = len(gate.running)
            release_b.set()
            b.join(5)
            self.assertFalse(b.is_alive(), "B did not finish")
        finally:
            release_a.set()
            release_b.set()
            a.join(5)
            if b.ident is not None:
                b.join(5)
        facts = dict(first_status=first_status, reservations=snapshots, mappings=mapped, errors=errors,
                     remaining=len(gate.running))
        print("duplicate-source observation: " + json.dumps(facts, sort_keys=True), flush=True)
        self.assertEqual(errors, {}, facts)
        self.assertEqual(snapshots, {"both_reserved": 2, "after_a_left": 1}, facts)
        self.assertEqual(mapped, {"A": 1, "B": 1}, facts)
        self.assertEqual(gate.running, {}, facts)
        self.assertEqual(results["A"][0], self.src)
        self.assertEqual(results["B"], (self.src, results["B"][1], None))
        self.assertEqual(results["A"][2], "authored compiler error" if first_status else None)
        successful = self.jobs if first_status == 0 else self.jobs[1:]
        self.assertCountEqual(self.cached, [(job[2], self.keys[job[2]]) for job in successful])
        for job in self.jobs:
            stamp = Path(job[2] + ".sha1")
            if job in successful:
                self.assertEqual(stamp.read_text(), self.keys[job[2]])
            else:
                self.assertFalse(stamp.exists())

    def test_duplicate_source_jobs_keep_separate_reservations(self):
        self.overlap(0)

    def test_compile_error_releases_only_its_own_reservation(self):
        self.overlap(17)

    def test_popen_error_releases_reservation(self):
        def failed(*args, **kwargs):
            raise OSError("authored process creation failure")
        self.popen(failed)
        with self.assertRaisesRegex(OSError, "authored process creation failure"):
            self.scope["compile_one"](self.jobs[0])
        self.assertEqual(self.gate.running, {})
        self.assertEqual(self.cached, [])

    def test_existing_object_and_cache_hit_bypass_gate(self):
        job = self.jobs[0]
        obj, key = Path(job[2]), self.keys[job[2]]
        self.popen(lambda *args, **kwargs: self.fail("cache hit launched a child"))
        for source in ("object", "cache"):
            with self.subTest(source=source):
                if source == "object":
                    obj.write_bytes(b"authored existing object")
                    Path(str(obj) + ".sha1").write_text(key)
                else:
                    obj.unlink()
                    Path(str(obj) + ".sha1").unlink()
                    (self.cache / (key + ".o")).write_bytes(b"authored cached object")
                with mock.patch.object(self.gate, "enter", wraps=self.gate.enter) as entered:
                    self.assertEqual(self.scope["compile_one"](job), (self.src, 0.0, None))
                    entered.assert_not_called()
                self.assertEqual(self.gate.running, {})
                self.assertEqual(self.cached, [])
                self.assertEqual(Path(str(obj) + ".sha1").read_text(), key)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    args, remaining = parser.parse_known_args()
    SOURCE = args.source.resolve()
    unittest.main(argv=[__file__, *remaining])
