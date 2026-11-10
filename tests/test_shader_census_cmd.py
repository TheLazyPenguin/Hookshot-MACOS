"""The shader list is started in UTF-8 mode, like the other build steps.

-I alone follows the console's code page. An archive name that page cannot print
stopped the list, and the game then compiled its shaders while it played.

Run with: python -I -B tests/test_shader_census_cmd.py
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import importlib.util

SOURCE = Path(__file__).resolve().parents[1] / "nx2" / "make_game.py"
spec = importlib.util.spec_from_file_location("make_game_under_test", SOURCE)
make_game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_game)


class ShaderCensusCommandTests(unittest.TestCase):
    def test_the_list_uses_the_utf8_interpreter(self):
        cmd = make_game.shader_census_cmd("/tmp/romfs", "/tmp/out/hookshot_shaders.bin")
        self.assertEqual(cmd[:5], [sys.executable, "-I", "-u", "-X", "utf8"])
        self.assertTrue(cmd[5].endswith("shader_census.py"))
        # (the romfs as a long path on Windows, #1468; as given elsewhere)
        self.assertEqual(cmd[6:], [make_game.long_path("/tmp/romfs"), "--out", "/tmp/out/hookshot_shaders.bin"])
        old = [sys.executable, "-I", cmd[5], "/tmp/romfs", "--out", "/tmp/out/hookshot_shaders.bin"]
        self.assertNotEqual(cmd, old)

    def test_that_interpreter_can_print_a_letter_the_page_might_not(self):
        with tempfile.TemporaryDirectory() as d:
            child = os.path.join(d, "child.py")
            with open(child, "w", encoding="utf-8") as f:
                f.write("import sys\nprint(sys.flags.utf8_mode)\nprint('\u6f22')\n")
            cmd = make_game.shader_census_cmd("romfs", "out.bin")
            script = next(i for i, arg in enumerate(cmd) if arg.endswith("shader_census.py"))
            ran = subprocess.run(cmd[:script] + [child], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertEqual(ran.stdout.splitlines()[0], "1")
        self.assertIn("\u6f22", ran.stdout)

    def test_the_build_calls_that_command(self):
        body = SOURCE.read_text(encoding="utf-8")
        start = body.index("def main(")
        main = body[start:]
        self.assertIn("shader_census_cmd(", main)
        self.assertNotIn('"-I", os.path.join(HERE, "shader_census.py")', main)


if __name__ == "__main__":
    unittest.main()
