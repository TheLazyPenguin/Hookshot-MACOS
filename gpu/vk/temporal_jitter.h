// The upscaler's jitter metadata crosses from replay to the game thread. Keep its lock separate from GPU/NGX work.
#pragma once

#include <mutex>

#include "vk_api.h"

namespace mkwvk {

class TemporalJitter {
    std::mutex mu;
    MkwVkJitter sample{};
    uint64_t frame = 0;

public:
    void publish(uint32_t width, uint32_t height, uint32_t phases, uint64_t at) {
        std::lock_guard lock(mu);
        sample = width && height && phases ? MkwVkJitter{width, height, phases} : MkwVkJitter{};
        frame = at;
    }

    MkwVkJitter read(uint64_t now) {
        std::lock_guard lock(mu);
        return frame && now - frame <= 30 ? sample : MkwVkJitter{};
    }
};

} // namespace mkwvk
