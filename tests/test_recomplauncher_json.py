"""Game-free checks of recomplauncher.json: it parses, and every settings key is a row of the in-game menu.

Run with: python -I tests/test_recomplauncher_json.py
"""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RecompLauncherJsonTests(unittest.TestCase):
    def test_settings_are_menu_rows(self):
        manifest = json.loads((ROOT / "recomplauncher.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["format"], 1)
        menu = (ROOT / "gpu" / "vk" / "vk_menu.cpp").read_text(encoding="utf-8")
        rows = {re.sub(" ", "_", name.lower()) for name in re.findall(r'\{TAB_[A-Z]+, "([^"]+)"', menu)}
        # (vk_menu.cpp ini_key: the rows whose key is not their name, renamed rows keeping the key an options file has:
        # output_res, resolution, upscaling, frame_rate_cap, dlss)
        ini_key = menu.split("const char* ini_key(const Row& r) {", 1)[1].split("\n}", 1)[0]
        rows |= set(re.findall(r'return "([a-z_0-9]+)";', ini_key))
        keys = {key for setting in manifest["settings"] for choice in setting["choices"] for key in choice["set"]}
        self.assertTrue(keys)
        self.assertEqual(keys - rows, set())

    def test_appimage_carries_it(self):
        self.assertIn('cp recomplauncher.json "$APPDIR/recomplauncher.json"',
                      (ROOT / "scripts" / "linux" / "appimage.sh").read_text(encoding="utf-8"))

    def test_windows_zip_carries_it(self):
        workflow = (ROOT / ".github" / "workflows" / "windows-builder.yml").read_text(encoding="utf-8")
        self.assertIn('z.write("recomplauncher.json", "recomplauncher.json")', workflow)
        self.assertIn("dist/Hookshot-*-Windows-x64.zip", workflow)


if __name__ == "__main__":
    unittest.main()
