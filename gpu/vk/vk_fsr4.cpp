// (hookshot) AMD FSR 4, one of the temporal upscaler's engines (vk_fsr4.h). The frame chain it draws with is
// vk_temporal.cpp's, the same as NVIDIA DLSS's: the colour as the game's network samples it, the depth, the motion (the
// camera's and the skinned draws' own) and the camera jitter. Here are AMD's library, the upscale context and its dispatch.
// The host side follows the API guide of FidelityFX SDK 2.4 (Kits/FidelityFX/docs/getting-started/ffx-api.md): a Vulkan
// backend description chained to the upscale context description, inputs read in SHADER_READ_ONLY_OPTIMAL, the output
// written in GENERAL. First written for Lichii's OoT branch (madebyjordan, vk_fsr4_upscaler.cpp), GPL-3.0-or-later; its Linux
// path (a Vulkan FSR 4 library through dlopen) by N3oTraX.
//
// AMD's library is looked for in RX_VK_FSR_DIR=<folder> when set, the executable's folder (bin\ beside the launcher), then
// the game folder: amd_fidelityfx_loader_vk.dll, with amd_fidelityfx_upscaler_vk.dll beside it (Linux: a Vulkan FSR 4
// library, amd_fidelityfx_upscaler_vk.so). Of the upscalers it lists for this GPU the newest FSR 4 is taken, never an older
// one in its place. RX_VK_FSR4=0: FSR 4 out for this run.
#include "vk_fsr4.h"

#include <atomic>
#include <cstdlib>

#include "vk_internal.h"
#include "vk_temporal.h"

#ifdef HOOKSHOT_FSR
#include <chrono>
#include <cstdio>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>
#include <vector>
#ifndef _WIN32
#include <dlfcn.h>
#include <unistd.h>
#endif

#include "vk_paths.h"
#include "vk_texture.h"

#include "api/include/ffx_api.h"
#include "api/include/ffx_api_types.h"
#include "api/include/vk/ffx_api_vk.h"
#include "upscalers/include/ffx_upscale.h"
#endif
#include "vk_work.h"   // (after the others: the barriers here count as work for full_barrier)

namespace mkwvk {

namespace {
int env_switch(const char* name) {   // (-1: unset)
    const char* e = getenv(name);
    return e && *e ? atoi(e) : -1;
}
// (what is known of FSR on this device: -1 not yet, else an FsrWhy. Set when AMD's library has been asked)
std::atomic<int> g_why{-1};
}  // namespace

FsrWhy fsr4_why() {
    if (!fsr4_built()) return FSR_NOT_BUILT;
    static const bool env_off = env_switch("RX_VK_FSR4") == 0;
    if (env_off) return FSR_ENV_OFF;
    const int w = g_why.load(std::memory_order_relaxed);
    return w < 0 ? FSR_OK : (FsrWhy)w;
}

#ifdef HOOKSHOT_FSR

namespace {

#ifdef _WIN32
constexpr const char* kLoader = "amd_fidelityfx_loader_vk.dll";
#else
// (linux) no AMD loader exists there: the upscaler library itself, which exports the ffx entry points (a Vulkan FSR 4 build)
constexpr const char* kLoader = "amd_fidelityfx_upscaler_vk.so";
#endif

/// AMD's library, loaded once (the menu's thread may ask first: fsr4_probe), and the upscaler it has for this device
struct Library {
    std::mutex mu;
    bool tried = false, ok = false;
    HMODULE lib = nullptr;
    PfnFfxCreateContext create = nullptr;
    PfnFfxDestroyContext destroy = nullptr;
    PfnFfxQuery query = nullptr;
    PfnFfxDispatch dispatch = nullptr;
    uint64_t version_id = 0;
    VkDeviceContext device_context{};
};
// (lib() and st() are never destroyed: Hookshot leaves through ExitProcess / exit() with the device alive, and a destructor
// then would call into AMD's library after its DLL_PROCESS_DETACH, or under a render thread still recording with it)
Library& lib() {
    static Library& l = *new Library;
    return l;
}

/// An upscale context and the descriptions it was made from: it keeps pointers into them until it is destroyed, which
/// happens a few frames after it is let go (temporal_later), so each context has its own
struct Context {
    ffxCreateBackendVKDesc backend{};
    ffxOverrideVersion version{};
#ifndef _WIN32
    ffxCreateBackendVKDesc_DEPRECATED legacy_backend{};   // (linux) the backend description a Vulkan FSR 4 build like fsr4-vk reads
#endif
    ffxCreateContextDescUpscale upscale{};
    ffxContext context = nullptr;
    uint32_t width = 0, height = 0;   // (its output, which is also the most the render size can be)
    uint64_t memory = 0;              // (what AMD's library says it holds)
    ~Context() {
        if (context) lib().destroy(&context, nullptr);
    }
};

/// The engine's state: used with the temporal upscaler's lock held
struct State {
    std::shared_ptr<Context> context;
    uint32_t in_w = 0, in_h = 0;   // (the inputs' size under this context: the largest render size it has had)
    std::chrono::steady_clock::time_point last{};
    uint64_t evals = 0;
    int told_resets = 0;
};
State& st() {
    static State& s = *new State;   // (never destroyed: lib()'s note)
    return s;
}

void on_message(uint32_t type, const wchar_t* message) {
    char text[512] = {};
    if (message) WideCharToMultiByte(CP_UTF8, 0, message, -1, text, (int)sizeof text - 1, nullptr, nullptr);
    logf("vk: AMD FSR 4: AMD's %s: %s", type == FFX_API_MESSAGE_TYPE_ERROR ? "error" : "warning", text);
}

/// The folders the library is looked for in: RX_VK_FSR_DIR, the executable's (bin\ beside the launcher), the game folder
std::vector<std::string> library_dirs() {
    std::vector<std::string> d;
    if (const char* e = getenv("RX_VK_FSR_DIR"); e && *e) d.emplace_back(e);
    char exe[MAX_PATH];
    DWORD n = GetModuleFileNameA(nullptr, exe, MAX_PATH);
    if (n && n < MAX_PATH) {
        std::string s(exe, n);
        d.push_back(s.substr(0, s.find_last_of("\\/")));
    }
    n = game_module_path(exe, MAX_PATH);
    if (n && n < MAX_PATH) {
        std::string s(exe, n);
        s = s.substr(0, s.find_last_of("\\/"));
        if (d.empty() || d.back() != s) d.push_back(s);
    }
    return d;
}

void* symbol(const char* name) {
#ifdef _WIN32
    return (void*)GetProcAddress(lib().lib, name);
#else
    return dlsym(lib().lib, name);
#endif
}

/// AMD's library on this device, once: false when FSR 4 cannot run here (g_why says why, the log too)
bool load() {
    Library& l = lib();
    std::lock_guard lk(l.mu);
    if (l.tried) return l.ok;
    l.tried = true;
    const auto no = [](FsrWhy why) {
        g_why = why;
        return false;
    };
    std::string where;
    for (const std::string& dir : library_dirs()) {
        where += (where.empty() ? "" : ", ") + dir;
#ifdef _WIN32
        const std::string path = dir + "\\" + kLoader;
        if (GetFileAttributesA(path.c_str()) == INVALID_FILE_ATTRIBUTES) continue;
        // (the upscaler DLL the loader picks lies beside it: the loader's folder first in the search)
        l.lib = LoadLibraryExA(path.c_str(), nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
        // (there but not loaded: a DLL it needs missing, a bad signature, or a relative RX_VK_FSR_DIR, which the search
        // flags refuse)
        if (!l.lib) logf("vk: AMD FSR 4: %s not loaded (Windows error %lu)", path.c_str(), (unsigned long)GetLastError());
#else
        const std::string path = dir + "/" + kLoader;
        if (access(path.c_str(), R_OK) != 0) continue;
        l.lib = (HMODULE)dlopen(path.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!l.lib) logf("vk: AMD FSR 4: %s not loaded: %s", path.c_str(), dlerror());
#endif
        if (l.lib) {
            logf("vk: AMD FSR 4: %s", path.c_str());
            break;
        }
    }
    if (!l.lib) {
        logf("vk: AMD FSR 4: no %s in %s (the readme says where AMD's files come from)", kLoader, where.c_str());
        return no(FSR_NO_LIBRARY);
    }
    l.create = (PfnFfxCreateContext)symbol("ffxCreateContext");
    l.destroy = (PfnFfxDestroyContext)symbol("ffxDestroyContext");
    l.query = (PfnFfxQuery)symbol("ffxQuery");
    l.dispatch = (PfnFfxDispatch)symbol("ffxDispatch");
    if (!l.create || !l.destroy || !l.query || !l.dispatch) {
        logf("vk: AMD FSR 4: %s lacks the FSR API's entry points", kLoader);
        return no(FSR_NO_LIBRARY);
    }
    l.device_context = VkDeviceContext{dev.device, dev.physical, vkGetDeviceProcAddr};
    // (the library lists every upscaler this device can run: the newest 4.x is taken explicitly, so an FSR 3.1 provider never
    // stands in silently)
    ffxQueryDescGetVersions versions{};
    versions.header.type = FFX_API_QUERY_DESC_TYPE_GET_VERSIONS;
    versions.createDescType = FFX_API_CREATE_CONTEXT_DESC_TYPE_UPSCALE;
    versions.device = &l.device_context;
    uint64_t count = 0;
    versions.outputCount = &count;
    if (l.query(nullptr, &versions.header) != FFX_API_RETURN_OK || !count) {
        logf("vk: AMD FSR 4: AMD's library lists no upscaler for this GPU");
        return no(FSR_NO_MODEL);
    }
    std::vector<uint64_t> ids(count);
    std::vector<const char*> names(count);
    versions.versionIds = ids.data();
    versions.versionNames = names.data();
    if (l.query(nullptr, &versions.header) != FFX_API_RETURN_OK) {
        logf("vk: AMD FSR 4: the upscalers could not be listed");
        return no(FSR_NO_MODEL);
    }
    std::string listed;
    unsigned best[3] = {0, 0, 0};
    for (uint64_t i = 0; i < count; i++) {
        const char* name = names[i] ? names[i] : "";
        listed += (listed.empty() ? "" : ", ") + std::string(name);
        unsigned v[3] = {0, 0, 0};
        sscanf(name, "%u.%u.%u", &v[0], &v[1], &v[2]);
        // (the first of equal versions: a Vulkan FSR 4 build lists its Auto, which picks the GPU's model, before INT8 and FP8)
        if (v[0] == 4 && (!l.version_id || v[1] > best[1] || (v[1] == best[1] && v[2] > best[2]))) {
            std::memcpy(best, v, sizeof best);
            l.version_id = ids[i];
        }
    }
    if (!l.version_id) {
        logf("vk: AMD FSR 4: no FSR 4 for this GPU (AMD's library has: %s)", listed.c_str());
        return no(FSR_NO_MODEL);
    }
    logf("vk: AMD FSR 4: upscalers %s; using %u.%u.%u", listed.c_str(), best[0], best[1], best[2]);
    l.ok = true;
    g_why = FSR_OK;
    return true;
}

/// A context for outputs of w x h, any render size up to that (the game's dynamic resolution and the Render resolution row
/// change it every so often: one context takes them all)
std::shared_ptr<Context> make_context(uint32_t w, uint32_t h) {
    Library& l = lib();
    auto c = std::make_shared<Context>();
    c->backend.header.type = FFX_API_CREATE_CONTEXT_DESC_TYPE_BACKEND_VK;
    c->backend.deviceContext = l.device_context;
    c->version.header.type = FFX_API_DESC_TYPE_OVERRIDE_VERSION;
    c->version.versionId = l.version_id;
    c->backend.header.pNext = &c->version.header;
#ifndef _WIN32
    // (linux) fsr4-vk looks for the SDK's older backend description, not ffxCreateBackendVKDesc: without it, it finds no device
    // and creation returns FFX_API_RETURN_ERROR_PARAMETER. Both stay chained
    c->legacy_backend.header.type = FFX_API_CREATE_CONTEXT_DESC_TYPE_BACKEND_VK_DEPRECATED;
    c->legacy_backend.vkDevice = l.device_context.vkDevice;
    c->legacy_backend.vkPhysicalDevice = l.device_context.vkPhysicalDevice;
    c->legacy_backend.vkDeviceProcAddr = l.device_context.vkDeviceProcAddr;
    c->version.header.pNext = &c->legacy_backend.header;
#endif
    c->upscale.header.type = FFX_API_CREATE_CONTEXT_DESC_TYPE_UPSCALE;
    c->upscale.header.pNext = &c->backend.header;
    // (the chain's colour is tonemapped and square-root encoded already: LDR, perceptual, no auto exposure; depth not
    // inverted. The render size changes under the one context)
    c->upscale.flags = FFX_UPSCALE_ENABLE_NON_LINEAR_COLORSPACE | FFX_UPSCALE_ENABLE_DYNAMIC_RESOLUTION;
    c->upscale.maxRenderSize = {w, h};
    c->upscale.maxUpscaleSize = {w, h};
    c->upscale.fpMessage = &on_message;
    const auto t0 = std::chrono::steady_clock::now();
    const ffxReturnCode_t r = l.create(&c->context, &c->upscale.header, nullptr);
    const double made_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    if (r != FFX_API_RETURN_OK || !c->context) {
        logf("vk: AMD FSR 4: its upscaler was not made (%d) for %ux%u", (int)r, w, h);
        c->context = nullptr;
        return nullptr;
    }
    c->width = w, c->height = h;
    FfxApiEffectMemoryUsage usage{};
    ffxQueryDescUpscaleGetGPUMemoryUsage mem{};
    mem.header.type = FFX_API_QUERY_DESC_TYPE_UPSCALE_GPU_MEMORY_USAGE;
    mem.gpuMemoryUsageUpscaler = &usage;
    if (l.query(&c->context, &mem.header) == FFX_API_RETURN_OK) c->memory = usage.totalUsageInBytes;
    ffxQueryGetProviderVersion provider{};
    provider.header.type = FFX_API_QUERY_DESC_TYPE_GET_PROVIDER_VERSION;
    const bool known = l.query(&c->context, &provider.header) == FFX_API_RETURN_OK && provider.versionName;
    logf("vk: AMD FSR 4: FSR %s made for outputs of %ux%u (frame %llu, %.1f ms of CPU; its own %llu MB)",
         known ? provider.versionName : "?", w, h, (unsigned long long)texture_frame_no(), made_ms,
         (unsigned long long)(c->memory >> 20));
    return c;
}

FfxApiResource resource(const TemporalImage& im, VkImageUsageFlags usage, uint32_t state) {
    VkImageCreateInfo ci{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
    ci.imageType = VK_IMAGE_TYPE_2D, ci.format = im.format, ci.extent = {im.width, im.height, 1};
    ci.mipLevels = 1, ci.arrayLayers = 1, ci.samples = VK_SAMPLE_COUNT_1_BIT, ci.tiling = VK_IMAGE_TILING_OPTIMAL;
    ci.usage = usage, ci.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    return ffxApiGetResourceVK((void*)im.image, ffxApiGetImageResourceDescriptionVK(im.image, ci, 0), state);
}

VkImageMemoryBarrier2 barrier(VkImage image, VkAccessFlags2 src, VkAccessFlags2 dst, VkImageLayout from, VkImageLayout to) {
    VkImageMemoryBarrier2 b{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER_2};
    b.srcStageMask = b.dstStageMask = VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT;
    b.srcAccessMask = src, b.dstAccessMask = dst, b.oldLayout = from, b.newLayout = to;
    b.srcQueueFamilyIndex = b.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    b.image = image, b.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
    return b;
}
void barriers(VkCommandBuffer cmd, const VkImageMemoryBarrier2* b, uint32_t n) {
    VkDependencyInfo di{VK_STRUCTURE_TYPE_DEPENDENCY_INFO};
    di.imageMemoryBarrierCount = n, di.pImageMemoryBarriers = b;
    vkCmdPipelineBarrier2(cmd, &di);
}

#ifndef _WIN32
/// (linux) a Vulkan FSR 4 build takes no frame without an exposure, and the chain's colour is tonemapped already: a 1x1 R32F of 1
bool unit_exposure(VkCommandBuffer cmd, TemporalImage& out) {
    static VkImage image = VK_NULL_HANDLE;
    static VmaAllocation allocation{};
    const bool made = image != VK_NULL_HANDLE;
    if (!made) {
        VkImageCreateInfo ci{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
        ci.imageType = VK_IMAGE_TYPE_2D, ci.format = VK_FORMAT_R32_SFLOAT, ci.extent = {1, 1, 1}, ci.mipLevels = 1, ci.arrayLayers = 1;
        ci.samples = VK_SAMPLE_COUNT_1_BIT, ci.tiling = VK_IMAGE_TILING_OPTIMAL;
        ci.usage = VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
        if (!create_image(ci, image, allocation)) return image = VK_NULL_HANDLE, false;
    }
    out = TemporalImage{image, VK_NULL_HANDLE, VK_FORMAT_R32_SFLOAT, 1, 1};
    if (!made) {
        const VkImageMemoryBarrier2 to_clear = barrier(image, 0, VK_ACCESS_2_TRANSFER_WRITE_BIT, VK_IMAGE_LAYOUT_UNDEFINED,
                                                       VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL);
        barriers(cmd, &to_clear, 1);
        const VkClearColorValue one{{1.0f, 0.0f, 0.0f, 0.0f}};
        const VkImageSubresourceRange range{VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        vkCmdClearColorImage(cmd, image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, &one, 1, &range);
        const VkImageMemoryBarrier2 to_read = barrier(image, VK_ACCESS_2_TRANSFER_WRITE_BIT, VK_ACCESS_2_SHADER_READ_BIT,
                                                      VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL);
        barriers(cmd, &to_read, 1);
    }
    return true;
}
#endif

// ---- the engine (vk_temporal.h TemporalEngine) ----

bool start() { return load(); }

void release() {
    State& s = st();
    if (!s.context) return;
    std::shared_ptr<Context> old = std::move(s.context);
    temporal_later([old] {});   // (destroyed with the last copy, a few frames on: recorded dispatches may still use it)
    s.context.reset();
}

int prepare(VkCommandBuffer, uint32_t rw, uint32_t rh, uint32_t ow, uint32_t oh, uint32_t* in_w, uint32_t* in_h, const char** why) {
    State& s = st();
    int made = 1;
    if (!s.context || s.context->width != ow || s.context->height != oh) {
        release();
        s.context = make_context(ow, oh);
        if (!s.context) return *why = "its upscaler was not made", -1;
        s.in_w = s.in_h = 0;
        made = 2;
    }
    // (the inputs as large as the largest render size this context has had, never past the output: a fixed share keeps
    // images of its own size, and the game's dynamic resolution only makes them again when it goes past them)
    s.in_w = std::min(std::max(s.in_w, rw), ow), s.in_h = std::min(std::max(s.in_h, rh), oh);
    *in_w = s.in_w, *in_h = s.in_h;
    return made;
}

bool evaluate(VkCommandBuffer cmd, const TemporalFrame& f) {
    State& s = st();
    Library& l = lib();
#ifndef _WIN32
    TemporalImage exposure{};
    if (!unit_exposure(cmd, exposure)) return false;
#endif
    const auto now = std::chrono::steady_clock::now();
    const float frame_ms = s.evals ? std::chrono::duration<float, std::milli>(now - s.last).count() : 1000.0f / 30.0f;
    s.last = now;

    constexpr VkImageLayout G = VK_IMAGE_LAYOUT_GENERAL, R = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
    constexpr VkAccessFlags2 any = VK_ACCESS_2_MEMORY_READ_BIT | VK_ACCESS_2_MEMORY_WRITE_BIT;
    const VkImageMemoryBarrier2 in[4] = {barrier(f.color.image, VK_ACCESS_2_MEMORY_WRITE_BIT, VK_ACCESS_2_SHADER_READ_BIT, G, R),
                                         barrier(f.depth.image, VK_ACCESS_2_MEMORY_WRITE_BIT, VK_ACCESS_2_SHADER_READ_BIT, G, R),
                                         barrier(f.motion.image, VK_ACCESS_2_MEMORY_WRITE_BIT, VK_ACCESS_2_SHADER_READ_BIT, G, R),
                                         barrier(f.output.image, any, any, G, G)};
    barriers(cmd, in, 4);

    ffxDispatchDescUpscale d{};
    d.header.type = FFX_API_DISPATCH_DESC_TYPE_UPSCALE;
    d.commandList = cmd;
    d.color = resource(f.color, VK_IMAGE_USAGE_SAMPLED_BIT, FFX_API_RESOURCE_STATE_COMPUTE_READ);
    d.depth = resource(f.depth, VK_IMAGE_USAGE_SAMPLED_BIT, FFX_API_RESOURCE_STATE_COMPUTE_READ);
    d.motionVectors = resource(f.motion, VK_IMAGE_USAGE_SAMPLED_BIT, FFX_API_RESOURCE_STATE_COMPUTE_READ);
    d.output = resource(f.output, VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_SAMPLED_BIT, FFX_API_RESOURCE_STATE_UNORDERED_ACCESS);
#ifndef _WIN32
    d.exposure = resource(exposure, VK_IMAGE_USAGE_SAMPLED_BIT, FFX_API_RESOURCE_STATE_COMPUTE_READ);
#endif
    d.jitterOffset = {f.jitter[0], f.jitter[1]};   // (render pixels, as the projection was offset: the same as DLSS's)
    d.motionVectorScale = {1.0f, 1.0f};             // (render pixels already, towards the frame before)
    d.renderSize = {f.render_w, f.render_h};
    d.upscaleSize = {f.output.width, f.output.height};
    d.enableSharpening = false;   // (the Sharpness row sharpens at the window, after the HUD)
    d.sharpness = 0.0f;
    d.frameTimeDelta = frame_ms;
    d.preExposure = 1.0f;
    d.reset = f.reset;
    d.cameraNear = f.near_z, d.cameraFar = f.far_z, d.cameraFovAngleVertical = f.fov_y;
    d.viewSpaceToMetersFactor = 1.0f;
    d.flags = FFX_UPSCALE_FLAG_NON_LINEAR_COLOR_SRGB;
    ::mkwvk::rec::boundary(::mkwvk::rec::B_DIRECT);   // (ffxDispatch records into cmd itself: what this thread recorded through vk_work.h reaches cmd first)
    const ffxReturnCode_t r = l.dispatch(&s.context->context, &d.header);
    note_work();   // (AMD's dispatches: full_barrier must not take the next barrier for a repeat of the one before them)

    const VkImageMemoryBarrier2 out[4] = {barrier(f.color.image, VK_ACCESS_2_SHADER_READ_BIT, any, R, G),
                                          barrier(f.depth.image, VK_ACCESS_2_SHADER_READ_BIT, any, R, G),
                                          barrier(f.motion.image, VK_ACCESS_2_SHADER_READ_BIT, any, R, G),
                                          barrier(f.output.image, any, any, G, G)};
    barriers(cmd, out, 4);
    if (r != FFX_API_RETURN_OK) {
        logf("vk: AMD FSR 4: its dispatch failed (%d)", (int)r);
        return false;
    }
    // (the first evaluation, and the first resets: a camera cut each)
    if (s.evals++ == 0 || (f.reset && s.told_resets < 40))
        s.told_resets++, logf("vk: AMD FSR 4: %ux%u -> %ux%u, jitter %+.3f %+.3f px%s", f.render_w, f.render_h, f.output.width,
                              f.output.height, f.jitter[0], f.jitter[1], f.reset ? " (history reset)" : "");
    return true;
}

uint64_t memory() {
    State& s = st();
    return s.context ? s.context->memory : 0;
}

const TemporalEngine kEngine{"AMD FSR 4", "FSR", start, prepare, evaluate, release, memory};

}  // namespace

bool fsr4_built() { return true; }
const TemporalEngine* fsr4_engine() { return &kEngine; }

void fsr4_probe() {
    if (fsr4_why() != FSR_OK || g_why.load(std::memory_order_relaxed) >= 0 || !dev.device) return;
    load();
}

bool fsr4_wants_descriptor_buffer() {
#ifdef _WIN32
    return false;
#else
    if (fsr4_why() == FSR_ENV_OFF) return false;
    for (const std::string& dir : library_dirs())
        if (access((dir + "/" + kLoader).c_str(), R_OK) == 0) return true;
    return false;
#endif
}

#else  // (no HOOKSHOT_FSR in this build: FSR is not there)

bool fsr4_built() { return false; }
const TemporalEngine* fsr4_engine() { return nullptr; }
void fsr4_probe() {}
bool fsr4_wants_descriptor_buffer() { return false; }

#endif

}  // namespace mkwvk
