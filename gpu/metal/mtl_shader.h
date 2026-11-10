// Metal shader translation and pipeline state object management.
// Translates SPIR-V binary from Eden into Metal Shading Language (MSL) via SPIRV-Cross,
// compiles MSL into MTLLibrary and MTLRenderPipelineState/MTLComputePipelineState,
// and caches compiled pipelines to disk.
#pragma once

#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>
#include <mutex>

#ifdef __APPLE__
#import <Metal/Metal.h>
#else
typedef void* id;
#endif

namespace mkwmtl {

enum class ShaderType {
    Vertex,
    Fragment,
    Compute,
};

struct CompiledMSL {
    std::string source;
    std::string entry_point;
    bool ok = false;
    std::string error;
};

// Translates a SPIR-V binary module into Metal Shading Language (MSL).
CompiledMSL translate_spirv_to_msl(const uint32_t* spirv_words, size_t word_count, ShaderType type);

#ifdef __APPLE__

struct PipelineKey {
    uint64_t vs_hash = 0;
    uint64_t fs_hash = 0;
    uint32_t color_format = 0;
    uint32_t depth_format = 0;

    bool operator==(const PipelineKey& o) const {
        return vs_hash == o.vs_hash && fs_hash == o.fs_hash &&
               color_format == o.color_format && depth_format == o.depth_format;
    }
};

struct PipelineKeyHash {
    size_t operator()(const PipelineKey& k) const noexcept {
        return (size_t)k.vs_hash ^ ((size_t)k.fs_hash << 1) ^
               ((size_t)k.color_format << 16) ^ ((size_t)k.depth_format << 24);
    }
};

class MetalPipelineCache {
public:
    static MetalPipelineCache& instance();

    void init(id<MTLDevice> device, const std::string& disk_cache_dir);

    // Compile or retrieve a cached compute pipeline
    id<MTLComputePipelineState> get_or_create_compute(
        const uint32_t* spirv_words, size_t word_count, uint64_t shader_hash);

    // Compile or retrieve a cached render pipeline
    id<MTLRenderPipelineState> get_or_create_render(
        const uint32_t* vs_words, size_t vs_count, uint64_t vs_hash,
        const uint32_t* fs_words, size_t fs_count, uint64_t fs_hash,
        MTLPixelFormat color_format, MTLPixelFormat depth_format);

private:
    id<MTLDevice> device_ = nil;
    std::string cache_dir_;
    std::mutex mu_;

    std::unordered_map<PipelineKey, id<MTLRenderPipelineState>, PipelineKeyHash> render_cache_;
    std::unordered_map<uint64_t, id<MTLComputePipelineState>> compute_cache_;

    id<MTLLibrary> compile_msl(const std::string& msl_code, uint64_t hash);
    void save_msl_to_disk(uint64_t hash, const std::string& msl_code);
    std::string load_msl_from_disk(uint64_t hash);
};

#endif // __APPLE__

} // namespace mkwmtl
