"""The real AppImage source-copy block preserves repository-local quoted header dependencies.

No AppImage, toolchain, generated files or game is built. Bash runs only the source
copy block before the separately bundled third-party dependencies.
"""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest

# (Linux only)
RUN_ALL_SKIP = {"windows": "the AppImage source-copy block uses POSIX Bash and cp"}

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = re.compile(r'^\s*#\s*include\s*"([^"\n]+)"', re.MULTILINE)


def missing_headers(source, packaged, entries):
    """Follow literal includes relative to their source, including transitive edges/cycles.

    System/include-path/generated dependencies are outside this local-header check.
    Inactive preprocessor branches are checked too: the package supports every host route.
    """
    pending = list(entries)
    visited, missing = set(), {}
    while pending:
        relative = pending.pop()
        if relative in visited:
            continue
        visited.add(relative)
        path = source / relative
        for name in INCLUDE.findall(path.read_text(encoding="utf-8")):
            included = (path.parent / name).resolve()
            if not included.is_relative_to(source) or not included.is_file():
                continue
            target = included.relative_to(source).as_posix()
            if not (packaged / target).is_file():
                missing.setdefault(target, relative)
            pending.append(target)
    return missing


class AppImageHeaders(unittest.TestCase):
    def test_actual_packaged_host_headers(self):
        script = (ROOT / "scripts/linux/appimage.sh").read_text(encoding="utf-8")
        # Execute production commands, stopping before binaries/dependencies and all native build steps.
        start = script.index("# ---- the tools (the sources")
        end = script.index("cp -a third_party/opus", start)
        with tempfile.TemporaryDirectory(prefix="hookshot-appimage-headers-") as folder:
            packaged = Path(folder) / "tools"
            packaged.mkdir()
            env = dict(os.environ, T=str(packaged), VERSION="authored-test")
            result = subprocess.run(["bash", "-eu", "-o", "pipefail", "-c", script[start:end]],
                                    cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            entries = [p.relative_to(ROOT).as_posix() for p in (ROOT / "host").rglob("*")
                       if p.suffix in (".c", ".h")]
            entries += [p.relative_to(ROOT).as_posix() for p in (ROOT / "gpu/render").glob("*.h")]
            self.assertEqual(missing_headers(ROOT, packaged, entries), {},
                             "AppImage source is missing a repository-local header (target: includer)")

    def test_transitive_missing_header_and_include_cycle(self):
        with tempfile.TemporaryDirectory(prefix="hookshot-local-includes-") as folder:
            source, packaged = Path(folder) / "source", Path(folder) / "packaged"
            files = {
                "host/main.c": '#include "../gpu/vk/top.h"\n',
                "gpu/vk/top.h": '#include "deep/leaf.h"\n',
                "gpu/vk/deep/leaf.h": '#include "../top.h"\n#include <external.h>\n',
            }
            for name, text in files.items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                if name != "gpu/vk/deep/leaf.h":
                    target = packaged / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(text, encoding="utf-8")
            self.assertEqual(missing_headers(source, packaged, ["host/main.c"]),
                             {"gpu/vk/deep/leaf.h": "gpu/vk/top.h"})
            target = packaged / "gpu/vk/deep/leaf.h"
            target.parent.mkdir()
            target.write_text(files["gpu/vk/deep/leaf.h"], encoding="utf-8")
            self.assertEqual(missing_headers(source, packaged, ["host/main.c"]), {})


if __name__ == "__main__":
    unittest.main()
