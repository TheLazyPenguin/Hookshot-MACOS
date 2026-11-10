// (hookshot) AMD FidelityFX Super Resolution 3.1 (the FSR 3.1.4 upscaler of FidelityFX SDK v1.1.4) in place of OoT's
// gameplay upscale network, the same place NVIDIA DLSS takes (vk_dlss.h). Built from AMD's open shader sources
// (third_party/fidelityfx-sdk, compiled into gpu/vk/shaders by scripts/fsr3_shaders.py): every pass is a dispatch of ours,
// and nothing of AMD's is linked or loaded at run time, so it is in every build and runs on any GPU with what supported()
// asks for.
//
// The passes (namespace fsr3) take colour, depth and motion at the render size and write the picture at the output size.
// Those inputs are made in vk_fsr3_inputs.cpp; fsr3_upscale below is the dispatch's side: the network's input in, FSR's
// picture squared back into the network's output, as vk_dlss.cpp's dlss_out.comp does for DLSS.
//
// RX_VK_FSR=0: never (the row stays), =1: FSR 3.1 over the Insert menu's Upscaler row.
#pragma once

#include <cstdint>

#include "fsr3_math.h"
#include "vk_internal.h"

namespace mkwvk {

struct Texture;

namespace fsr3 {

/// One evaluation's inputs, in the SDK's meanings: the colour at the render size, the depth reversed, the motion toward the
/// frame before in render pixels without the jitter, and the jitter in render pixels (input texel k is sampled at
/// k + 0.5 - jitter)
struct Inputs {
    VkImageView color = VK_NULL_HANDLE;
    VkImageView depth = VK_NULL_HANDLE;
    VkImageView motion = VK_NULL_HANDLE;
    uint32_t render_width = 0, render_height = 0;
    uint32_t upscale_width = 0, upscale_height = 0;
    float jitter[2]{};
    uint32_t jitter_phases = 8;   ///< the length of the jitter's sequence (dlss_jitter_phases: the host's own)
    /// Turns a motion vector into render pixels (1 for vectors already in them)
    float motion_scale[2]{1.0f, 1.0f};
    fsr3_math::Camera camera;     ///< device_to_view_depth (fsr3_math.h)
    float frame_time_ms = 16.667f;
    bool reset = false;
};

/// Whether this device can run the passes: push descriptors enough for the widest pass, storage images in every format the
/// SDK's internal images use, the extended storage formats and storage writes without a format (the accumulate and RCAS
/// passes' output). Without subgroup quad operations in compute the two pyramids run as their wave-less variants. Asked
/// once; the reason it cannot is logged once
[[nodiscard]] bool supported();

/// Records one evaluation into output_image(), making the pipelines and the internal images at these sizes first (again
/// when they change). False when something could not be made or the inputs are not usable
[[nodiscard]] bool upscale(VkCommandBuffer cmd, const Inputs& in);

/// The image an evaluation resolves into: RGBA16F at the upscale size, or null before the first
[[nodiscard]] VkImage output_image();
[[nodiscard]] VkImageView output_view();

} // namespace fsr3

/// FSR 3.1 upscales: the Insert menu's Upscaler row says FSR 3.1 (upscaler_rows.h FSR3) and neither RX_VK_DLSS nor
/// RX_VK_FSR4 is set over it (vk_temporal.h temporal_env_chosen), or RX_VK_FSR=1; and it runs here
bool fsr3_wanted();

/// A gameplay upscale's dispatch, as vk_temporal.h's temporal_upscale takes it (vk_draw.cpp's fsr3_stand_in finds them the same
/// way). With FSR 3.1's frame interpolation on, the dispatch's input and this frame's camera become its inputs here
/// (vk_fsr3_inputs.h) whichever upscaler runs. true: FSR 3.1 wrote the output (the dispatch is left out); false: the network
/// (or DLSS) runs, the reason logged when it changes
bool fsr3_upscale(VkCommandBuffer cmd, uint64_t key, bool known, Texture* in, VkImageView in_view, Texture* out,
                  VkImageView out_view, uint32_t out_level);

} // namespace mkwvk
