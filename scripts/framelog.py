"""The flashes in a frame log (RX_VK_FRAMELOG, gpu/vk/vk_replay.cpp): capture samples, 320x180.

Timestamps sample command recording before GPU submission.

    python -I scripts/framelog.py <file> [out.png]
    python -I scripts/framelog.py <file> --inspect

A frame is a flash where a part of the picture goes brighter (or darker) than BOTH its neighbours by more than they differ
from each other, with the brightness of that part back within reach the next frame. Blocks of 20x20, so that an edge moving
past counts little; a block must jump in brightness, not only in detail. Prints the events by size, with whether the frame was
the game's or a made one, and writes the worst as rows of (before, frame, after).
Only consecutive sequence numbers form a triplet: dropped records cannot establish a one-frame flash. Inspect a
completed, stable capture; --inspect validates its headers without NumPy. Sequence numbers may wrap at uint32;
nonadvancing headers, partial records and captures shorter than three frames are rejected.
"""
import argparse
import mmap
from pathlib import Path
import struct
from typing import NamedTuple

W, H = 320, 180
SIZE = 16 + W * H * 4
MASK = (1 << 32) - 1


class CaptureInfo(NamedTuple):
    timestamps: list[int]
    sequences: list[int]
    kinds: list[int]
    missing: int
    centres: list[int]


def triplet_centres(sequences):
    """Only stored consecutive frames can establish a one-frame brightness jump."""
    return [i for i in range(1, len(sequences) - 1)
            if ((sequences[i] - sequences[i - 1]) & MASK) == 1
            and ((sequences[i + 1] - sequences[i]) & MASK) == 1]


def capture_info(path):
    size = Path(path).stat().st_size
    count, tail = divmod(size, SIZE)
    if tail:
        raise ValueError("truncated record %d: %d bytes, expected %d" % (count + 1, tail, SIZE))
    if count < 3:
        raise ValueError("need at least 3 frames for flash analysis; got %d" % count)
    timestamps, sequences, kinds = [], [], []
    missing = 0
    with open(path, "rb") as file, mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as raw:
        for i in range(count):
            t, s, k = struct.unpack_from("<QII", raw, i * SIZE)
            if k not in (0, 1):
                raise ValueError("invalid frame kind %d at record %d (expected 0 or 1)" % (k, i + 1))
            if timestamps and t <= timestamps[-1]:
                raise ValueError("timestamp does not advance at record %d" % (i + 1))
            if sequences:
                delta = (s - sequences[-1]) & MASK
                if not delta or delta >= (1 << 31):
                    raise ValueError("sequence does not advance at record %d" % (i + 1))
                missing += delta - 1
            timestamps.append(t), sequences.append(s), kinds.append(k)
    return CaptureInfo(timestamps, sequences, kinds, missing, triplet_centres(sequences))


def blocks(a):
    """luma means of 20x20 blocks"""
    l = a[..., 0] * 0.3 + a[..., 1] * 0.6 + a[..., 2] * 0.1
    return l[:H // 20 * 20, :].reshape(H // 20, 20, W // 20, 20).mean(axis=(1, 3))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("out", nargs="?", help="write the worst events to this PNG")
    parser.add_argument("--inspect", action="store_true", help="validate metadata and report eligible triplets without NumPy")
    args = parser.parse_args()
    path, out = args.path, args.out
    try:
        info = capture_info(path)
    except (OSError, ValueError, struct.error) as error:
        parser.error(str(error))
    n = len(info.sequences)
    print(n, "frames")
    eligible = set(info.centres)
    print("flash triplets: %d eligible, %d skipped across sequence gaps; missing %d frames" % (
        len(eligible), n - 2 - len(eligible), info.missing))
    if args.inspect:
        return 0
    try:
        import numpy as np
    except ImportError:
        parser.error("image analysis requires NumPy; --inspect validates capture metadata without it")
    raw = np.memmap(path, dtype=np.uint8, mode="r")
    ts = np.array(info.timestamps, dtype=np.uint64)
    kinds = np.array(info.kinds)
    d = np.diff(ts) / 1e6
    print("capture samples apart: median %.1f ms, 99%% %.1f, worst %.1f; made %d of %d; missing %d" % (
        np.median(d), np.percentile(d, 99), d.max(), kinds.sum(), n, info.missing))
    frame = lambda i: np.asarray(raw[i * SIZE + 16:(i + 1) * SIZE]).reshape(H, W, 4)[..., :3].astype(np.float32)
    prev = blocks(frame(0))
    cur = blocks(frame(1))
    events = []
    for i in range(1, n - 1):
        nxt = blocks(frame(i + 1))
        if i in eligible:
            up = np.minimum(cur - prev, cur - nxt)
            down = np.minimum(prev - cur, nxt - cur)
            span = np.abs(prev - nxt)
            for sign, jump in ((1, up), (-1, down)):
                hit = (jump > 12) & (jump > span * 1.5)
                c = int(hit.sum())
                if c:
                    events.append((float(jump[hit].sum()), i, sign, c, float(jump.max())))
        prev, cur = cur, nxt
    events.sort(reverse=True)
    tot = {0: 0, 1: 0}
    for e in events:
        tot[int(kinds[e[1]])] += 1
    print("events: %d on the game's frames, %d on made frames" % (tot[0], tot[1]))
    for size, i, sign, c, peak in events[:24]:
        print("frame %d (%s) %s %d blocks, peak %.0f, at %.2f s" % (i, "made" if kinds[i] else "game", "brighter" if sign > 0 else "darker",
                                                                     c, peak, (ts[i] - ts[0]) / 1e9))
    if out and events:
        from PIL import Image
        rows = events[:8]
        im = Image.new("RGB", (W * 3, H * len(rows)))
        for r, e in enumerate(rows):
            for k in range(3):
                im.paste(Image.fromarray(frame(e[1] - 1 + k).astype(np.uint8)), (k * W, r * H))
        im.save(out)


if __name__ == "__main__":
    raise SystemExit(main())
