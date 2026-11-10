"""Switch (Horizon) image builder: we are rtld.

Lays an ExeFS's modules out at fixed guest addresses, applies their relocations and binds every symbol import,
once, at build time. The result is the guest image the lifter reads and the runtime maps.

  - Modules load in rtld's order (main, subsdk*, sdk) from MAIN_BASE, each 1 MB aligned. Skipped modules
    (`skip`, e.g. subsdk0, TOTK's movie player) are not loaded; their exports become hooks.
  - Symbols resolve in that same global order. A symbol named in `hle` that a loaded module defines is hooked at
    its definition (the lifter emits a call of the hook there instead of the body). An undefined weak symbol
    resolves to 0, as rtld does, unless it is in `hle`; any other unresolved symbol binds to a trampoline, so a
    call to it stops with its name instead of jumping to 0.
  - Trampolines are 16-byte slots from TRAMP_BASE. They are guest addresses with no code: the lifter turns calls
    to them into calls of the hook `imp_<mangled name>` (the Rexcomp import model).
  - Entry candidates: .eh_frame_hdr function starts, exported functions, init_array, every RELATIVE/ABS64 result
    that lands in code, every BL target, each module's start.

Usage:  python nx_image.py <exefs_dir> <out_dir> [--skip subsdk0] [--hle names.txt]
  Writes image.bin (MAIN_BASE .. end), image.json (modules, hooks, entries, init order) to out_dir.
"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import nso

MAIN_BASE = 0x08000000
TRAMP_BASE = 0x07000000
ALIGN = 0x100000


def c_ident(sym):
    return "imp_" + "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in sym)


class NxImage:
    def __init__(self, exefs, skip=(), hle=()):
        self.modules = [m for m in nso.load_exefs(exefs) if m.name != "rtld" and m.name not in skip]
        self.skipped = [n for n in skip]
        base = MAIN_BASE
        for m in self.modules:
            m.base = base
            base = (base + len(m.image) + ALIGN - 1) & ~(ALIGN - 1)
        self.end = base
        self.mem = bytearray(self.end - MAIN_BASE)
        for m in self.modules:
            self.mem[m.base - MAIN_BASE:m.base - MAIN_BASE + len(m.image)] = m.image
        self.hle = set(hle)
        self.exports = {}
        for m in self.modules:
            for s in m.symbols:
                if s["defined"] and s["name"] and s["name"] not in self.exports:
                    self.exports[s["name"]] = (m, s)
        self.hooks = {}        # guest address -> C name
        self.hook_syms = {}    # C name -> symbol
        self.tramp = {}        # symbol -> trampoline address
        self.unresolved = {}   # symbol -> number of references
        # An HLE'd symbol a loaded module defines is hooked at its definition: the game's import resolves to it
        # as usual, and lifted SDK code calling it internally reaches the same host function.
        for sym in sorted(self.hle):
            hit = self.exports.get(sym)
            if hit:
                m, s = hit
                name = c_ident(sym)
                self.hooks[m.base + s["value"]] = name
                self.hook_syms[name] = sym
        self._relocate()
        self.code = [(m.base + lo, m.base + hi, m.name) for m in self.modules for lo, hi in [m.code_range()]]
        self._entries()
        self.names = self.symbol_names()

    # ---- binding ---------------------------------------------------------------------------------------
    def trampoline(self, sym):
        a = self.tramp.get(sym)
        if a is None:
            a = self.tramp[sym] = TRAMP_BASE + 16 * len(self.tramp)
            name = c_ident(sym)
            self.hooks[a] = name
            self.hook_syms[name] = sym
        return a

    def resolve(self, sym, weak):
        hit = self.exports.get(sym)
        if hit:
            m, s = hit
            return m.base + s["value"]
        if weak and sym not in self.hle:
            return 0
        if sym not in self.hle:
            self.unresolved[sym] = self.unresolved.get(sym, 0) + 1
        return self.trampoline(sym)

    def _relocate(self):
        for m in self.modules:
            bind = {s["name"]: s["bind"] for s in m.symbols}
            for r in m.relocs:
                at = m.base + r["offset"] - MAIN_BASE
                if r["type"] == "RELATIVE":
                    v = m.base + r["addend"]
                elif r["type"] in ("ABS64", "GLOB_DAT", "JUMP_SLOT"):
                    # S + A for all three (AArch64 ELF ABI; rtld writes the same: symbol address + r_addend)
                    v = self.resolve(r["sym"], bind.get(r["sym"]) == "weak") + r["addend"]
                else:
                    raise SystemExit(f"{m.name}: relocation type {r['type']} at {r['offset']:#x} not supported")
                struct.pack_into("<Q", self.mem, at, v & 0xFFFFFFFFFFFFFFFF)

    # ---- entry candidates ------------------------------------------------------------------------------
    def in_code(self, a):
        if a & 3:
            return False
        for lo, hi, _ in self.code:
            if lo <= a < hi:
                return True
        return False

    def word(self, a):
        return struct.unpack_from("<I", self.mem, a - MAIN_BASE)[0]

    def read(self, a, n):
        if not (MAIN_BASE <= a and a + n <= self.end):
            raise ValueError("read outside the image: %#x" % a)
        return bytes(self.mem[a - MAIN_BASE:a - MAIN_BASE + n])

    def _entries(self):
        e = set()
        for m in self.modules:
            lo, hi = m.code_range()
            e.add(m.base + lo)
            # DT_INIT / DT_FINI: the SDK crt's _init/_fini, which rtld calls per module (rtld+0xcac / +0xcbc)
            e.update(m.base + m.dynamic[k][0] for k in ("INIT", "FINI") if k in m.dynamic)
            e.update(m.base + f for f in m.eh_funcs)
            e.update(m.base + s["value"] for s in m.symbols if s["defined"] and s["type"] == "func" and s["value"])
            for r in m.relocs:
                if r["type"] in ("RELATIVE", "ABS64"):
                    v = struct.unpack_from("<Q", self.mem, m.base + r["offset"] - MAIN_BASE)[0]
                    if self.in_code(v):
                        e.add(v)
            # BL targets. Not ADR / ADRP+ADD targets: in TOTK 3,735 of those were nothing but jump-table base
            # labels, and an entry there cuts a function in two with tail calls looping between the halves.
            # Functions whose address is taken have .eh_frame entries anyway.
            text = memoryview(self.mem)[m.base + lo - MAIN_BASE:m.base + hi - MAIN_BASE]
            for i, w in enumerate(struct.unpack("<%dI" % (len(text) // 4), text)):
                if (w & 0xFC000000) == 0x94000000:
                    off = w & 0x3FFFFFF
                    e.add(m.base + lo + 4 * i + 4 * (off - (1 << 26) if off & (1 << 25) else off))
        self.init_arrays = {m.name: [struct.unpack_from("<Q", self.mem, m.base + off - MAIN_BASE)[0]
                                     for off in self._init_array_offsets(m)] for m in self.modules}
        for arr in self.init_arrays.values():
            e.update(a for a in arr if self.in_code(a))
        self.entries = {a for a in e if self.in_code(a)}
        self.eh_starts = sorted(m.base + f for m in self.modules for f in m.eh_funcs)

    def _init_array_offsets(self, m):
        start = m.dynamic.get("INIT_ARRAY", [0])[0]
        size = m.dynamic.get("INIT_ARRAYSZ", [0])[0]
        return [start + 8 * i for i in range(size // 8)]

    # ---- output ----------------------------------------------------------------------------------------
    def symbol_names(self):
        """guest address -> mangled name, for comments in lifted code"""
        names = {}
        for m in self.modules:
            for s in m.symbols:
                if s["defined"] and s["type"] == "func" and s["name"]:
                    names.setdefault(m.base + s["value"], s["name"])
        return names

    def write(self, out):
        os.makedirs(out, exist_ok=True)
        open(os.path.join(out, "image.bin"), "wb").write(self.mem)
        meta = {
            "base": MAIN_BASE, "end": self.end, "tramp_base": TRAMP_BASE,
            "modules": [{"name": m.name, "base": m.base, "size": len(m.image), "build_id": m.build_id,
                         "init": m.base + m.dynamic["INIT"][0] if "INIT" in m.dynamic else 0,
                         "fini": m.base + m.dynamic["FINI"][0] if "FINI" in m.dynamic else 0,
                         "segments": [{"name": n, "addr": m.base + o, "size": s} for o, s, n in m.segments],
                         "bss": [m.base + m.bss[0], m.base + m.bss[1]]} for m in self.modules],
            "skipped": self.skipped,
            "hooks": [{"addr": a, "c": n, "sym": self.hook_syms[n]} for a, n in sorted(self.hooks.items())],
            "unresolved": self.unresolved,
            "init_arrays": self.init_arrays,
            "exports": {name: m.base + s["value"] for name, (m, s) in self.exports.items() if s["type"] == "func"},
        }
        json.dump(meta, open(os.path.join(out, "image.json"), "w"), indent=0)
        return meta


def main():
    args = sys.argv[1:]
    skip, hle = [], []
    if "--skip" in args:
        i = args.index("--skip"); skip = args[i + 1].split(","); del args[i:i + 2]
    if "--hle" in args:
        i = args.index("--hle"); hle = [l.strip() for l in open(args[i + 1]) if l.strip() and not l.startswith("#")]; del args[i:i + 2]
    img = NxImage(args[0], skip, hle)
    meta = img.write(args[1])
    for m in meta["modules"]:
        print(f"  {m['name']:<8} {m['base']:#010x}  {m['size']:>12,}")
    print(f"entries {len(img.entries):,}  hooks {len(img.hooks):,}  unresolved non-weak {len(img.unresolved)}")


if __name__ == "__main__":
    main()
