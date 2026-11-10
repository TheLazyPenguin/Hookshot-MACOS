// The content rectangle for a window present, independent of Vulkan.
#pragma once

#include <cstdint>
#include <limits>

namespace mkwvk {

struct PresentSourceRect {
    uint32_t x, y, w, h;
};

// Vulkan blit offsets and the interpolation copy shader use signed 32-bit coordinates.
// A nonpositive crop extent keeps the existing full-image convention; an invalid origin is empty.
constexpr PresentSourceRect present_source_rect(uint32_t sw, uint32_t sh, const int crop[4]) noexcept {
    if (!sw || !sh || sw > INT32_MAX || sh > INT32_MAX) return {0, 0, 0, 0};
    if (!crop || crop[2] <= 0 || crop[3] <= 0) return {0, 0, sw, sh};
    if (crop[0] < 0 || crop[1] < 0 || (uint32_t)crop[0] >= sw || (uint32_t)crop[1] >= sh) return {0, 0, 0, 0};
    const uint32_t available_w = sw - (uint32_t)crop[0];
    const uint32_t available_h = sh - (uint32_t)crop[1];
    const uint32_t crop_w = (uint32_t)crop[2];
    const uint32_t crop_h = (uint32_t)crop[3];
    return {(uint32_t)crop[0], (uint32_t)crop[1], crop_w < available_w ? crop_w : available_w,
            crop_h < available_h ? crop_h : available_h};
}

struct PresentRect {
    uint32_t x, y, w, h;
};

struct PresentContentSize {
    uint32_t w, h;
};

// Display aspect of the presented (cropped) picture, not necessarily its texture's
// pixel aspect. Zero/invalid means square pixels, using the source content size.
struct PresentAspect {
    double ratio = 0;
};

constexpr PresentContentSize present_content_size(uint32_t sw, uint32_t sh, const int crop[4]) noexcept {
    const PresentSourceRect source = present_source_rect(sw, sh, crop);
    return {source.w, source.h};
}

constexpr PresentRect present_rect(uint32_t sw, uint32_t sh, const int crop[4], uint32_t dw, uint32_t dh,
                                   PresentAspect aspect = {}) noexcept {
    if (!dw || !dh) return {0, 0, dw, dh};
    const PresentContentSize content = present_content_size(sw, sh, crop);
    if (!content.w || !content.h) return {0, 0, dw, dh};

    if (aspect.ratio > 0 && aspect.ratio < std::numeric_limits<double>::infinity()) {
        // Compare ratios before multiplying: even extreme finite aspect values
        // must not overflow a float-to-integer conversion. Round to the nearest
        // pixel so a float camera ratio does not add a one-pixel bar at its own size.
        if (static_cast<double>(dw) / dh > aspect.ratio) {
            const uint32_t rounded = static_cast<uint32_t>(dh * aspect.ratio + 0.5);
            const uint32_t w = rounded ? rounded : 1;
            return {(dw - w) / 2, 0, w, dh};
        }
        const uint32_t rounded = static_cast<uint32_t>(dw / aspect.ratio + 0.5);
        const uint32_t h = rounded ? rounded : 1;
        return {0, (dh - h) / 2, dw, h};
    }

    // Fit the source content into the destination while preserving its aspect.
    if ((uint64_t)dw * content.h > (uint64_t)dh * content.w) {
        const uint32_t w = (uint32_t)((uint64_t)dh * content.w / content.h);
        return {(dw - w) / 2, 0, w ? w : 1, dh};
    }
    const uint32_t h = (uint32_t)((uint64_t)dw * content.h / content.w);
    return {0, (dh - h) / 2, dw, h ? h : 1};
}

}  // namespace mkwvk
