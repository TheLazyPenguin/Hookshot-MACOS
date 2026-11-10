// (hookshot) The compaction's rules (RX_VK_COMPACT=1; vk_texture.cpp's compact_step and the texture budget), apart from Vulkan so
// that tests/test_vram_compact.py can run them.
//
// The driver counts VMA's blocks whole. An evicted texture's memory stays inside its 128 MB block, so the count keeps what the
// cache gave up: at DLAA 2560 x 1440 on a 12 GB card the count sat at 10.0 of the 10.9 GB the driver allows with 1.4-1.7 GB of it
// free inside the blocks. There the GPU's frame went from ~10 ms to 13-20 ms (the driver itself short, and the write-back
// shadows given back at 95%): 34-49 frames over 33 ms in a five-minute walk across Hyrule Field, a 1% low of 26-29 fps.
// Compacted, the textures' free space goes back to the driver, and the budget can hold the count below that.
#pragma once

#include <algorithm>
#include <cstdint>

namespace vram_compact {

/// The driver's count over 90% of what it allows: a run starts for less free space, and the next one sooner
inline bool pressed(uint64_t used, uint64_t allowed) { return allowed && used > allowed / 10 * 9; }

/// The free space in the textures' pool from which a run starts: RX_VK_COMPACT_MB (512), 192 MB while pressed. The cache grows
/// into what a run gave back while the next one waits: under a 9.8 GB allowance the count reached 10.2 GB with 1.1-1.6 GB free
inline uint64_t run_from(uint64_t min_free, bool is_pressed) { return is_pressed ? std::min<uint64_t>(min_free, 192ull << 20) : min_free; }

/// The presents between the end of a run and the next look
inline uint64_t rest(bool is_pressed) { return is_pressed ? 120 : 600; }

/// The free space the texture budget takes off the driver's count: the textures' pool's alone, which a run gives back. What the
/// other blocks hold free (the render targets', the buffers') stays in the count and no texture can take it; taken off as well,
/// it let the cache grow until the count was at the limit (99% eight times in five minutes, 850 MB free where no texture goes)
inline uint64_t reclaimable(uint64_t block_free, uint64_t pool_free) { return std::min(block_free, pool_free); }

/// The texture budget that holds the count, as it will be once a run has given `reclaim` back, at pct% of the allowance:
/// what the textures hold (total) less the excess, and never more than the budget was
inline uint64_t held_budget(uint64_t budget, uint64_t total, uint64_t used, uint64_t reclaim, uint64_t allowed, uint64_t pct) {
    const uint64_t line = allowed / 100 * pct;
    const uint64_t pressure = used - std::min(used, reclaim);
    if (!allowed || pressure <= line) return budget;
    const uint64_t over = pressure - line;
    return std::min(budget, total > over ? total - over : 0);
}

}   // namespace vram_compact
