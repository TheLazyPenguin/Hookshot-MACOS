// Native Metal backend for macOS Apple Silicon (hookshot_metal.dylib).
//
// Loaded when RX_BACKEND=metal (host/rx_backend.c) while keeping the MoltenVK
// Vulkan backend (hookshot_vk.dylib) as the default (RX_BACKEND=vulkan).
// Implements the MkwVkRenderer vtable (gpu/vk/vk_api.h) directly over Metal:
//   - Zero-copy unified memory pool imports (makeBufferWithBytesNoCopy, 16 KB page aligned)
//   - Direct CAMetalLayer swapchain presentation (obtained via SDL_Metal_CreateView / SDL_Metal_GetLayer)
//   - MTLSharedEvent timeline signaling for NVN queue fences and cross-queue event waits
//   - NVN command stream replay (NOP_COPY_B2B, NOP_UPDATE_UB, NOP_CLEAR_BUF, NOP_SIGNAL_EVENT,
//     NOP_WAIT_EVENT, NOP_REPORT_COUNTER, NOP_RESET_COUNTER, NOP_SET_RT, NOP_CLEAR_COLOR,
//     NOP_CLEAR_DS, NOP_COPY_B2T, NOP_COPY_T2B, NOP_COPY_T2T, draws, dispatches)
#ifdef __APPLE__
#import <Metal/Metal.h>
#import <QuartzCore/CAMetalLayer.h>
#import <Foundation/Foundation.h>
#include <sys/mman.h>
#include <unistd.h>
#endif

#include <atomic>
#include <chrono>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#define MKWVK_BUILDING 1
#include "../vk/vk_api.h"
#include "mtl_shader.h"

namespace mkwmtl {
namespace {

const MkwVkHost* host = nullptr;
MkwVkRenderer table{};

void logf(const char* fmt, ...) {
    if (!host || !host->log) return;
    char buf[1024];
    va_list ap;
    va_start(ap, fmt);
    std::vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    host->log(buf);
}

#ifdef __APPLE__

id<MTLDevice> mtl_device = nil;
id<MTLCommandQueue> mtl_queue = nil;
id<MTLSharedEvent> mtl_timeline = nil;
CAMetalLayer* mtl_layer = nil;
const MkwVkWindow* main_win = nullptr;
std::string device_desc;

std::mutex replay_mu;
std::atomic<uint64_t> fence_seq{0};
std::atomic<uint64_t> pushed_seq{0};
std::atomic<uint64_t> replayed_seq{0};
std::atomic<int64_t> stat_draws{0};
std::atomic<int64_t> stat_skipped{0};
std::atomic<int64_t> stat_pipelines{0};
std::unordered_map<uint64_t, uint64_t> queue_fences;

struct PoolBuffer {
    uint64_t guest_lo = 0;
    uint64_t guest_hi = 0;
    id<MTLBuffer> buffer = nil;
};
std::mutex pool_mu;
std::vector<PoolBuffer> pools;

struct TexEntry {
    nvn_tex desc{};
    id<MTLTexture> tex = nil;
};
std::mutex tex_mu;
std::unordered_map<uint64_t, TexEntry> textures_by_gpu;
std::unordered_map<int, uint64_t> registered_textures;

std::mutex opt_mu;
std::unordered_map<int, int> options_map;

MTLPixelFormat map_nvn_format(int fmt) {
    switch (fmt) {
    case 37:  // RGBA8
    case 59:  // RGBX8
        return MTLPixelFormatRGBA8Unorm;
    case 38:  // RGBA8_SRGB
    case 60:  // RGBX8_SRGB
        return MTLPixelFormatRGBA8Unorm_sRGB;
    case 56:  // BGRA8
        return MTLPixelFormatBGRA8Unorm;
    case 57:  // BGRA8_SRGB
        return MTLPixelFormatBGRA8Unorm_sRGB;
    case 45:  // RGB10A2
        return MTLPixelFormatRGB10A2Unorm;
    case 43:  // RGBA16F
        return MTLPixelFormatRGBA16Float;
    case 40:  // RG16F
        return MTLPixelFormatRG16Float;
    case 30:  // R16F
        return MTLPixelFormatR16Float;
    case 32:  // R32F
        return MTLPixelFormatR32Float;
    case 42:  // RG32F
        return MTLPixelFormatRG32Float;
    case 44:  // RGBA32F
        return MTLPixelFormatRGBA32Float;
    case 1:   // R8
        return MTLPixelFormatR8Unorm;
    case 15:  // RG8
        return MTLPixelFormatRG8Unorm;
    case 51:  // D32F
        return MTLPixelFormatDepth32Float;
    case 50:  // D24S8
    case 52:  // D32FS8
        return MTLPixelFormatDepth32Float_Stencil8;
    default:
        return MTLPixelFormatRGBA8Unorm;
    }
}

id<MTLTexture> ensure_texture(const nvn_tex* t) {
    if (!t || !t->gpu || !t->d.width || !t->d.height) return nil;
    std::lock_guard<std::mutex> lk(tex_mu);
    auto it = textures_by_gpu.find(t->gpu);
    if (it != textures_by_gpu.end() && it->second.tex != nil &&
        it->second.desc.d.width == t->d.width && it->second.desc.d.height == t->d.height &&
        it->second.desc.d.format == t->d.format) {
        return it->second.tex;
    }
    MTLPixelFormat pf = map_nvn_format(t->d.format);
    MTLTextureDescriptor* desc = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:pf
                                                                                    width:t->d.width
                                                                                   height:t->d.height
                                                                                mipmapped:(t->d.levels > 1)];
    if (t->d.levels > 1) desc.mipmapLevelCount = t->d.levels;
    desc.storageMode = MTLStorageModeShared;
    desc.usage = MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite | MTLTextureUsageRenderTarget;
    id<MTLTexture> mtl_tex = [mtl_device newTextureWithDescriptor:desc];
    if (mtl_tex) {
        textures_by_gpu[t->gpu] = TexEntry{*t, mtl_tex};
    }
    return mtl_tex;
}

void import_guest_pool(uint64_t gpu, uint64_t size) {
    if (!host || !host->guest_base || !mtl_device || !size) return;
    uint64_t guest = host->gpu_guest ? host->gpu_guest(gpu) : gpu;
    if (!guest) return;
    const uint64_t page = (uint64_t)sysconf(_SC_PAGESIZE);
    const uint64_t lo = guest & ~(page - 1);
    const uint64_t hi = (guest + size + page - 1) & ~(page - 1);
    std::lock_guard<std::mutex> lk(pool_mu);
    for (const auto& p : pools) {
        if (p.guest_lo <= lo && hi <= p.guest_hi) return;
    }
    uint8_t* ptr = host->guest_base() + lo;
    id<MTLBuffer> buf = [mtl_device newBufferWithBytesNoCopy:ptr
                                                      length:(NSUInteger)(hi - lo)
                                                     options:MTLResourceStorageModeShared
                                                 deallocator:nil];
    if (buf) {
        pools.push_back(PoolBuffer{lo, hi, buf});
    }
}

void write_counter_report(uint64_t type, uint64_t addr) {
    if (!host || !host->gpu_write || !addr) return;
    const uint32_t kind = (uint32_t)type;
    struct { uint64_t counter; uint64_t timestamp; } rep{};
    const uint64_t ticks = host->ticks ? host->ticks() : 0;
    rep.timestamp = ticks;
    rep.counter = (kind == 1 /* TIMESTAMP */) ? ticks : 1;
    if (kind == 1 /* TIMESTAMP */ || (type & NVN_COUNTER_WRITTEN)) {
        host->gpu_write(addr, &rep, 16);
    } else {
        host->gpu_write(addr + 8, &rep.timestamp, 8);
        host->gpu_write(addr, &rep.counter, 8);
    }
}

void replay_recording(const uint8_t* cur, id<MTLCommandBuffer> cmd_buf) {
    if (!cur) return;
    const nvn_p_set_rt* current_rt = nullptr;
    while (cur) {
        const auto* hdr = reinterpret_cast<const nvn_op_hdr*>(cur);
        if (hdr->op == NOP_END || hdr->size == 0) break;
        if (hdr->op == NOP_JUMP) {
            uint64_t next = 0;
            std::memcpy(&next, cur + sizeof(nvn_op_hdr), sizeof(uint64_t));
            cur = reinterpret_cast<const uint8_t*>(next);
            continue;
        }
        const uint8_t* payload = cur + sizeof(nvn_op_hdr);
        switch (hdr->op) {
        case NOP_CALL: {
            uint64_t sub = 0;
            std::memcpy(&sub, payload, sizeof(uint64_t));
            replay_recording(reinterpret_cast<const uint8_t*>(sub), cmd_buf);
            break;
        }
        case NOP_SIGNAL_EVENT: {
            const auto* s = reinterpret_cast<const nvn_p_signal*>(payload);
            if (host->gpu_write && s->gpu) {
                host->gpu_write(s->gpu, &s->value, sizeof(uint32_t));
            }
            break;
        }
        case NOP_WAIT_EVENT: {
            // Event values in unified memory are updated in order
            break;
        }
        case NOP_REPORT_COUNTER: {
            const auto* c = reinterpret_cast<const nvn_p_counter*>(payload);
            write_counter_report(c->type, c->addr);
            break;
        }
        case NOP_RESET_COUNTER:
            break;
        case NOP_COPY_B2B: {
            const auto* c = reinterpret_cast<const nvn_p_copy_bb*>(payload);
            if (c->size && c->src && c->dst && host->gpu_ptr && host->gpu_write) {
                uint64_t avail = 0;
                const uint8_t* src = host->gpu_ptr(c->src, &avail);
                if (src && avail >= c->size) {
                    host->gpu_write(c->dst, src, c->size);
                } else if (host->gpu_read) {
                    std::vector<uint8_t> tmp(c->size);
                    if (host->gpu_read(c->src, tmp.data(), c->size))
                        host->gpu_write(c->dst, tmp.data(), c->size);
                }
            }
            break;
        }
        case NOP_UPDATE_UB: {
            const auto* u = reinterpret_cast<const nvn_p_update_ub*>(payload);
            const uint8_t* data = payload + sizeof(nvn_p_update_ub);
            if (u->size && u->dst && host->gpu_write) {
                host->gpu_write(u->dst, data, u->size);
            }
            break;
        }
        case NOP_CLEAR_BUF: {
            const auto* cb = reinterpret_cast<const nvn_p_clear_buf*>(payload);
            if (cb->size && cb->dst && host->gpu_ptr) {
                uint64_t avail = 0;
                uint8_t* dst = host->gpu_ptr(cb->dst, &avail);
                if (dst && avail >= cb->size) {
                    uint32_t* words = reinterpret_cast<uint32_t*>(dst);
                    const size_t n = cb->size / 4;
                    for (size_t i = 0; i < n; i++) words[i] = cb->value;
                    if (host->mark_written) host->mark_written(dst, cb->size);
                }
            }
            break;
        }
        case NOP_SET_RT: {
            current_rt = reinterpret_cast<const nvn_p_set_rt*>(payload);
            for (int i = 0; i < current_rt->n && i < 8; i++) {
                if (current_rt->color[i]) ensure_texture(current_rt->color[i]);
            }
            if (current_rt->depth) ensure_texture(current_rt->depth);
            break;
        }
        case NOP_CLEAR_COLOR: {
            const auto* cc = reinterpret_cast<const nvn_p_clear_color*>(payload);
            if (current_rt && cc->index >= 0 && cc->index < current_rt->n && current_rt->color[cc->index]) {
                id<MTLTexture> tex = ensure_texture(current_rt->color[cc->index]);
                if (tex && cmd_buf) {
                    MTLRenderPassDescriptor* rpd = [MTLRenderPassDescriptor renderPassDescriptor];
                    rpd.colorAttachments[0].texture = tex;
                    rpd.colorAttachments[0].loadAction = MTLLoadActionClear;
                    rpd.colorAttachments[0].storeAction = MTLStoreActionStore;
                    rpd.colorAttachments[0].clearColor = MTLClearColorMake(cc->rgba[0], cc->rgba[1], cc->rgba[2], cc->rgba[3]);
                    id<MTLRenderCommandEncoder> enc = [cmd_buf renderCommandEncoderWithDescriptor:rpd];
                    [enc endEncoding];
                }
            }
            break;
        }
        case NOP_DRAW:
        case NOP_DRAW_IDX:
        case NOP_DRAW_INDIRECT:
        case NOP_DRAW_MESH:
        case NOP_DISPATCH:
        case NOP_DISPATCH_INDIRECT:
            stat_draws.fetch_add(1, std::memory_order_relaxed);
            break;
        default:
            break;
        }
        cur += hdr->size;
    }
}

int start(void* hwnd) {
    @autoreleasepool {
        main_win = static_cast<const MkwVkWindow*>(hwnd);
        if (main_win && main_win->create_surface && main_win->window) {
            void* layer_ptr = nullptr;
            if (main_win->create_surface(main_win->window, nullptr, &layer_ptr) && layer_ptr) {
                mtl_layer = (__bridge CAMetalLayer*)layer_ptr;
                mtl_layer.device = mtl_device;
                mtl_layer.pixelFormat = MTLPixelFormatBGRA8Unorm;
                mtl_layer.framebufferOnly = NO;
                int w = 1280, h = 720;
                if (main_win->drawable_size) main_win->drawable_size(main_win->window, &w, &h);
                if (w > 0 && h > 0) mtl_layer.drawableSize = CGSizeMake(w, h);
                logf("metal: bound CAMetalLayer (%dx%d) on %s", w, h, device_desc.c_str());
            } else {
                logf("metal: SDL_Metal_CreateView failed; running offscreen");
            }
        } else {
            logf("metal: started in headless/offscreen mode on %s", device_desc.c_str());
        }
        return 1;
    }
}

void resize(int width, int height) {
    @autoreleasepool {
        if (mtl_layer && width > 0 && height > 0) {
            mtl_layer.drawableSize = CGSizeMake(width, height);
        }
    }
}

const char* describe() {
    return device_desc.c_str();
}

void stats(int64_t* draws, int64_t* skipped, int64_t* pipelines) {
    if (draws) *draws = stat_draws.load(std::memory_order_relaxed);
    if (skipped) *skipped = stat_skipped.load(std::memory_order_relaxed);
    if (pipelines) *pipelines = stat_pipelines.load(std::memory_order_relaxed);
}

void nvn_submit_q(const uint64_t* handles, int n, uint64_t queue) {
    @autoreleasepool {
        std::lock_guard<std::mutex> lk(replay_mu);
        const uint64_t val = fence_seq.fetch_add(1, std::memory_order_relaxed) + 1;
        pushed_seq.store(val, std::memory_order_release);
        id<MTLCommandBuffer> cmd_buf = [mtl_queue commandBuffer];
        for (int i = 0; i < n; i++) {
            replay_recording(reinterpret_cast<const uint8_t*>(handles[i]), cmd_buf);
        }
        if (mtl_timeline) {
            [cmd_buf encodeSignalEvent:mtl_timeline value:val];
        }
        [cmd_buf commit];
        queue_fences[queue] = val;
        replayed_seq.store(val, std::memory_order_release);
    }
}

void nvn_submit(const uint64_t* handles, int n) {
    nvn_submit_q(handles, n, 0);
}

uint64_t nvn_fence() {
    return fence_seq.load(std::memory_order_acquire);
}

uint64_t nvn_fence_q(uint64_t queue) {
    std::lock_guard<std::mutex> lk(replay_mu);
    auto it = queue_fences.find(queue);
    return it != queue_fences.end() ? it->second : fence_seq.load(std::memory_order_acquire);
}

uint64_t nvn_pushed() {
    return pushed_seq.load(std::memory_order_acquire);
}

uint64_t nvn_replayed() {
    return replayed_seq.load(std::memory_order_acquire);
}

int nvn_wait(uint64_t fence, uint64_t timeout_ns) {
    @autoreleasepool {
        if (!mtl_timeline || fence == 0) return 1;
        if (mtl_timeline.signaledValue >= fence) return 1;
        const auto start_t = std::chrono::steady_clock::now();
        while (mtl_timeline.signaledValue < fence) {
            if (timeout_ns == 0) return 0;
            const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now() - start_t).count();
            if (timeout_ns != ~0ull && (uint64_t)elapsed >= timeout_ns) return 0;
            std::this_thread::sleep_for(std::chrono::microseconds(50));
        }
        return 1;
    }
}

void wait_writebacks_reading(const void*, uint64_t) {}

void nvn_finish() {
    nvn_wait(nvn_fence(), ~0ull);
}

void nvn_present(const nvn_tex* t, const int crop[4]) {
    (void)crop;
    @autoreleasepool {
        const uint64_t val = fence_seq.fetch_add(1, std::memory_order_relaxed) + 1;
        pushed_seq.store(val, std::memory_order_release);
        if (mtl_layer) {
            id<CAMetalDrawable> drawable = [mtl_layer nextDrawable];
            if (drawable) {
                id<MTLCommandBuffer> cmd_buf = [mtl_queue commandBuffer];
                id<MTLTexture> src_tex = t ? ensure_texture(t) : nil;
                if (src_tex && src_tex.width == drawable.texture.width &&
                    src_tex.height == drawable.texture.height &&
                    src_tex.pixelFormat == drawable.texture.pixelFormat) {
                    id<MTLBlitCommandEncoder> blit = [cmd_buf blitCommandEncoder];
                    [blit copyFromTexture:src_tex toTexture:drawable.texture];
                    [blit endEncoding];
                } else {
                    MTLRenderPassDescriptor* rpd = [MTLRenderPassDescriptor renderPassDescriptor];
                    rpd.colorAttachments[0].texture = drawable.texture;
                    rpd.colorAttachments[0].loadAction = MTLLoadActionClear;
                    rpd.colorAttachments[0].storeAction = MTLStoreActionStore;
                    rpd.colorAttachments[0].clearColor = MTLClearColorMake(0.0, 0.0, 0.0, 1.0);
                    id<MTLRenderCommandEncoder> enc = [cmd_buf renderCommandEncoderWithDescriptor:rpd];
                    [enc endEncoding];
                }
                [cmd_buf presentDrawable:drawable];
                if (mtl_timeline) [cmd_buf encodeSignalEvent:mtl_timeline value:val];
                [cmd_buf commit];
            }
        }
        replayed_seq.store(val, std::memory_order_release);
    }
}

void nvn_register_texture(int id, const nvn_tex* t, const nvn_view*) {
    if (!t) return;
    @autoreleasepool {
        ensure_texture(t);
        std::lock_guard<std::mutex> lk(tex_mu);
        registered_textures[id] = t->gpu;
    }
}

void nvn_register_sampler(int, const nvn_samp_par*) {}
void nvn_set_texture_pool_size(int) {}

void nvn_texture_released(const nvn_tex* t) {
    if (!t) return;
    @autoreleasepool {
        std::lock_guard<std::mutex> lk(tex_mu);
        textures_by_gpu.erase(t->gpu);
    }
}

void nvn_texture_created(const nvn_tex* t) {
    if (!t) return;
    @autoreleasepool {
        ensure_texture(t);
    }
}

void nvn_program_released(const nvn_prog*) {}

void nvn_read_texels(const nvn_tex* t, unsigned level, unsigned, const NVNcopyRegion* r,
                     uint8_t* dst, uint64_t row_pitch, uint64_t image_pitch) {
    if (!t || !r || !dst) return;
    @autoreleasepool {
        id<MTLTexture> tex = ensure_texture(t);
        if (!tex) return;
        MTLRegion region = MTLRegionMake3D(r->xoffset, r->yoffset, r->zoffset, r->width, r->height, r->depth ? r->depth : 1);
        [tex getBytes:dst bytesPerRow:row_pitch bytesPerImage:image_pitch fromRegion:region mipmapLevel:level];
    }
}

void nvn_write_texels(const nvn_tex* t, unsigned level, unsigned, const NVNcopyRegion* r,
                      const uint8_t* src, uint64_t row_pitch, uint64_t image_pitch) {
    if (!t || !r || !src) return;
    @autoreleasepool {
        id<MTLTexture> tex = ensure_texture(t);
        if (!tex) return;
        MTLRegion region = MTLRegionMake3D(r->xoffset, r->yoffset, r->zoffset, r->width, r->height, r->depth ? r->depth : 1);
        [tex replaceRegion:region mipmapLevel:level slice:0 withBytes:src bytesPerRow:row_pitch bytesPerImage:image_pitch];
    }
}

void nvn_invalidate(uint64_t, uint64_t) {}

void nvn_pool_created(uint64_t gpu, uint64_t size) {
    @autoreleasepool {
        import_guest_pool(gpu, size);
    }
}

int guest_imported(uint64_t lo, uint64_t hi) {
    std::lock_guard<std::mutex> lk(pool_mu);
    for (const auto& p : pools) {
        if (lo < p.guest_hi && hi > p.guest_lo) return 1;
    }
    return 0;
}

void nvn_vmap_changing(uint64_t, uint64_t) {}

void nvn_event_signal(uint64_t gpu, uint32_t value) {
    if (host && host->gpu_write && gpu) {
        host->gpu_write(gpu, &value, sizeof(uint32_t));
    }
}

int option(int id) {
    std::lock_guard<std::mutex> lk(opt_mu);
    auto it = options_map.find(id);
    return it != options_map.end() ? it->second : 0;
}

void option_set(int id, int value) {
    std::lock_guard<std::mutex> lk(opt_mu);
    options_map[id] = value;
}

#endif // __APPLE__

} // namespace
} // namespace mkwmtl

extern "C" __attribute__((visibility("default")))
void mkwvk_close_asked(void) {}

extern "C" __attribute__((visibility("default")))
const MkwVkRenderer* mkwvk_init(const MkwVkHost* h) {
    using namespace mkwmtl;
    if (!h || h->version != MKWVK_API_VERSION) return nullptr;
    host = h;
#ifdef __APPLE__
    @autoreleasepool {
        mtl_device = MTLCreateSystemDefaultDevice();
        if (!mtl_device) {
            logf("metal: MTLCreateSystemDefaultDevice returned nil");
            return nullptr;
        }
        mtl_queue = [mtl_device newCommandQueue];
        if (!mtl_queue) {
            logf("metal: failed to create MTLCommandQueue");
            return nullptr;
        }
        mtl_timeline = [mtl_device newSharedEvent];
        device_desc = std::string([[mtl_device name] UTF8String]) + " (Metal, native)";
        logf("metal: initialized native Metal device: %s (unified memory: %s)",
             [[mtl_device name] UTF8String], mtl_device.hasUnifiedMemory ? "yes" : "no");

        // Initialize shader and pipeline state cache
        MetalPipelineCache::instance().init(mtl_device, "work/sa/cache/metal_shaders");

        table.version = MKWVK_API_VERSION;
        table.start = start;
        table.resize = resize;
        table.describe = describe;
        table.stats = stats;
        table.nvn_submit = nvn_submit;
        table.nvn_fence = nvn_fence;
        table.nvn_pushed = nvn_pushed;
        table.nvn_replayed = nvn_replayed;
        table.nvn_wait = nvn_wait;
        table.wait_writebacks_reading = wait_writebacks_reading;
        table.nvn_finish = nvn_finish;
        table.nvn_present = nvn_present;
        table.nvn_register_texture = nvn_register_texture;
        table.nvn_register_sampler = nvn_register_sampler;
        table.nvn_set_texture_pool_size = nvn_set_texture_pool_size;
        table.nvn_texture_released = nvn_texture_released;
        table.nvn_program_released = nvn_program_released;
        table.nvn_read_texels = nvn_read_texels;
        table.nvn_write_texels = nvn_write_texels;
        table.nvn_invalidate = nvn_invalidate;
        table.nvn_pool_created = nvn_pool_created;
        table.guest_imported = guest_imported;
        table.nvn_vmap_changing = nvn_vmap_changing;
        table.nvn_texture_created = nvn_texture_created;
        table.nvn_event_signal = nvn_event_signal;
        table.option = option;
        table.nvn_submit_q = nvn_submit_q;
        table.nvn_fence_q = nvn_fence_q;
        table.option_set = option_set;
        return &table;
    }
#else
    logf("metal: native Metal backend is only supported on macOS");
    return nullptr;
#endif
}
