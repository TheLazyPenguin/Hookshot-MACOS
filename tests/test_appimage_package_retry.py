"""Execute the real AppImage package bootstrap with failing apt/PPA commands.

No network or package installation. The command stand-ins record ordering and
inject transient or persistent failures at each bootstrap stage under sh -e.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

# (Linux only)
RUN_ALL_SKIP = {"windows": "the AppImage package bootstrap is POSIX shell; exercised on Linux"}

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("update", "prerequisites", "ppa", "toolchain", "dependencies")
STUB = r'''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
name=Path(sys.argv[0]).name
if name=='sleep':stage='sleep'
elif name=='add-apt-repository':stage='ppa'
elif sys.argv[1]=='update':stage='update'
elif 'software-properties-common' in sys.argv:stage='prerequisites'
elif 'g++-13' in sys.argv:stage='toolchain'
elif 'libx11-dev' in sys.argv:stage='dependencies'
else:raise SystemExit('unexpected package command')
state=Path(os.environ['BOOTSTRAP_STATE'])
data=json.loads(state.read_text())
data['calls'].append({'stage':stage,'argv':sys.argv[1:]})
fail=stage==os.environ.get('BOOTSTRAP_FAIL_STAGE') and data['failures']<int(os.environ.get('BOOTSTRAP_FAIL_COUNT','0'))
if fail:data['failures']+=1
state.write_text(json.dumps(data))
raise SystemExit(100 if fail else 0)
'''


def bootstrap(root):
    source = (root / ".github/workflows/linux-appimage.yml").read_text(encoding="utf-8")
    start = source.index("      - name: System packages")
    start = source.index("        run: |\n", start) + len("        run: |\n")
    lines = []
    for line in source[start:].splitlines():
        if line and not line.startswith("          "):
            break
        lines.append(line[10:] if line else "")
    return "\n".join(lines) + "\n"


@unittest.skipIf(os.name == "nt", "POSIX AppImage package bootstrap")
class PackageRetry(unittest.TestCase):
    def run_bootstrap(self, stage="", failures=0):
        shell = shutil.which("sh")
        self.assertIsNotNone(shell)
        with tempfile.TemporaryDirectory(prefix="appimage-packages-") as temp:
            folder = Path(temp)
            tools = folder / "bin"
            tools.mkdir()
            for command in ("apt-get", "add-apt-repository", "sleep"):
                path = tools / command
                path.write_text(STUB, encoding="utf-8")
                path.chmod(0o755)
            state = folder / "state.json"
            state.write_text(json.dumps({"calls": [], "failures": 0}), encoding="utf-8")
            script = folder / "bootstrap.sh"
            script.write_text(bootstrap(ROOT), encoding="utf-8")
            env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"],
                       BOOTSTRAP_STATE=str(state), BOOTSTRAP_FAIL_STAGE=stage,
                       BOOTSTRAP_FAIL_COUNT=str(failures), DEBIAN_FRONTEND="noninteractive")
            result = subprocess.run([shell, "-e", str(script)], capture_output=True, text=True, env=env, timeout=30)
            self.assertFalse(result.stderr, result.stderr)
            return result.returncode, json.loads(state.read_text(encoding="utf-8"))["calls"]

    def test_success_keeps_the_five_bootstrap_stages(self):
        code, calls = self.run_bootstrap()
        self.assertEqual(code, 0)
        self.assertEqual([c["stage"] for c in calls], list(STAGES))

    def test_each_transient_failure_restarts_with_fresh_indexes(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                code, calls = self.run_bootstrap(stage, 1)
                self.assertEqual(code, 0)
                failed_prefix = list(STAGES[:STAGES.index(stage) + 1])
                self.assertEqual([c["stage"] for c in calls], failed_prefix + ["sleep"] + list(STAGES))
                self.assertEqual([c["argv"] for c in calls if c["stage"] == "sleep"], [["20"]])

    def test_two_index_failures_can_recover_on_the_last_attempt(self):
        code, calls = self.run_bootstrap("update", 2)
        self.assertEqual(code, 0)
        self.assertEqual([c["stage"] for c in calls], ["update", "sleep", "update", "sleep"] + list(STAGES))

    def test_persistent_failures_stop_after_three_attempts_with_the_original_status(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                code, calls = self.run_bootstrap(stage, 10)
                self.assertEqual(code, 100)
                prefix = list(STAGES[:STAGES.index(stage) + 1])
                self.assertEqual([c["stage"] for c in calls], prefix + ["sleep"] + prefix + ["sleep"] + prefix)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    args, remaining = parser.parse_known_args()
    ROOT = args.source
    unittest.main(argv=[sys.argv[0]] + remaining)
