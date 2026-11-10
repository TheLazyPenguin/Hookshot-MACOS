"""Game-free coverage of the camera-centering source transformation.

python -I -B tests/test_camera_centering.py
"""
import sys
import unittest
from pathlib import Path

RUN_ALL_ARGS = []

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nx2"))
import oot_patches


class CameraCenteringPatchTests(unittest.TestCase):
    def setUp(self):
        self.body = (oot_patches.CAM_FOLLOW_ANCHOR
                     + "    c->x[25] = c->x[26];\n"
                     + oot_patches.CAM_FOLLOW_JOIN + "\n    return;\n")
        self.before = ('#include "a64.h"\n'
                       'void before(Ctx *c) {\n' + self.body + '}\n')
        self.after = 'void after(Ctx *c) {\n' + self.body + '}\n'

    def source(self, body):
        return self.before + oot_patches.CAM_HEAD + body + '}\n' + self.after

    def test_inserts_hook_after_authored_override_only_in_camera(self):
        source = self.source(self.body)
        patched = oot_patches.patch_camera_centering(source)
        expected = self.source(self.body.replace(
            oot_patches.CAM_FOLLOW_ANCHOR,
            oot_patches.CAM_FOLLOW_ANCHOR + oot_patches.CAM_FOLLOW_HOOK))
        expected = expected.replace('#include "a64.h"\n',
                                    '#include "a64.h"\nextern int hos_disable_camera_centering(void);\n', 1)
        self.assertEqual(patched, expected)
        self.assertEqual(oot_patches.patch_camera_centering(patched), patched)

    def test_rejects_missing_or_ambiguous_labels_in_camera(self):
        for anchor in (oot_patches.CAM_FOLLOW_ANCHOR, oot_patches.CAM_FOLLOW_JOIN):
            for copies in (0, 2):
                with self.subTest(anchor=anchor, copies=copies):
                    body = self.body.replace(anchor, anchor * copies)
                    self.assertIsNone(oot_patches.patch_camera_centering(self.source(body)))

    def test_rejects_missing_camera_or_unterminated_body(self):
        self.assertIsNone(oot_patches.patch_camera_centering(self.before + self.after))
        self.assertIsNone(oot_patches.patch_camera_centering(
            self.before + oot_patches.CAM_HEAD + self.body))


if __name__ == "__main__":
    unittest.main()
