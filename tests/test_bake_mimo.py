"""The bake pass, end to end, on synthetic archives: enumerate -> translate (Eglantine, offline) -> bank.

nx2/bake_mimo.py over a fixture romfs this test writes (a BNSH and an NDSR carrying the same three stages, a
file this machine cannot decompress), then gpu/shaderbatch.cpp over the seed it makes. What it proves:
  - the miner reads the containers nx2/shader_census.py reads, and dedupes two archives' copies of one stage to
    one stable ID (the FNV-1a code_key of gpu/vk/vk_shader.cpp:135-137, recomputed here independently);
  - the runtime's seed comes out of it byte-shaped as seed_open reads it (vk_shader.cpp:1844-1883);
  - a stage goes all the way through capture, LowerToMaxwell, the Maxwell frontend and EmitSPIRV with no GPU,
    and the SPIR-V is a module;
  - the bank records it, with every pipeline still PENDING_GPU.

No game files: the fixture is built here. CPU only; the first run compiles gpu/shaderbatch.cpp against the
vendored recompiler (~164 files, cached under the output folder's obj/).
python3 -I -B tests/test_bake_mimo.py [--cxx <compiler>] [--headers <SPIRV-Headers/include>]
"""
import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "work" / "bake-mimo-test"

RUN_ALL_ARGS = ["--cxx", "{cxx}", "--headers", "{spirv_headers}"]

EXIT = struct.pack("<4I", 0x0000794D, 0, 0x03800000, 0x000FEA00)   # (tests/test_lower_atomg_cas.py's EXIT)
CONTROL = 0xD8
FNV_OFFSET = 0xCBF29CE484222325
FNV_PRIME = 0x100000001B3


def fnv1a(data, h=FNV_OFFSET):
    for b in data:
        h = ((h ^ b) * FNV_PRIME) & ((1 << 64) - 1)
    return h


def control_section(nvn_stage, native_bytes, workgroup=(8, 1, 1)):
    """An NVN2 control section: magic 0x98761234, the code length, the stage, the workgroup (vk_shader.cpp:95-134)"""
    c = bytearray(CONTROL)
    struct.pack_into("<I", c, 0, 0x98761234)
    struct.pack_into("<I", c, 0x38, native_bytes)     # len
    struct.pack_into("<I", c, 0x40, native_bytes)     # c1o (the program's own constants: none here)
    struct.pack_into("<I", c, 0x44, native_bytes)     # end: the code area's size
    struct.pack_into("<H", c, 0x56, vn := vn_stage(nvn_stage))
    if vn == 5:
        struct.pack_into("<3I", c, 0x58, *workgroup)
    return bytes(c)


def vn_stage(s):
    return s


def program_header(shader_type):
    """128 bytes of graphics program header: common0.shader_type is bits 10..14 (program_header.h:34)"""
    h = bytearray(128)
    struct.pack_into("<I", h, 0, shader_type << 10)
    return bytes(h)


def make_stages():
    """Five stages: a compute program, a vertex + fragment pair, and an NVN2 task + mesh pair (the fragment
    goes to both graphics programs). A graphics stage needs more than the header and one instruction to not
    read as header-only (vk_shader.cpp:175-179: len <= 128 + 16 is a header alone), so each carries two."""
    compute_ctl = control_section(5, len(EXIT))
    compute_code = EXIT
    vs_ctl = control_section(0, 128 + 2 * len(EXIT))
    vs_code = program_header(1) + EXIT + EXIT
    fs_ctl = control_section(1, 128 + 2 * len(EXIT))
    fs_code = program_header(5) + EXIT + EXIT
    # (task and mesh: control +0x58 threads 15:0 / payload 31:16, +0x60 primitives 15:0 / vertices 31:16,
    #  +0x5f the output topology in GL's numbers (3 = triangles) — parse_code vk_shader.cpp:164-172)
    task_ctl = bytearray(control_section(6, 128 + 2 * len(EXIT)))
    struct.pack_into("<I", task_ctl, 0x58, 32 | (128 << 16))
    mesh_ctl = bytearray(control_section(7, 128 + 2 * len(EXIT)))
    struct.pack_into("<I", mesh_ctl, 0x58, 32)
    struct.pack_into("<I", mesh_ctl, 0x60, 64 | (64 << 16))
    mesh_ctl[0x5F] = 3
    task_code = program_header(0) + EXIT + EXIT
    mesh_code = program_header(0) + EXIT + EXIT
    return ((compute_ctl, compute_code), (vs_ctl, vs_code), (fs_ctl, fs_code),
            (bytes(task_ctl), task_code), (bytes(mesh_ctl), mesh_code))


def stage_key(ctl, code):
    end = struct.unpack_from("<I", ctl, 0x44)[0]
    return fnv1a(code[:end], fnv1a(ctl[:0xD8]))


def make_bnsh(programs):
    """A BNSH good enough for bnsh_programs (nx2/shader_census.py:65-92): header, variation table, program
    records with their stage slots, then stage records, control sections and code areas"""
    n = len(programs)
    header = 136                      # (count + variations offset sit at 124)
    variations = header               # count records of 64 bytes, the program pointer at +16
    progs_at = variations + n * 64
    stages_at = progs_at + n * 80
    stage_records = sum(len(p) for p in programs)
    ctl_at = stages_at + stage_records * 32
    ctl_size = CONTROL * stage_records
    code_at = ctl_at + ctl_size

    codes = []
    codes_end = code_at
    for p in programs:
        for _, code in p:
            codes.append((codes_end, len(code)))
            codes_end += len(code)

    buf = bytearray(codes_end)
    buf[0:4] = b"BNSH"
    buf[12:14] = b"\xff\xfe"
    buf[96:100] = b"grsc"
    struct.pack_into("<I", buf, 28, len(buf))
    struct.pack_into("<IQ", buf, 124, n, variations)

    c = ctl_at
    ci = 0
    si = 0
    for pi, p in enumerate(programs):
        rec = variations + pi * 64
        struct.pack_into("<Q", buf, rec + 16, progs_at + pi * 80)
        for k in range(len(p)):   # (the program's stage slots, 8 bytes each from +8: SLOTS, shader_census:35)
            struct.pack_into("<Q", buf, progs_at + pi * 80 + 8 + 8 * k, stages_at + (si + k) * 32)
        for k, (ctl, code) in enumerate(p):
            off = stages_at + (si + k) * 32
            struct.pack_into("<QQII", buf, off + 8, c, codes[ci + k][0], codes[ci + k][1], CONTROL)
            buf[c:c + CONTROL] = ctl
            ca, cl = codes[ci + k]
            buf[ca:ca + cl] = code
            c += CONTROL
        ci += len(p)
        si += len(p)
    return bytes(buf)


def make_ndsr(programs):
    """An NDSR good enough for ndsr_programs (nx2/shader_census.py:142-164): items of control (type 0/3/6) and
    code (1/4/7) offsets, a vertex and the fragment after it one program, a compute one alone"""
    items = []      # (type, blob)
    for p in programs:
        if len(p) == 1:
            items.append((6, p[0][0]))     # compute control
            items.append((7, p[0][1]))     # compute code
        else:
            for k, (ctl, code) in enumerate(p):
                items.append((0 if k == 0 else 3, ctl))
                items.append((1 if k == 0 else 4, code))
    head = 0x14 + 8 * len(items)
    blobs, at = [], head
    offsets = []
    for _, blob in items:
        offsets.append(at)
        blobs.append(blob)
        at += len(blob)
    buf = bytearray(at)
    buf[0:4] = b"NDSR"
    struct.pack_into("<I", buf, 0x0C, len(items))
    for i, ((t, blob), off) in enumerate(zip(items, offsets)):
        struct.pack_into("<II", buf, 0x14 + 8 * i, off, (len(blob) << 4) | t)
        buf[off:off + len(blob)] = blob
    return bytes(buf)


def write_fixture(romfs):
    cs, vs, fs, task, mesh = make_stages()
    programs = [[cs], [vs, fs], [task, mesh, fs]]
    (romfs / "Shader").mkdir(parents=True, exist_ok=True)
    (romfs / "Lib" / "agl").mkdir(parents=True, exist_ok=True)
    (romfs / "Shader" / "Sample.bfsha").write_bytes(make_bnsh(programs))
    (romfs / "Lib" / "agl" / "agl_ndsr_sample.pck").write_bytes(make_ndsr(programs))
    # (a file this machine cannot read: zstd magic with nothing behind it)
    (romfs / "Shader" / "Unreadable.bfsha.zs").write_bytes(b"\x28\xb5\x2f\xfd" + os.urandom(64))
    return programs


def run(args, expect=0):
    r = subprocess.run([sys.executable, "-I", "-B"] + args, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != expect:
        raise SystemExit("%s: exit %d\n%s\n%s" % (" ".join(args), r.returncode, r.stdout, r.stderr))
    return r


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="enumerate -> translate -> bank on the fixtures")
    p.add_argument("--cxx", default=None, help="C++ compiler (sets BAKE_CXX)")
    p.add_argument("--headers", default=None, help="SPIR-V headers dir (sets HOOKSHOT_SPIRV_HEADERS)")
    a = p.parse_args(argv)
    if a.cxx:
        os.environ["BAKE_CXX"] = a.cxx
    if a.headers:
        os.environ["HOOKSHOT_SPIRV_HEADERS"] = a.headers
    # (a compiler and the SPIR-V headers are what the translate stage needs; without them the miner and the bank
    #  still run — tests/run_all.py skips a check whose tool is missing the same way)
    sys.path.insert(0, str(ROOT / "nx2"))
    import bake_mimo
    try:
        bake_mimo.cxx_std(bake_mimo.cxx())   # (a compiler, and one with a C++23 mode: the recompiler needs it)
    except SystemExit as e:
        print("SKIP: %s" % e)
        return
    if not bake_mimo.spirv_headers():
        print("SKIP: no SPIR-V headers (HOOKSHOT_SPIRV_HEADERS or a CPM cache): only the miner could run")
        return
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    romfs = OUT / "romfs"
    programs = write_fixture(romfs)
    py = [str(ROOT / "nx2" / "bake_mimo.py")]

    # ---- enumerate ----
    run(py + ["enumerate", "--romfs", str(romfs), "--out", str(OUT)])
    manifest = json.loads((OUT / "manifest.json").read_text())
    assert manifest["counters"]["programs"] == 3, manifest["counters"]
    assert manifest["counters"]["stages"] == 5, manifest["counters"]
    assert manifest["counters"]["compressed_without_zstandard"] + manifest["counters"]["skipped"] >= 1, \
        "the unreadable .zs was not reported"
    kinds = sorted(p["kind"] for p in manifest["programs"])
    assert kinds == ["compute", "graphics", "mesh"], kinds
    # stable IDs: the FNV-1a code_key, recomputed here from the seed itself
    seed = (OUT / "hookshot_shaders.bin").read_text if False else (OUT / "hookshot_shaders.bin").read_bytes()
    assert seed[:8] == b"HKSEED01"
    nprograms, nstages = struct.unpack_from("<II", seed, 8)
    assert (nprograms, nstages) == (3, 5), (nprograms, nstages)
    at, ids = 16, []
    for _ in range(nstages):
        key, stage, csize, nbytes = struct.unpack_from("<QIII", seed, at)
        control = seed[at + 20:at + 20 + csize]
        code = seed[at + 20 + csize:at + 20 + csize + nbytes]
        here = fnv1a(code, fnv1a(control))
        assert key == here, (hex(key), hex(here))
        ids.append("%016x" % key)
        at += 20 + csize + nbytes
    assert set(ids) == {s["id"] for s in manifest["stages"]}, (ids, manifest["stages"])
    # both fixtures carried the same stages: each one's provenance names both files
    for s in manifest["stages"]:
        files = {x.split("#")[0] for x in s["sources"]}
        assert "Shader/Sample.bfsha" in files and "Lib/agl/agl_ndsr_sample.pck" in files, s["sources"]
    for p in manifest["programs"]:   # (the same program in both archives: both sources named)
        assert len(p["sources"]) == 2, p["sources"]
    compute = [p for p in manifest["programs"] if p["kind"] == "compute"][0]
    assert compute["runtime_key"] in compute["stage_ids"], compute

    # ---- translate (the only slow part: the first run builds gpu/shaderbatch) ----
    run(py + ["translate", "--out", str(OUT)])
    stages_rows = (OUT / "translate" / "stages.tsv").read_text().splitlines()
    header, rows = stages_rows[0], [r.split("\t") for r in stages_rows[1:] if r]
    assert header.startswith("#key")
    by_key = {r[0]: r for r in rows}
    assert set(by_key) == set(ids), (set(by_key), set(ids))   # the tool's keys are the miner's IDs
    statuses = {r[0]: r[2] for r in rows}
    spv_dir = OUT / "translate" / "spv"
    programs_rows = [r.split("\t") for r in (OUT / "translate" / "programs.tsv").read_text().splitlines()[1:] if r]
    assert programs_rows, "no program rows"
    translated = [r for r in programs_rows if r[6] == "OK"]
    assert len(translated) == len(programs_rows), [(r[0], r[3], r[6], r[8]) for r in programs_rows]
    # (every stage translated, NVN2 task/mesh included: the mesh program's task, mesh and fragment modules)
    assert set(statuses.values()) == {"OK"}, statuses
    mesh_row = [r for r in programs_rows if r[3] == "mesh"]
    assert mesh_row and mesh_row[0][6] == "OK", mesh_row
    for suffix in ("_6.spv", "_7.spv", "_1.spv"):
        assert any(f.endswith(suffix) for f in mesh_row[0][7].split(",") if f), (suffix, mesh_row[0][7])
    modules = list(spv_dir.glob("*.spv"))
    assert modules, "no SPIR-V written"
    for m in modules:
        assert m.read_bytes()[:4] == b"\x03\x02\x23\x07", m   # SPIR-V magic, little endian
    # (spirv-val, where the machine has one: the modules are real, not just magic-numbered)
    if shutil.which("spirv-val"):
        for m in modules:
            r = subprocess.run(["spirv-val", "--target-env", "vulkan1.3", str(m)], capture_output=True, text=True)
            assert r.returncode == 0, (m, r.stdout, r.stderr)
    # every program key in the TSV is a 16-hex runtime key
    for r in programs_rows:
        assert len(r[2]) == 16 and all(c in "0123456789abcdef" for c in r[2]), r

    # ---- bank ----
    run(py + ["bank", "--out", str(OUT)])
    bank = json.loads((OUT / "bank" / "bank.json").read_text())
    assert bank["format"] == "HKBANK01"
    assert len(bank["translator_stamp"]) == 16
    entries = [json.loads(x) for x in (OUT / "bank" / "programs.jsonl").read_text().splitlines() if x]
    assert len(entries) == len(programs_rows)
    assert all(e["pipelines"] == "PENDING_GPU" for e in entries)
    assert any(e["status"] == "TRANSLATED" for e in entries), [e["status"] for e in entries]
    for e in entries:
        for f in e["spv"]:
            assert (OUT / "bank" / f).is_file(), f
    print("PASS: enumerate -> translate -> bank on the fixtures: %s"
          % {r[3] + "/" + r[6] for r in programs_rows})


if __name__ == "__main__":
    main()
