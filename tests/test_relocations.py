"""The image builder's relocations (third_party/a64-kit/hos/nx_image.py, NxImage._relocate) on authored modules.

We are rtld, so each relocation must write what Horizon's rtld writes: RELATIVE is the module base + A, and ABS64,
GLOB_DAT and JUMP_SLOT are the symbol's address + A (AArch64 ELF ABI). Symbols bind across modules, an undefined weak
symbol is 0, and any other undefined symbol binds to a trampoline that names it. No game is used.
"""
import os
import struct
import sys
from types import ModuleType, SimpleNamespace
import unittest

# nx_image imports tools/nso.py, which imports lz4.block to decompress NSO segments. _relocate decompresses nothing,
# and run_all installs no packages (CI has no lz4): an empty stand-in lets the test run there; a real lz4 is used when
# present.
try:
    import lz4.block  # noqa: F401
except ImportError:
    sys.modules["lz4"] = ModuleType("lz4")
    sys.modules["lz4.block"] = sys.modules["lz4"].block = ModuleType("lz4.block")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "third_party", "a64-kit", "hos"))
import nx_image  # noqa: E402

MAIN, SDK = nx_image.MAIN_BASE, nx_image.MAIN_BASE + 0x100000


def module(name, base, symbols, relocs):
    return SimpleNamespace(name=name, base=base, symbols=symbols, relocs=relocs)


def sym(name, value=0, defined=True, bind="global"):
    return {"name": name, "value": value, "defined": defined, "bind": bind}


def rel(offset, kind, addend, name=None):
    return {"offset": offset, "type": kind, "addend": addend, "sym": name}


def relocated(modules):
    """NxImage._relocate on these modules: each symbol is defined by at most one of them"""
    img = object.__new__(nx_image.NxImage)
    img.modules = modules
    img.mem = bytearray(0x200000)
    img.hle, img.hooks, img.hook_syms, img.tramp, img.unresolved = set(), {}, {}, {}, {}
    img.exports = {s["name"]: (m, s) for m in modules for s in m.symbols if s["defined"]}
    img._relocate()
    return img, lambda base, offset: struct.unpack_from("<Q", img.mem, base + offset - MAIN)[0]


class Relocations(unittest.TestCase):
    def setUp(self):
        main = module("main", MAIN, [sym("vtable", 0x4000), sym("gone", defined=False),
                                     sym("maybe", defined=False, bind="weak")], [
            rel(0x1000, "RELATIVE", 0x2468),
            rel(0x1008, "ABS64", 0x10, "vtable"),
            rel(0x1010, "GLOB_DAT", 0x18, "table"),
            rel(0x1018, "JUMP_SLOT", 0, "nnFunc"),
            rel(0x1020, "JUMP_SLOT", 0x8, "nnFunc"),
            rel(0x1028, "GLOB_DAT", 0, "maybe"),
            rel(0x1030, "JUMP_SLOT", 0, "gone"),
        ])
        sdk = module("sdk", SDK, [sym("table", 0x800), sym("nnFunc", 0x200)], [])
        self.img, self.word = relocated([main, sdk])

    def test_each_kind_writes_what_rtld_writes(self):
        expect = {
            0x1000: MAIN + 0x2468,          # RELATIVE: B + A
            0x1008: MAIN + 0x4000 + 0x10,   # ABS64: S + A
            0x1010: SDK + 0x800 + 0x18,     # GLOB_DAT: S + A, S defined by another module
            0x1018: SDK + 0x200,            # JUMP_SLOT: S + 0
            0x1020: SDK + 0x200 + 0x8,      # JUMP_SLOT: S + A
            0x1028: 0,                      # undefined weak: 0
        }
        for offset, value in expect.items():
            with self.subTest(offset=hex(offset)):
                self.assertEqual(self.word(MAIN, offset), value)

    def test_an_undefined_symbol_binds_to_its_named_trampoline(self):
        at = self.word(MAIN, 0x1030)
        self.assertEqual(at, self.img.tramp["gone"])
        self.assertEqual(self.img.hooks[at], nx_image.c_ident("gone"))
        self.assertEqual(self.img.unresolved, {"gone": 1})


if __name__ == "__main__":
    unittest.main()
