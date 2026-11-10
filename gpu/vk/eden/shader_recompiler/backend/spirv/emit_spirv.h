// SPDX-FileCopyrightText: Copyright 2026 Eden Emulator Project
// SPDX-License-Identifier: GPL-3.0-or-later

// SPDX-FileCopyrightText: Copyright 2021 yuzu Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

#include <vector>

#include "common/common_types.h"
#include "shader_recompiler/backend/bindings.h"
#include "shader_recompiler/frontend/ir/program.h"
#include "shader_recompiler/profile.h"
#include "shader_recompiler/runtime_info.h"

namespace Shader::Backend::SPIRV {

constexpr u32 NUM_TEXTURE_SCALING_WORDS = 4;
constexpr u32 NUM_IMAGE_SCALING_WORDS = 2;
constexpr u32 NUM_TEXTURE_AND_IMAGE_SCALING_WORDS =
    NUM_TEXTURE_SCALING_WORDS + NUM_IMAGE_SCALING_WORDS;

struct RescalingLayout {
    alignas(16) std::array<u32, NUM_TEXTURE_SCALING_WORDS> rescaling_textures;
    alignas(16) std::array<u32, NUM_IMAGE_SCALING_WORDS> rescaling_images;
    u32 down_factor;
};
struct RenderAreaLayout {
    std::array<f32, 4> render_area;
};
constexpr u32 RESCALING_LAYOUT_WORDS_OFFSET = offsetof(RescalingLayout, rescaling_textures);
constexpr u32 RESCALING_LAYOUT_DOWN_FACTOR_OFFSET = offsetof(RescalingLayout, down_factor);
constexpr u32 RENDERAREA_LAYOUT_OFFSET = offsetof(RenderAreaLayout, render_area);
// (hookshot) guest memory's page table, a u64 device address pushed to every compute program that reads global memory, after the blocks
// above. It was a constant in the SPIR-V, and the address changes from run to run: the drivers' pipeline caches never hit
constexpr u32 GUEST_PAGES_PUSH_OFFSET = sizeof(RescalingLayout) + sizeof(RenderAreaLayout);
// (hookshot) a task program's first workgroup: NVN draws tasks [first, first + count), Vulkan from 0. The address of the draw's first
// (a u32, 16 bytes per draw of an indirect draw, read at + DrawIndex * 16) is pushed here
constexpr u32 MESH_FIRST_PUSH_OFFSET = GUEST_PAGES_PUSH_OFFSET + 8;
// (hookshot) the mesh shader fallback's buffers, after it: the task payloads and the vertex records (u64 device addresses).
// Paths without the fallback never push them.
constexpr u32 MESH_FALLBACK_PUSH_OFFSET = MESH_FIRST_PUSH_OFFSET + 8;
constexpr u32 MESH_FALLBACK_PAYLOAD_PUSH_OFFSET = MESH_FALLBACK_PUSH_OFFSET;
constexpr u32 MESH_FALLBACK_RECORDS_PUSH_OFFSET = MESH_FALLBACK_PUSH_OFFSET + 8;
constexpr u32 MESH_FALLBACK_INDIRECT_INPUT_PUSH_OFFSET = MESH_FALLBACK_PUSH_OFFSET + 16;
constexpr u32 MESH_FALLBACK_PUSH_END = MESH_FALLBACK_PUSH_OFFSET + 24;
// (hookshot) the fallback's mesh workgroups a draw can run: each a slot, a word of the payload buffer saying whether its task
// started it; then each task workgroup's payload. It was 1024, a record block each, and Ocarina's floor grass (433 tasks of
// 32 slots) lost 13 of 14 meshlets. At 16384, Hyrule Field's far trees (3cb76827/4f0c0b40: 721 tasks of 32) lost the tasks
// past 512, a different set each frame as the culling's list order changes: they flickered. 65535: Vulkan's least
// maxComputeWorkGroupCount, which the mesh dispatch can reach; the payload buffer is ~6.5 MB a recording thread at 800 words.
constexpr u32 MESH_FALLBACK_CAPACITY = 65535;
// (hookshot) the records buffer: a VkDrawIndirectCommand the vertex stage's draw reads (its vertex count the records written),
// the allocator's word, then the records. A mesh workgroup takes records for its primitives' corners only, so a draw covers
// what was drawn, not every slot's maximum
constexpr u32 MESH_FALLBACK_DRAW_WORD = 0;        // (vertexCount; instanceCount at word 1, set to 1 by the host)
constexpr u32 MESH_FALLBACK_ALLOC_WORD = 4;       // (records taken, past the end too: those that do not fit are not drawn)
// (a VkDispatchIndirectCommand for the mesh workgroups a task program started (y and z 1, set by the host): each started task
// thread takes an index of it and writes its slot there in the payload buffer's map, so the mesh dispatch runs only those. With
// a count from the GPU (DrawMeshTasksIndirect, the floor grass) the host knew none, and dispatched no mesh workgroup)
constexpr u32 MESH_FALLBACK_DISPATCH_WORD = 5;
constexpr u32 MESH_FALLBACK_HEADER_WORDS = 8;
constexpr u32 MESH_FALLBACK_RECORD_WORDS = 16u << 20;   // (64 MB: ~47k grass primitives of 31 words are 17 MB)

[[nodiscard]] std::vector<u32> EmitSPIRV(const Profile& profile, const RuntimeInfo& runtime_info, IR::Program& program, Bindings& bindings);
[[nodiscard]] inline std::vector<u32> EmitSPIRV(const Profile& profile, IR::Program& program) {
    Bindings binding;
    return EmitSPIRV(profile, {}, program, binding);
}

} // namespace Shader::Backend::SPIRV
