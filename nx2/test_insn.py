"""Every instruction form the game uses, in Unicorn and as lifted C: a64-kit's tests/insn_test.py with the Switch 2
additions.

Differences from running the vendored test as is:
  - the Switch 2 forms translate (insn.install()), and RETAx are returns (not sampled, like RET);
  - Unicorn runs its "max" CPU model, which has the ARMv8.1+ forms (the default Cortex-A72 rejects LSE, CAS, LDAPR);
  - the harness is built with -mcx16 (CASP on 128 bits);
  - PAC and MTE forms are left out: here they are the identity by design (see insn.py), not the hardware's result;
  - memory operands based on x29 / x30 get their scratch address too: capstone names them fp / lr, which
    insn_test.mem_regs does not parse, so those cases ran on a random (often tiny) address that the harness
    does not reset between cases (a false LDADD [x29] failure, 2026-10-31).

Usage:  python -I nx2/test_insn.py [--modules main,sdk,...] [--per 6] [--states 12] [--only lse]
  (--modules: every code module of the exefs but rtld by default)
  Needs the module images of nso.py in <work>/modules (made on first use).
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # (python -I leaves the script folder off)
import kit
import insn

insn.install()
sys.path.insert(0, os.path.join(kit.KIT, "tests"))
import insn_test   # noqa: E402
import toolchain   # noqa: E402
import unicorn     # noqa: E402
from unicorn import arm64_const as A   # noqa: E402

# (the game: this runs the lifted code of a real dump against Unicorn)
RUN_ALL_SKIP = {
    "linux": "needs the game's modules (work/dump) and Unicorn",
    "windows": "needs the game's modules (work/dump) and Unicorn",
}


class _Unicorn:
    """insn_test's view of the unicorn module: every engine it makes runs the ARMv8.x "max" CPU"""
    UcError = unicorn.UcError
    UC_ARCH_ARM64 = unicorn.UC_ARCH_ARM64
    UC_MODE_ARM = unicorn.UC_MODE_ARM

    @staticmethod
    def Uc(arch, mode):
        uc = unicorn.Uc(arch, mode)
        uc.ctl_set_cpu_model(A.UC_CPU_ARM64_MAX)
        return uc


ONLY = {"lse": lambda w: (w & 0x3F200C00) == 0x38200000 or (w & 0x3FA07C00) == 0x08A07C00
        or (w & 0xBFA07C00) == 0x08207C00,
        "nx2": lambda w: insn.emit(w) is not None}


def mem_regs(w):
    md = insn_test.capstone.Cs(insn_test.capstone.CS_ARCH_ARM64, insn_test.capstone.CS_MODE_ARM)
    md.detail = True
    ins = next(md.disasm(insn_test.struct.pack("<I", w), insn_test.CODE), None)
    alias = {"fp": 29, "lr": 30, "x29": 29, "x30": 30}
    for op in ins.operands if ins else ():
        if op.type == insn_test.capstone.arm64.ARM64_OP_MEM:
            def num(r):
                if r is None:
                    return None
                name = ins.reg_name(r)
                if name in ("sp", "wsp"):
                    return "sp"
                if name in alias:
                    return alias[name]
                return int(name[1:]) if name[1:].isdigit() else None
            return num(op.mem.base or None), num(op.mem.index or None)
    return None


def main():
    kit.wait_for_quiet('the instruction test')
    only = None
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        only = ONLY[sys.argv[i + 1]]
        del sys.argv[i:i + 2]
    modules = os.path.join(kit.WORK, "modules")
    if not os.path.exists(os.path.join(modules, "main.json")):
        subprocess.run([sys.executable, "-I", os.path.join(kit.KIT, "tools", "nso.py"), kit.need_exefs(), modules],
                       check=True, stdout=subprocess.DEVNULL)
    if "--modules" not in sys.argv:
        sys.argv += ["--modules", ",".join(kit.game_modules())]
    insn_test.unicorn = _Unicorn
    insn_test.mem_regs = mem_regs
    base_target = toolchain.native_target
    toolchain.native_target = lambda *a, **k: base_target(*a, **k) + ["-mcx16"]
    base_sample = insn_test.sample

    def sample(image_dir, mods, per, rng):
        picked = [(k, w) for k, w in base_sample(image_dir, mods, per, rng) if not insn.is_identity_model(w)]
        return [(k, w) for k, w in picked if only(w)] if only else picked

    insn_test.sample = sample
    sys.argv = [sys.argv[0], modules] + sys.argv[1:]
    return insn_test.main()


if __name__ == "__main__":
    sys.exit(main())
