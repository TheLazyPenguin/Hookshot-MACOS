"""The AppImage carries scripts/, so NVIDIA DLSS (nx2/make_game.py's ngx_script(), scripts/ngx_sdk.py) can be fetched from a
release AppImage and not only from a source checkout. Runs the real copy block of scripts/linux/appimage.sh into a
temporary folder; nothing is built.

Issue: the comment above the copy ("the sources the player's build compiles, and the scripts") already said scripts
belonged here, but the cp -a line itself left scripts out, so HOOKSHOT_NGX_SDK/--fetch-ngx-sdk on a released AppImage
failed with FileNotFoundError on scripts/ngx_sdk.py.

    python -I -B tests/test_appimage_scripts.py
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WANT = {
    "scripts/ngx_sdk.py": "scripts/ngx_sdk.py",
    "scripts/linux/ngx-sdk.sh": "scripts/linux/ngx-sdk.sh",
}


class AppImageScripts(unittest.TestCase):
    # (the AppImage is made on Linux; Windows runners have no usable bash for the script's block)
    @unittest.skipUnless(sys.platform.startswith("linux"), "the AppImage is made on Linux")
    def test_copied(self):
        script = (ROOT / "scripts/linux/appimage.sh").read_text(encoding="utf-8")
        start = script.index("# ---- the tools (the sources")
        end = script.index("cp -a third_party/opus", start)
        with tempfile.TemporaryDirectory(prefix="hookshot-appimage-scripts-") as folder:
            env = dict(os.environ, T=folder, VERSION="authored-test")
            result = subprocess.run(["bash", "-eu", "-o", "pipefail", "-c", script[start:end]], cwd=ROOT, env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for shipped, source in WANT.items():
                self.assertEqual((Path(folder) / shipped).read_bytes(), (ROOT / source).read_bytes(), shipped)


if __name__ == "__main__":
    unittest.main()
