"""Compile and run the VRAM compaction's rules (gpu/vk/vram_compact.h; no game/GPU required), and check that vk_texture.cpp and
vk_vma.cpp still use them: the textures in a pool of their own only with RX_VK_COMPACT, nothing of that pool freed while a pass is
open, and the budget holding the driver's count with the textures' free space alone taken off.

python -I -B tests/test_vram_compact.py [--cxx g++]
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "g++"]

ROOT = Path(__file__).resolve().parents[1]


def block(text, marker):
    start = text.index(marker)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def need(where, text, needles):
    for needle in needles:
        if needle not in text:
            raise SystemExit(where + " no longer has: " + needle)


def check_source():
    tex = (ROOT / "gpu/vk/vk_texture.cpp").read_text(encoding="utf-8")
    vma = (ROOT / "gpu/vk/vk_vma.cpp").read_text(encoding="utf-8")
    # (the compaction is opt-in)
    need("vk_texture.cpp: compact_on()", block(tex, "bool compact_on()"), ['getenv("RX_VK_COMPACT")'])
    # (a texture that is not a render target's goes to the textures' pool only when they are compacted, in a branch before the
    # render targets' pool and blocks, which stay as they are)
    make = block(tex, "Texture* create(const Key& key")
    own = "in_textures && create_image(ci, x.image, x.allocation, false, false, true)"
    need("vk_texture.cpp: create()", make,
         ["const bool in_textures = compact_on() && !x.sparse && !(as_target && !is_bc(x.format) && !is_astc(x.format));", own])
    if not make.index(own) < make.index("pool_take(pool_key, x.image, x.allocation, x.views)"):
        raise SystemExit("vk_texture.cpp: the textures' pool is no longer tried before the render targets' pool and blocks")
    # (while a pass is open nothing of the pool is freed: VMA holds the allocations it listed)
    frame = block(tex, "void texture_frame(uint64_t completed)")
    step_at, sweep = frame.index("compact_step(completed);"), frame.index("for (auto it = dead.begin(); it != dead.end();) {")
    if not step_at < sweep or "if (compact.in_pass) break;" not in frame[sweep:sweep + 400]:
        raise SystemExit("vk_texture.cpp: the dead list is no longer held while a compaction pass is open")
    need("vk_texture.cpp: texture_frame()", frame,
         ["vram_compact::reclaimable(block_free, pool_free)", "vram_compact::pressed(used, allowed)",
          "vram_compact::held_budget(budget, total_bytes, used, reclaim, allowed, pct)", 'getenv("RX_VK_COMPACT_PCT")',
          # (the hold lets go of the excess alone, not of an eighth of the cache; the driver's limit still asks for 7/8)
          "if (held < budget) budget = evict_to = held;", "if (budget < evict_to) evict_to = 0;",
          "total_bytes - pending_bytes <= (evict_to ? evict_to : budget / 8 * 7)"])
    need("vk_texture.cpp: compact_step()", block(tex, "void compact_step(uint64_t completed)"),
         ["if (!compact_on()) return;", "vram_compact::run_from(min_free, compact.pressed)", "vram_compact::rest(compact.pressed)",
          "t != present_source", "image_compact_ignore(i);", "destroy_gen++;"])
    need("vk_vma.cpp: create_image()", block(vma, "bool create_image(const VkImageCreateInfo& ci"),
         ["textures && textures_pool() ? textures_pool()"])
    need("vk_vma.cpp: image_compact_begin()", block(vma, "bool image_compact_begin("), ["di.pool = texture_pool;"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    check_source()
    with tempfile.TemporaryDirectory(prefix="vram-compact-") as tmp:
        exe = Path(tmp) / "vram-compact"
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", str(ROOT / "tests/test_vram_compact.cpp"), "-o", str(exe)],
                       check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
