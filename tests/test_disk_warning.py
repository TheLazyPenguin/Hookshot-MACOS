"""A build on a hard drive warns that an SSD is much faster and goes ahead: nx2/disk.py's answer for a drive, the Linux sysfs
walk behind it (a partition, and a device-mapper disk through its slaves), and make_game.py's one warning line.

python -I -B tests/test_disk_warning.py
"""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nx2"))
import disk  # noqa: E402
import make_game  # noqa: E402


def put(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).write_text(text, encoding="ascii")


class DriveTypeTests(unittest.TestCase):
    def test_a_partition_reads_the_disk_above_it(self):
        with tempfile.TemporaryDirectory(prefix="hookshot-disk-") as tmp:
            sda = os.path.join(tmp, "devices", "pci", "block", "sda")
            put(os.path.join(sda, "queue", "rotational"), "1\n")
            os.makedirs(os.path.join(sda, "sda1"))
            self.assertIs(disk._device_rotational(os.path.join(sda, "sda1")), True)

            put(os.path.join(sda, "queue", "rotational"), "0\n")
            self.assertIs(disk._device_rotational(os.path.join(sda, "sda1")), False)

    def test_a_device_mapper_disk_follows_its_slaves(self):
        with tempfile.TemporaryDirectory(prefix="hookshot-disk-") as tmp:
            dm = os.path.join(tmp, "devices", "virtual", "block", "dm-0")
            put(os.path.join(dm, "queue", "rotational"), "0\n")   # (dm reports its own, not what it lies on)
            sda = os.path.join(tmp, "devices", "pci", "block", "sda")
            put(os.path.join(sda, "queue", "rotational"), "1\n")
            os.makedirs(os.path.join(sda, "sda1"))
            os.makedirs(os.path.join(dm, "slaves"))
            try:   # (as sysfs has it: a slave is a symlink to the disk or partition behind it)
                os.symlink(os.path.join(sda, "sda1"), os.path.join(dm, "slaves", "sda1"), target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("this PC does not let a test make the symlink sysfs uses")

            self.assertIs(disk._device_rotational(dm), True)   # (one spinning slave makes the build slow)

    def test_an_unknown_device_is_not_guessed(self):
        with tempfile.TemporaryDirectory(prefix="hookshot-disk-") as tmp:
            self.assertIsNone(disk._device_rotational(os.path.join(tmp, "nowhere")))

    def test_spinning_picks_the_system_reader(self):
        with tempfile.TemporaryDirectory(prefix="hookshot-disk-") as tmp:
            with mock.patch.object(disk.os, "name", "nt"), \
                 mock.patch.object(disk, "_windows_spinning", return_value=True) as windows, \
                 mock.patch.object(disk, "_linux_spinning") as linux:
                self.assertIs(disk.spinning(tmp), True)
                windows.assert_called_once()
                linux.assert_not_called()
            with mock.patch.object(disk.os, "name", "posix"), mock.patch.object(disk.sys, "platform", "linux"), \
                 mock.patch.object(disk, "_linux_spinning", return_value=False) as linux, \
                 mock.patch.object(disk, "_windows_spinning") as windows:
                self.assertIs(disk.spinning(tmp), False)
                linux.assert_called_once()
                windows.assert_not_called()

    def test_a_folder_made_later_is_measured_at_its_existing_parent(self):
        with tempfile.TemporaryDirectory(prefix="hookshot-disk-") as tmp:
            self.assertEqual(disk.existing_parent(os.path.join(tmp, "Games", "Hookshot")), os.path.abspath(tmp))


class WarningTests(unittest.TestCase):
    def warning(self, slow, folders):
        out = io.StringIO()
        with mock.patch.object(make_game, "spinning_disk", side_effect=lambda p: p in slow), contextlib.redirect_stdout(out):
            make_game.warn_slow_disk(*folders)
        return out.getvalue()

    def test_a_hard_drive_warns_once_and_the_build_goes_on(self):
        text = self.warning({"D:/Games", "D:/Build"}, ["D:/Games", "D:/Build"])
        self.assertEqual(text.count("Warning:"), 1)
        self.assertIn("D:/Games", text)
        self.assertIn("SSD", text)
        self.assertIn("goes ahead", text)

    def test_the_build_files_folder_is_checked_too(self):
        text = self.warning({"C:/Cache"}, ["C:/Games", "C:/Cache"])
        self.assertIn("C:/Cache", text)

    def test_an_ssd_or_an_unknown_drive_says_nothing(self):
        # (spinning_disk is True only for a hard drive: False for an SSD and None for a drive it cannot tell)
        self.assertEqual(self.warning(set(), ["C:/Games"]), "")

    def test_under_prepare_the_warning_keeps_stdout_for_the_progress_lines(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(make_game, "spinning_disk", return_value=True), mock.patch.object(make_game, "PREPARE", True), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            make_game.warn_slow_disk("D:/Games")
        self.assertEqual(out.getvalue(), "")   # (RecompLauncher reads the progress lines on stdout)
        self.assertIn("SSD", err.getvalue())


class BuilderTests(unittest.TestCase):
    """The three builders ask before a build on a hard drive, and their "Build" goes on when the player says so"""

    def test_the_windows_builder_asks(self):
        source = (ROOT / "builder" / "HookshotBuilder" / "MainWindow.xaml.cs").read_text(encoding="utf-8")
        self.assertIn("HardDriveWarning()", source)
        self.assertIn("Disk.Spinning", source)
        self.assertIn("MessageBoxButton.OKCancel", source)

    def test_the_python_builder_asks(self):
        source = (ROOT / "builder" / "py" / "hookshot_builder" / "window.py").read_text(encoding="utf-8")
        self.assertIn("hard_drive_warning()", source)
        self.assertIn("core.spinning", source)

    def test_the_linux_builder_asks(self):
        source = (ROOT / "builder" / "linux" / "hookshot_builder.py").read_text(encoding="utf-8")
        self.assertIn("slow_disk_warning(out)", source)
        self.assertIn("askokcancel", source)

    def test_make_game_warns_before_it_builds(self):
        source = (ROOT / "nx2" / "make_game.py").read_text(encoding="utf-8")
        self.assertIn("warn_slow_disk(out, work)", source)


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=1))
