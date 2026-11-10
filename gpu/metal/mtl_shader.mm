// Metal shader translation and pipeline state object management.
#include "mtl_shader.h"

#include <cstdio>
#include <cstring>
#include <dirent.h>
#include <fstream>
#include <sstream>
#include <sys/stat.h>
#include <unistd.h>

#include "../../third_party/spirv-cross/spirv_msl.hpp"

namespace mkwmtl {

CompiledMSL translate_spirv_to_msl(const uint32_t* spirv_words, size_t word_count, ShaderType type) {
    CompiledMSL res;
    if (!spirv_words || word_count == 0) {
        res.error = "SPIR-V words buffer is empty";
        return res;
    }

    try {
        spirv_cross::CompilerMSL msl(spirv_words, word_count);

        spirv_cross::CompilerMSL::Options options;
        options.set_msl_version(2, 3); // Metal 2.3+ for Apple Silicon
        options.enable_decoration_binding = true;
        options.pad_fragment_output_components = true;
        msl.set_msl_options(options);

        res.source = msl.compile();
        res.entry_point = "main0";
        res.ok = true;
    } catch (const std::exception& e) {
        res.error = e.what();
        res.ok = false;
    }

    return res;
}

#ifdef __APPLE__

MetalPipelineCache& MetalPipelineCache::instance() {
    static MetalPipelineCache s_cache;
    return s_cache;
}

void MetalPipelineCache::init(id<MTLDevice> device, const std::string& disk_cache_dir) {
    std::lock_guard<std::mutex> lock(mu_);
    device_ = device;
    cache_dir_ = disk_cache_dir;

    if (!cache_dir_.empty()) {
        mkdir(cache_dir_.c_str(), 0755);
    }
}

void MetalPipelineCache::save_msl_to_disk(uint64_t hash, const std::string& msl_code) {
    if (cache_dir_.empty()) return;
    char path[512];
    snprintf(path, sizeof path, "%s/%016llx.msl", cache_dir_.c_str(), (unsigned long long)hash);
    std::ofstream out(path);
    if (out.is_open()) {
        out << msl_code;
    }
}

std::string MetalPipelineCache::load_msl_from_disk(uint64_t hash) {
    if (cache_dir_.empty()) return "";
    char path[512];
    snprintf(path, sizeof path, "%s/%016llx.msl", cache_dir_.c_str(), (unsigned long long)hash);
    std::ifstream in(path);
    if (!in.is_open()) return "";
    std::stringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

id<MTLLibrary> MetalPipelineCache::compile_msl(const std::string& msl_code, uint64_t hash) {
    if (!device_ || msl_code.empty()) return nil;

    @autoreleasepool {
        NSString* src = [NSString stringWithUTF8String:msl_code.c_str()];
        MTLCompileOptions* opts = [[MTLCompileOptions alloc] init];
        opts.languageVersion = MTLLanguageVersion2_3;
        opts.fastMathEnabled = YES;

        NSError* err = nil;
        id<MTLLibrary> lib = [device_ newLibraryWithSource:src options:opts error:&err];
        if (err || !lib) {
            NSLog(@"[Metal] Failed to compile MSL for hash %016llx: %@", (unsigned long long)hash, err);
            return nil;
        }

        save_msl_to_disk(hash, msl_code);
        return lib;
    }
}

id<MTLComputePipelineState> MetalPipelineCache::get_or_create_compute(
    const uint32_t* spirv_words, size_t word_count, uint64_t shader_hash) {
    std::lock_guard<std::mutex> lock(mu_);
    if (!device_) return nil;

    auto it = compute_cache_.find(shader_hash);
    if (it != compute_cache_.end()) {
        return it->second;
    }

    std::string msl_code = load_msl_from_disk(shader_hash);
    if (msl_code.empty()) {
        CompiledMSL compiled = translate_spirv_to_msl(spirv_words, word_count, ShaderType::Compute);
        if (!compiled.ok) {
            NSLog(@"[Metal] SPIR-V to MSL compute translation failed for %016llx: %s",
                  (unsigned long long)shader_hash, compiled.error.c_str());
            return nil;
        }
        msl_code = std::move(compiled.source);
    }

    id<MTLLibrary> lib = compile_msl(msl_code, shader_hash);
    if (!lib) return nil;

    @autoreleasepool {
        id<MTLFunction> fn = [lib newFunctionWithName:@"main0"];
        if (!fn) {
            NSLog(@"[Metal] Entry point 'main0' not found in compute shader %016llx", (unsigned long long)shader_hash);
            return nil;
        }

        NSError* err = nil;
        id<MTLComputePipelineState> pso = [device_ newComputePipelineStateWithFunction:fn error:&err];
        if (err || !pso) {
            NSLog(@"[Metal] Failed to create compute PSO for %016llx: %@", (unsigned long long)shader_hash, err);
            return nil;
        }

        compute_cache_[shader_hash] = pso;
        return pso;
    }
}

id<MTLRenderPipelineState> MetalPipelineCache::get_or_create_render(
    const uint32_t* vs_words, size_t vs_count, uint64_t vs_hash,
    const uint32_t* fs_words, size_t fs_count, uint64_t fs_hash,
    MTLPixelFormat color_format, MTLPixelFormat depth_format) {
    std::lock_guard<std::mutex> lock(mu_);
    if (!device_) return nil;

    PipelineKey key{vs_hash, fs_hash, (uint32_t)color_format, (uint32_t)depth_format};
    auto it = render_cache_.find(key);
    if (it != render_cache_.end()) {
        return it->second;
    }

    // Compile Vertex Shader
    std::string vs_msl = load_msl_from_disk(vs_hash);
    if (vs_msl.empty() && vs_words && vs_count > 0) {
        CompiledMSL compiled = translate_spirv_to_msl(vs_words, vs_count, ShaderType::Vertex);
        if (compiled.ok) {
            vs_msl = std::move(compiled.source);
        } else {
            NSLog(@"[Metal] SPIR-V to MSL vertex translation failed for %016llx: %s",
                  (unsigned long long)vs_hash, compiled.error.c_str());
            return nil;
        }
    }
    id<MTLLibrary> vs_lib = compile_msl(vs_msl, vs_hash);
    if (!vs_lib) return nil;

    // Compile Fragment Shader (if provided)
    id<MTLLibrary> fs_lib = nil;
    if (fs_words && fs_count > 0) {
        std::string fs_msl = load_msl_from_disk(fs_hash);
        if (fs_msl.empty()) {
            CompiledMSL compiled = translate_spirv_to_msl(fs_words, fs_count, ShaderType::Fragment);
            if (compiled.ok) {
                fs_msl = std::move(compiled.source);
            } else {
                NSLog(@"[Metal] SPIR-V to MSL fragment translation failed for %016llx: %s",
                      (unsigned long long)fs_hash, compiled.error.c_str());
                return nil;
            }
        }
        fs_lib = compile_msl(fs_msl, fs_hash);
    }

    @autoreleasepool {
        id<MTLFunction> vs_fn = [vs_lib newFunctionWithName:@"main0"];
        id<MTLFunction> fs_fn = fs_lib ? [fs_lib newFunctionWithName:@"main0"] : nil;

        if (!vs_fn) {
            NSLog(@"[Metal] Vertex entry point 'main0' not found for %016llx", (unsigned long long)vs_hash);
            return nil;
        }

        MTLRenderPipelineDescriptor* desc = [[MTLRenderPipelineDescriptor alloc] init];
        desc.vertexFunction = vs_fn;
        desc.fragmentFunction = fs_fn;

        if (color_format != MTLPixelFormatInvalid) {
            desc.colorAttachments[0].pixelFormat = color_format;
        }
        if (depth_format != MTLPixelFormatInvalid) {
            desc.depthAttachmentPixelFormat = depth_format;
        }

        NSError* err = nil;
        id<MTLRenderPipelineState> pso = [device_ newRenderPipelineStateWithDescriptor:desc error:&err];
        if (err || !pso) {
            NSLog(@"[Metal] Failed to create render PSO (vs: %016llx, fs: %016llx): %@",
                  (unsigned long long)vs_hash, (unsigned long long)fs_hash, err);
            return nil;
        }

        render_cache_[key] = pso;
        return pso;
    }
}

size_t MetalPipelineCache::prewarm_cache_from_disk() {
    std::lock_guard<std::mutex> lock(mu_);
    if (!device_ || cache_dir_.empty()) return 0;
    size_t count = 0;
    DIR* dir = opendir(cache_dir_.c_str());
    if (!dir) return 0;
    struct dirent* ent = nullptr;
    while ((ent = readdir(dir)) != nullptr) {
        const char* name = ent->d_name;
        size_t len = strlen(name);
        if (len > 4 && strcmp(name + len - 4, ".msl") == 0) {
            char path[512];
            snprintf(path, sizeof path, "%s/%s", cache_dir_.c_str(), name);
            std::ifstream in(path);
            if (in.is_open()) {
                std::stringstream ss;
                ss << in.rdbuf();
                std::string msl = ss.str();
                uint64_t hash = 0;
                try {
                    hash = std::stoull(name, nullptr, 16);
                } catch (...) {}
                if (compile_msl(msl, hash)) {
                    count++;
                }
            }
        }
    }
    closedir(dir);
    return count;
}

#endif // __APPLE__

} // namespace mkwmtl
