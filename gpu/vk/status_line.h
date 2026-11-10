/* The renderer's status line (vk_replay.cpp status_tick): every 600 of the game's frames one line of what the video memory
   holds, with DLSS's details when it draws, and the warning when the use passes what the driver allows. Plain functions:
   tests/test_status_line.cpp checks them. */
#pragma once

#include <cstdint>
#include <cstdio>

namespace mkwvk::status_line {

constexpr int kEvery = 600;      // (the game's frames between two status lines)
constexpr int kCheckEvery = 60;  // (and between two looks at the allowance, for the warning)

inline double gb(uint64_t bytes) { return bytes / (1024.0 * 1024.0 * 1024.0); }

/// The video memory part: "VRAM 7.1 of 8.0 GB" (used of what the driver allows the game, VK_EXT_memory_budget), or without
/// a budget from the driver what the game's own allocations hold
inline int vram_text(char* b, size_t n, uint64_t used, uint64_t allowed, bool budget_known) {
    if (budget_known && allowed) return snprintf(b, n, "VRAM %.1f of %.1f GB", gb(used), gb(allowed));
    return snprintf(b, n, "VRAM %.1f GB in the game's allocations (no budget from the driver)", gb(used));
}

/// The warning's once and again: true the first time a reading is over the allowance, then not until a reading has been
/// back under it (over: the state between readings). Nothing known (allowed 0): under
inline bool crossed(bool& over, uint64_t used, uint64_t allowed) {
    const bool now = allowed && used > allowed;
    const bool tell = now && !over;
    over = now;
    return tell;
}

/// What the warning adds for the upscaler drawing (upscaler_rows.h: 1 DLSS, 2 DLAA, 4 FSR 4, 5 its native AA; 0 none: nothing)
inline const char* over_advice(int dlss_mode) {
    if (dlss_mode == 2) return ": DLAA may stutter here; Quality or Balanced uses less";
    if (dlss_mode == 1) return ": DLSS may stutter here; a lower Render resolution mode uses less";
    if (dlss_mode == 5) return ": FSR 4's native AA may stutter here; FSR 4's Quality or Balanced uses less";
    if (dlss_mode == 4) return ": FSR 4 may stutter here; a lower Render resolution mode uses less";
    return "";
}
inline int over_text(char* b, size_t n, uint64_t used, uint64_t allowed, int dlss_mode) {
    return snprintf(b, n, "vk: over the driver's video-memory allowance (%.1f of %.1f GB)%s", gb(used), gb(allowed),
                    over_advice(dlss_mode));
}

} // namespace mkwvk::status_line
