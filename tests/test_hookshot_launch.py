"""The launcher starts the built game and does not keep the builder's libraries on the path.

python -I -B tests/test_hookshot_launch.py
"""
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

# (Linux only)
RUN_ALL_SKIP = {"windows": "the Linux launcher, a POSIX shell script"}

ROOT = Path(__file__).resolve().parents[1]
LAUNCH = ROOT / "builder" / "linux" / "hookshot-launch"


def game(folder):
    folder.mkdir()
    (folder / "image.bin").write_bytes(b"image")
    exe = folder / "hookshot"
    exe.write_text(
        "#!/bin/sh\n"
        "pwd\n"
        "printf 'APPDIR=%s\\n' \"${APPDIR-UNSET}\"\n"
        "printf 'LD_LIBRARY_PATH=%s\\n' \"${LD_LIBRARY_PATH-UNSET}\"\n"
        "printf 'HOOKSHOT_TOOLS=%s\\n' \"${HOOKSHOT_TOOLS-UNSET}\"\n"
        "printf 'PYTHONPATH=%s\\n' \"${PYTHONPATH-UNSET}\"\n"
        "printf 'HOME=%s\\n' \"$HOME\"\n",
        encoding="utf-8",
    )
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)


class LaunchTests(unittest.TestCase):
    def env(self, **extra):
        e = os.environ.copy()
        e.pop("DISPLAY", None)
        e.pop("WAYLAND_DISPLAY", None)
        e.update(
            APPDIR="/from/the/appimage",
            APPIMAGE="/tmp/Hookshot.AppImage",
            ARGV0="Hookshot",
            OWD="/old",
            LD_LIBRARY_PATH="/builder/lib",
            HOOKSHOT_TOOLS="/builder/tools",
            PYTHONPATH="/builder/python",
        )
        e.update(extra)
        return e

    def test_the_saved_folder_starts_without_the_builders_libraries(self):
        with tempfile.TemporaryDirectory(prefix="hookshot-launch-") as tmp:
            root = Path(tmp)
            folder = root / "100% Games"
            game(folder)
            ini = root / "builder.ini"
            ini.write_text("kind=nup\nout=%s\n" % folder, encoding="utf-8")
            ran = subprocess.run(
                [str(LAUNCH)],
                env=self.env(HOOKSHOT_LAUNCH_CONFIG=str(ini)),
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(ran.returncode, 0, ran.stderr)
        lines = ran.stdout.splitlines()
        self.assertEqual(lines[0], str(folder))
        self.assertIn("APPDIR=UNSET", lines)
        self.assertIn("LD_LIBRARY_PATH=UNSET", lines)
        self.assertIn("HOOKSHOT_TOOLS=UNSET", lines)
        self.assertIn("PYTHONPATH=UNSET", lines)
        self.assertIn("HOME=%s" % os.environ["HOME"], lines)

    def test_play_starts_the_game_in_bin_not_the_launcher(self):
        with tempfile.TemporaryDirectory(prefix="hookshot-launch-") as tmp:
            root = Path(tmp)
            folder = root / "game"
            game(folder)
            (folder / "hookshot").write_text("#!/bin/sh\nprintf 'launcher\\n'\n", encoding="utf-8")
            nested = folder / "bin"
            nested.mkdir()
            exe = nested / "hookshot"
            exe.write_text(
                "#!/bin/sh\nprintf 'game\\n'\nprintf 'CHECK=%s\\n' \"${HOOKSHOT_NO_UPDATE_CHECK-UNSET}\"\n",
                encoding="utf-8",
            )
            exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
            ran = subprocess.run([str(LAUNCH), str(folder)], env=self.env(), text=True, capture_output=True, check=False)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertEqual(ran.stdout.splitlines()[0], "game")
        self.assertIn("CHECK=1", ran.stdout)

    def test_a_folder_argument_wins(self):
        with tempfile.TemporaryDirectory(prefix="hookshot-launch-") as tmp:
            root = Path(tmp)
            saved = root / "saved"
            other = root / "other"
            game(saved)
            game(other)
            ini = root / "builder.ini"
            ini.write_text("out=%s\n" % saved, encoding="utf-8")
            ran = subprocess.run(
                [str(LAUNCH), str(other)],
                env=self.env(HOOKSHOT_LAUNCH_CONFIG=str(ini)),
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertEqual(ran.stdout.splitlines()[0], str(other))

    def test_relative_folder_paths(self):
        for source in ("argument", "config"):
            for relative in ("100% Games", "./100% Games"):
                with self.subTest(source=source, folder=relative):
                    with tempfile.TemporaryDirectory(prefix="hookshot-launch-") as tmp:
                        root = Path(tmp)
                        folder = root / "100% Games"
                        game(folder)
                        ini = root / "builder.ini"
                        ini.write_text("out=%s\n" % relative, encoding="utf-8")
                        args = [str(LAUNCH)]
                        if source == "argument":
                            args.append(relative)
                        ran = subprocess.run(
                            args,
                            cwd=root,
                            env=self.env(HOOKSHOT_LAUNCH_CONFIG=str(ini)),
                            text=True,
                            capture_output=True,
                            check=False,
                        )
                    self.assertEqual(ran.returncode, 0, ran.stderr)
                    self.assertEqual(ran.stdout.splitlines()[0], str(folder))

    def test_no_game_is_an_error(self):
        with tempfile.TemporaryDirectory(prefix="hookshot-launch-") as tmp:
            ini = Path(tmp) / "builder.ini"
            ini.write_text("out=%s\n" % tmp, encoding="utf-8")
            ran = subprocess.run(
                [str(LAUNCH)],
                env=self.env(HOOKSHOT_LAUNCH_CONFIG=str(ini)),
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertNotEqual(ran.returncode, 0)
        self.assertIn("no built game", ran.stderr)

    def test_play_is_the_builder_appimage(self):
        script = (ROOT / "scripts" / "linux" / "appimage.sh").read_text(encoding="utf-8")
        self.assertNotIn("Hookshot-launcher-", script)
        apprun = (ROOT / "builder" / "linux" / "AppRun").read_text(encoding="utf-8")
        self.assertIn("hookshot-launch", apprun)
        desktop = (ROOT / "builder" / "linux" / "hookshot-builder.desktop").read_text(encoding="utf-8")
        self.assertIn("Actions=Play;", desktop)
        self.assertIn("Exec=AppRun --play\n", desktop)


if __name__ == "__main__":
    unittest.main()
