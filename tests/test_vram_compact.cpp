// The compaction's rules (gpu/vk/vram_compact.h): tests/test_vram_compact.py compiles and runs this.
#include "../gpu/vk/vram_compact.h"

#include <cstdio>
#include <cstdlib>

#define CHECK(x) do { if (!(x)) { std::printf("FAIL line %d: %s\n", __LINE__, #x); std::exit(1); } } while (0)

int main() {
    using namespace vram_compact;
    const uint64_t MB = 1ull << 20;
    // pressed: the driver's count over 90% of what it allows; never without an allowance
    CHECK(!pressed(9000 * MB, 10900 * MB));
    CHECK(pressed(10023 * MB, 10900 * MB));   // (the uncompacted walk's count)
    CHECK(!pressed(10023 * MB, 0));
    // a run starts for RX_VK_COMPACT_MB of free space, for 192 MB while pressed, and never for more than was asked
    CHECK(run_from(512 * MB, false) == 512 * MB);
    CHECK(run_from(512 * MB, true) == 192 * MB);
    CHECK(run_from(64 * MB, true) == 64 * MB);
    CHECK(rest(false) == 600 && rest(true) == 120);
    // only the textures' pool's free space comes off the count
    CHECK(reclaimable(850 * MB, 215 * MB) == 215 * MB);    // (the rest is in the render targets' and the buffers' blocks)
    CHECK(reclaimable(100 * MB, 215 * MB) == 100 * MB);    // (never more than the blocks hold free in all)
    // the budget holds the count, less what a run gives back, at pct% of the allowance
    const uint64_t allowed = 10900 * MB, budget = 6144 * MB;
    CHECK(held_budget(budget, 5000 * MB, 9000 * MB, 200 * MB, allowed, 85) == budget);   // (8,800 of 9,265: under the line)
    CHECK(held_budget(budget, 5600 * MB, 10023 * MB, 215 * MB, allowed, 85) == 5600 * MB - (10023 - 215 - 9265) * MB);
    CHECK(held_budget(budget, 5600 * MB, 10023 * MB, 215 * MB, allowed, 90) == budget);   // (9,808 of 9,810: at 90 that count is let be)
    CHECK(held_budget(budget, 5600 * MB, 10323 * MB, 215 * MB, allowed, 90) == 5600 * MB - (10323 - 215 - 9810) * MB);
    CHECK(held_budget(4096 * MB, 5600 * MB, 10023 * MB, 215 * MB, allowed, 85) == 4096 * MB);   // (never more than it was)
    CHECK(held_budget(budget, 300 * MB, 10800 * MB, 0, allowed, 85) == 0);                      // (the excess is more than the textures hold)
    CHECK(held_budget(budget, 5600 * MB, 10023 * MB, 215 * MB, 0, 85) == budget);               // (no allowance known: left alone)
    CHECK(held_budget(budget, 5600 * MB, 100 * MB, 215 * MB, allowed, 85) == budget);           // (more to give back than is used)
    std::printf("PASS: the compaction's rules\n");
    return 0;
}
