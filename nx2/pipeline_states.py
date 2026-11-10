"""The pipeline state lists (gpu/vk/vk_draw.cpp: hookshot_pipeline_states.bin, written as the game is played): show one, or merge
several into the list a release ships (assets/pipeline_states.bin.xz, unpacked by nx2/make_game.py beside the game as
hookshot_pipeline_states_shipped.bin, whose pipelines the first start's shader preparation builds before the title).

    python -I nx2/pipeline_states.py <list>...                    what they hold
    python -I nx2/pipeline_states.py --out assets/pipeline_states.bin.xz assets/pipeline_states.bin.xz <list>...
                                                                  merged, each pipeline once

A list may be xz-compressed (read by its magic; written so when --out ends in .xz): the shipped one is, so that the
repository's history stays small. xz, not zstd: the AppImage's Python (3.12) has lzma but not compression.zstd.

A list holds no game code: each record is a pipeline's stage code keys (hashes of the game's shaders, which the player's own
hookshot_shaders.bin turns back into the shaders), the program variant's hash, and the formats and draw state baked into the pipeline.

    <list>: "HKSTATE1", u32 record size (528), then the records:
            u64 code[4] (vertex or mesh, fragment, task, the header-only stage), u64 variant,
            u32 mesh, topology, targets, samples, depth format, has depth, u32 color formats[8], u8 color types[8],
            u64 blend[8], u32 vertex attributes[16], u32 attribute count, u32 strides[16], u32 divisors[16],
            u32 blend enables, channel mask, polygon mode, depth clamp, alpha to coverage, pad,
            u32 answers, u32 questions, u32 answers[24] (stage, descriptor, image, type), u8 questions[32] (each answer as asked)
"""
import argparse
import collections
import lzma
import os
import struct
import sys

MAGIC = b"HKSTATE1"
SIZE = 528
SHIPPED = ("assets", "pipeline_states.bin.xz")   # (under the repository's root: the list a release ships)
XZ_MAGIC = b"\xfd7zXZ\x00"


def load(path):
    """The list's bytes as the game reads them: unpacked when the file is xz"""
    with open(path, "rb") as f:
        data = f.read()
    if data[:6] == XZ_MAGIC:
        try:
            data = lzma.decompress(data)
        except lzma.LZMAError as e:
            raise SystemExit("%s: a damaged xz file (%s)" % (path, e))
    return data


def parse(data, path, strict=False):
    """The records of a list's bytes. Stops with the reason when they are not a list of this build's format. A record cut
    short at the end (a game that ended while it wrote) is left out, as the game leaves it out; strict: stops there too"""
    if data[:8] != MAGIC or len(data) < 12 or struct.unpack_from("<I", data, 8)[0] != SIZE:
        found = data[:8].decode("ascii", "replace") if data[:7] == MAGIC[:7] else "no list"
        raise SystemExit("%s: not a pipeline state list of this build's format (%s, %d-byte records; found %s): make it again "
                         "with this build (docs/development.md, \"The pipeline state list\")" % (path, MAGIC.decode(), SIZE, found))
    over = (len(data) - 12) % SIZE
    if over:
        if strict:
            raise SystemExit("%s: cut short (%d bytes over the last whole record)" % (path, over))
        print("%s: %d bytes of a record cut short at the end, left out" % (path, over), file=sys.stderr)
    body = data[12:len(data) - over]
    return [body[i:i + SIZE] for i in range(0, len(body), SIZE)]


def read(path, strict=False):
    return parse(load(path), path, strict)


def check_shipped(path):
    """The list a release ships: present, whole, of this build's format and not empty; its records. Stops with the reason"""
    if not os.path.isfile(path):
        raise SystemExit("%s is missing, and a release must ship it (docs/development.md, \"The pipeline state list\")" % path)
    recs = read(path, strict=True)
    if not recs:
        raise SystemExit("%s holds no pipelines" % path)
    return recs


def write(path, recs):
    data = MAGIC + struct.pack("<I", SIZE) + b"".join(recs)
    if path.endswith(".xz"):
        # (preset 6: an 8 MB window, as much as a list needs; 9's 64 MB would only cost the reader memory)
        data = lzma.compress(data, preset=6 | lzma.PRESET_EXTREME)
    with open(path + ".new", "wb") as f:
        f.write(data)
    os.replace(path + ".new", path)


def describe(recs):
    programs = collections.Counter()
    kinds = collections.Counter()
    for r in recs:
        code = struct.unpack_from("<4Q", r, 0)
        mesh = struct.unpack_from("<I", r, 40)[0]
        programs[(code, mesh)] += 1
        kinds["mesh" if mesh else "graphics"] += 1
    return "%d pipelines (%s) of %d programs" % (len(recs), ", ".join("%s %d" % kv for kv in sorted(kinds.items())), len(programs))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("lists", nargs="+")
    p.add_argument("--out")
    p.add_argument("--check", action="store_true", help="each list must be whole and hold pipelines (the release checks)")
    a = p.parse_args()
    merged, seen = [], set()
    for path in a.lists:
        recs = check_shipped(path) if a.check else read(path)
        print("%s: %s" % (path, describe(recs)))
        for r in recs:
            if r not in seen:
                seen.add(r)
                merged.append(r)
    if a.out:
        write(a.out, merged)
        print("%s: %s" % (a.out, describe(merged)))


if __name__ == "__main__":
    sys.exit(main())
