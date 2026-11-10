// (hookshot) NVIDIA DLSS Super Resolution, one of the temporal upscaler's engines (vk_dlss.h). The frame chain it draws
// with (the scene's camera and depth, the inputs, the actor motion, the jitter, the picture into the network's output) is
// vk_temporal.cpp's; here are NGX, DLSS's feature and its evaluation.
//
// RX_VK_DLSS=0 / 1 / 2: the game's own, DLSS, DLAA over the Insert menu's Upscaler row (0 also leaves NGX's extensions
// off). DLSS's runtime (Windows: nvngx_dlss.dll; Linux: libnvidia-ngx-dlss.so.*) is looked for in RX_VK_DLSS_DIR=<folder>
// when set, the game folder's ngx folder, and %LOCALAPPDATA%\Hookshot\ngx (Linux: $XDG_DATA_HOME/hookshot/ngx): NGX takes
// the newest one it finds in them. Windows' paths are wide all the way (GetModuleFileNameW, _wgetenv), so any folder name
// works. On Linux NGX takes only ASCII paths: a folder named otherwise goes to it as /proc/self/fd/<n> (wide()), and the
// runtime itself has to be in a folder whose real path is ASCII (the log and the menu say so when it is not). The Insert
// menu's DLSS model row (opts.dlss_model, upscaler_rows.h) chooses DLSS's preset: K by default, M, L, or NVIDIA's default
// (0). RX_VK_DLSS_PRESET=<letter> (or 0) over it. RX_VK_DLSS_LOG=1: NGX's own log in ours.
//
// NVIDIA's NGX SDK is not part of Hookshot (NVIDIA's license): a local build fetches it (scripts/ngx_sdk.py) and builds with
// HOOKSHOT_NGX_SDK, which compiles this file with HOOKSHOT_NGX. Without it only the stubs at the end are here.
// NGX's core is the driver's (Windows: _nvngx.dll, which NVIDIA's loader finds in the driver's own folder; Linux:
// libnvidia-ngx.so). It is never put beside the game: a copy there would be loaded in place of the driver's.
#include "vk_dlss.h"

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <mutex>
#include <string>
#ifndef _WIN32
#include <fcntl.h>   // (wide: a folder's descriptor for NGX)
#endif

#include "dlss_checks.h"
#include "upscaler_rows.h"
#include "vk_menu.h"
#include "vk_paths.h"
#include "vk_temporal.h"
#include "vk_texture.h"

#ifdef HOOKSHOT_NGX
#include "nvsdk_ngx_vk.h"
#include "nvsdk_ngx_helpers.h"
#include "nvsdk_ngx_helpers_vk.h"
#endif
#include "vk_work.h"   // (after the others: counts the commands that do GPU work, for full_barrier)

namespace mkwvk {

namespace {
int env_switch(const char* name) {   // (-1: unset)
    const char* e = getenv(name);
    return e && *e ? atoi(e) : -1;
}
}  // namespace

// (what is known of DLSS on this device: -1 not yet, else a DlssWhy. Set once the device is made and when NGX answers)
std::atomic<int> g_why{-1};

DlssWhy dlss_why() {
    if (!dlss_built()) return DLSS_NOT_BUILT;
    static const bool env_off = env_switch("RX_VK_DLSS") == 0;
    if (env_off) return DLSS_ENV_OFF;
    const int w = g_why.load(std::memory_order_relaxed);
    return w < 0 ? DLSS_OK : (DlssWhy)w;
}

#ifdef HOOKSHOT_NGX

namespace {

/// NGX and DLSS's feature. The feature is used with the temporal upscaler's lock held; NGX's start (ngx_init) also from the
/// menu's thread (dlss_probe), under mu
struct State {
    std::mutex mu;
    bool ngx_tried = false, ngx_ok = false;
    NVSDK_NGX_Parameter* caps = nullptr;
    NVSDK_NGX_Parameter* params = nullptr;
    NVSDK_NGX_Handle* feature = nullptr;
    uint32_t feature_rw = 0, feature_rh = 0, feature_ow = 0, feature_oh = 0;   // (its largest render size, its output)
    uint32_t min_rw = 0, min_rh = 0;
    unsigned feature_preset = ~0u;   // (the preset it was made with: another one from the menu makes it again)
    uint64_t features_made = 0;      // (how many times: a feature made again in play costs a stall, so each says why)
};
State& st() {
    static State s;
    return s;
}

NVSDK_NGX_Resource_VK resource(const TemporalImage& im, bool write) {
    return NVSDK_NGX_Create_ImageView_Resource_VK(im.view, im.image, {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}, im.format,
                                                  im.width, im.height, write);
}

void NVSDK_CONV ngx_log(const char* message, NVSDK_NGX_Logging_Level, NVSDK_NGX_Feature) {
    std::string m(message ? message : "");
    while (!m.empty() && (m.back() == '\n' || m.back() == '\r')) m.pop_back();
    logf("ngx: %s", m.c_str());
}

namespace fs = std::filesystem;
#ifdef _WIN32
/// The game folder (game_module_path's rule: bin\hookshot.exe beside image.bin is the folder above bin), from
/// GetModuleFileNameW: a folder with characters outside the ANSI code page is still the right one
fs::path game_dir() {
    std::wstring exe(32768, L'\0');
    const DWORD n = GetModuleFileNameW(nullptr, exe.data(), (DWORD)exe.size());
    if (!n || n >= exe.size()) return {};
    exe.resize(n);
    fs::path dir = fs::path(exe).parent_path();
    if (!_wcsicmp(dir.filename().c_str(), L"bin") && GetFileAttributesW((dir.parent_path() / L"image.bin").c_str()) != INVALID_FILE_ATTRIBUTES)
        dir = dir.parent_path();
    return dir;
}
/// An environment variable as a path (_wgetenv: not through the ANSI code page); empty when unset
fs::path env_path(const wchar_t* name) {
    const wchar_t* e = _wgetenv(name);
    return e && *e ? fs::path(e) : fs::path();
}
/// A path for our log (UTF-8)
std::string shown(const fs::path& p) {
    const std::wstring& w = p.native();
    const int n = WideCharToMultiByte(CP_UTF8, 0, w.data(), (int)w.size(), nullptr, 0, nullptr, nullptr);
    std::string s(n > 0 ? n : 0, '\0');
    if (n > 0) WideCharToMultiByte(CP_UTF8, 0, w.data(), (int)w.size(), s.data(), n, nullptr, nullptr);
    return s;
}
/// A path for NGX, which takes wide strings: Windows' own
std::wstring wide(const fs::path& p) { return p.native(); }
#else
fs::path game_dir() {
    char exe[MAX_PATH];
    const DWORD n = game_module_path(exe, MAX_PATH);
    return fs::path(std::string(exe, n)).parent_path();
}
fs::path env_path(const char* name) {
    const char* e = getenv(name);
    return e && *e ? fs::path(e) : fs::path();
}
std::string shown(const fs::path& p) { return p.native(); }
/// A path for NGX, which takes wide strings. NGX's Linux library turns them back into bytes in the "C" locale
/// (WStrToUTF8Str: newlocale(LC_ALL, "C") and wcsrtombs), which fails on any character past ASCII, and the path comes out
/// empty. Before, each byte was also widened alone ("CafÃ©"). So a folder whose path is not all ASCII goes to NGX as
/// /proc/self/fd/<n>, the folder opened and kept open for the process's life: an ASCII name for the same folder, nothing
/// made on the disk. NGX writes its own files (the data path) and finds the runtime through it; the driver's part then
/// loads the runtime by its real path (realpath), which has to be ASCII too: ngx_init says so when that is all there is.
/// When the folder cannot be opened (not there), its path decoded from UTF-8 (dlss_checks.h, not through the locale; bytes
/// that are not UTF-8 become U+FFFD), for an NGX that takes it. Each such folder is said in the log
std::wstring wide(const fs::path& p) {
    const std::string& s = p.native();
    if (dlss_checks::ascii(s)) return std::wstring(s.begin(), s.end());
    if (const int fd = open(s.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC); fd >= 0) {
        const std::string alias = "/proc/self/fd/" + std::to_string(fd);
        logf("vk: NVIDIA DLSS: %s is not all ASCII, which NGX's Linux library does not take: given to it as %s", s.c_str(),
             alias.c_str());
        return std::wstring(alias.begin(), alias.end());
    }
    bool bad = false;
    std::wstring w = dlss_checks::utf8_to_wide(s, &bad);
    logf("vk: NVIDIA DLSS: %s is not all ASCII and could not be opened: given to NGX as it is%s", s.c_str(),
         bad ? " (not UTF-8: U+FFFD for its bad bytes)" : "");
    return w;
}
#endif

#ifdef _WIN32
constexpr const char* kRuntime = "nvngx_dlss.dll";   // (DLSS's runtime, as scripts/ngx_sdk.py fetches it)
constexpr const fs::path::value_type* kRuntimeName = L"nvngx_dlss.dll";
#else
constexpr const char* kRuntime = "libnvidia-ngx-dlss.so";
constexpr const fs::path::value_type* kRuntimeName = "libnvidia-ngx-dlss.so";
#endif

/// NGX on this device, once: false when DLSS cannot run here (the reason logged)
bool ngx_init() {
    State& s = st();
    std::lock_guard lk(s.mu);
    if (s.ngx_tried) return s.ngx_ok;
    s.ngx_tried = true;
    // (the game folder or nothing: an empty one made "ngx" relative, and NGX looked for its runtime in the current folder)
    const fs::path game = game_dir();
    if (game.empty() || game.is_relative()) {
        logf("vk: NVIDIA DLSS: the game's folder could not be found: no DLSS");
        g_why = DLSS_NO_RUNTIME;
        return false;
    }
    // where DLSS's runtime (kRuntime) is looked for (NGX takes the newest it finds), and its own files go
    std::vector<fs::path> dirs;
#ifdef _WIN32
    if (fs::path e = env_path(L"RX_VK_DLSS_DIR"); !e.empty()) dirs.push_back(e);
    dirs.push_back(game / L"ngx");
    if (fs::path l = env_path(L"LOCALAPPDATA"); !l.empty()) dirs.push_back(l / L"Hookshot" / L"ngx");
#else
    if (fs::path e = env_path("RX_VK_DLSS_DIR"); !e.empty()) dirs.push_back(e);
    dirs.push_back(game / "ngx");
    if (fs::path x = env_path("XDG_DATA_HOME"); !x.empty()) dirs.push_back(x / "hookshot" / "ngx");
    else if (fs::path h = env_path("HOME"); !h.empty()) dirs.push_back(h / ".local" / "share" / "hookshot" / "ngx");
#endif
    std::vector<std::wstring> wdirs;
    for (const auto& d : dirs) wdirs.push_back(wide(d));
    std::vector<const wchar_t*> paths;
    for (const auto& d : wdirs) paths.push_back(d.c_str());
    const fs::path data = game / "ngx";
    std::error_code made;   // (not the throwing overload: a folder that cannot be made, read-only or so, must not end the game)
    fs::create_directories(data, made);   // (NGX's logs and its own files: the game folder's, not /usr/share)
    const std::wstring wdata = wide(data);
    NVSDK_NGX_FeatureCommonInfo info{};
    info.PathListInfo.Path = paths.data();
    info.PathListInfo.Length = (unsigned)paths.size();
    static const bool verbose = env_switch("RX_VK_DLSS_LOG") > 0;
    info.LoggingInfo.LoggingCallback = verbose ? ngx_log : nullptr;
    info.LoggingInfo.MinimumLoggingLevel = verbose ? NVSDK_NGX_LOGGING_LEVEL_ON : NVSDK_NGX_LOGGING_LEVEL_OFF;
    // (NGX also writes its own log files into the data folder; with RX_VK_DLSS_LOG=1 its lines go to ours instead)
    info.LoggingInfo.DisableOtherLoggingSinks = verbose;
    // (a project id of Hookshot's own: NGX wants one with the custom engine type, any GUID)
    NVSDK_NGX_Result r = NVSDK_NGX_VULKAN_Init_with_ProjectID("7b2f5d0c-6a1e-4c39-9f84-3d5e2a1b0c96", NVSDK_NGX_ENGINE_TYPE_CUSTOM,
                                                              "1.0", wdata.c_str(), dev.instance, dev.physical, dev.device,
                                                              instance_proc(), vkGetDeviceProcAddr, &info);
    if (NVSDK_NGX_FAILED(r)) {
        logf("vk: NVIDIA DLSS: NGX did not start (%#x): not an NVIDIA GPU, or its driver has no NGX", (unsigned)r);
        g_why = DLSS_NEEDS_RTX;
        return false;
    }
    if (NVSDK_NGX_FAILED(NVSDK_NGX_VULKAN_GetCapabilityParameters(&s.caps)) || !s.caps) {
        logf("vk: NVIDIA DLSS: NGX has no capabilities for this device");
        g_why = DLSS_NEEDS_RTX;
        return false;
    }
    // (NGX's C functions, not NVSDK_NGX_Parameter's virtual ones: its object comes from NVIDIA's MSVC-built library, whose
    // vtable order is not the Itanium ABI's that llvm-mingw calls with. The overloads only lined up by luck)
    int available = 0, needs_driver = 0;
    unsigned major = 0, minor = 0;
    NVSDK_NGX_Parameter_GetI(s.caps, NVSDK_NGX_Parameter_SuperSampling_Available, &available);
    NVSDK_NGX_Parameter_GetI(s.caps, NVSDK_NGX_Parameter_SuperSampling_NeedsUpdatedDriver, &needs_driver);
    NVSDK_NGX_Parameter_GetUI(s.caps, NVSDK_NGX_Parameter_SuperSampling_MinDriverVersionMajor, &major);
    NVSDK_NGX_Parameter_GetUI(s.caps, NVSDK_NGX_Parameter_SuperSampling_MinDriverVersionMinor, &minor);
    std::string where;
    for (const auto& d : dirs) where += (where.empty() ? "" : ", ") + shown(d);
    if (!available) {
        // (for the menu: a runtime found in none of the folders is the likely reason; with one there, the GPU (a GTX))
        int init = 0;
        NVSDK_NGX_Parameter_GetI(s.caps, NVSDK_NGX_Parameter_SuperSampling_FeatureInitResult, &init);
        // (Linux: NGX loads the runtime by its real path, ASCII only (wide()): one only in folders named otherwise is not
        // loaded, FeatureInitResult 0xbad00004, though the GPU runs DLSS)
        bool runtime = false, loadable = false;
        std::error_code ec;
        for (const auto& d : dirs)
            for (const auto& f : fs::directory_iterator(d, ec))
                if (f.path().filename().native().rfind(kRuntimeName, 0) == 0) {
                    runtime = true;
#ifdef _WIN32
                    loadable = true;
#else
                    std::error_code real;
                    loadable |= dlss_checks::ascii(fs::canonical(f.path(), real).native()) && !real;
#endif
                }
        if (needs_driver) logf("vk: NVIDIA DLSS: needs NVIDIA's driver %u.%u or newer", major, minor);
        else if (!runtime) logf("vk: NVIDIA DLSS: not available: no %s in %s (scripts/ngx_sdk.py fetches it)", kRuntime, where.c_str());
        else if (!loadable)
            logf("vk: NVIDIA DLSS: not available: %s is only in folders whose path is not all ASCII (%s), and NVIDIA's NGX on "
                 "Linux loads it only from one that is: put it in $XDG_DATA_HOME/hookshot/ngx, or RX_VK_DLSS_DIR=<an ASCII folder>",
                 kRuntime, where.c_str());
        else logf("vk: NVIDIA DLSS: not available on this GPU (%#x): DLSS needs an NVIDIA RTX GPU", (unsigned)init);
        g_why = needs_driver ? DLSS_NEEDS_DRIVER : !runtime ? DLSS_NO_RUNTIME : !loadable ? DLSS_RUNTIME_NOT_ASCII : DLSS_NEEDS_RTX;
        return false;
    }
    if (NVSDK_NGX_FAILED(NVSDK_NGX_VULKAN_AllocateParameters(&s.params)) || !s.params) return false;
    logf("vk: NVIDIA DLSS: NGX started (DLSS's runtime: the newest %s in %s)", kRuntime, where.c_str());
    s.ngx_ok = true;
    g_why = DLSS_OK;
    return true;
}

/// DLSS's preset: the DLSS model row's, RX_VK_DLSS_PRESET over it (upscaler_rows.h dlss_preset)
unsigned wanted_preset() {
    static const char* const env = getenv("RX_VK_DLSS_PRESET");
    return upscaler_rows::dlss_preset(opts.dlss_model, env && *env ? env : nullptr);
}

/// DLSS's feature for this output size and preset, made when either changes (cmd: its creation's work): the engine's
/// prepare (vk_temporal.h)
int prepare(VkCommandBuffer cmd, uint32_t rw, uint32_t rh, uint32_t ow, uint32_t oh, uint32_t* in_w, uint32_t* in_h,
            const char** fail) {
    State& s = st();
    const unsigned preset = wanted_preset();
    if (s.feature && s.feature_ow == ow && s.feature_oh == oh && rw <= s.feature_rw && rh <= s.feature_rh &&
        rw >= s.min_rw && rh >= s.min_rh && s.feature_preset == preset)
        return *in_w = s.feature_rw, *in_h = s.feature_rh, 1;
    // (why it is made: in the log with its time, so a stall in play can be matched with one)
    char why[160];
    if (!s.feature && !s.features_made) snprintf(why, sizeof why, "the first");
    else if (!s.feature) snprintf(why, sizeof why, "again after it was let go");
    else if (s.feature_ow != ow || s.feature_oh != oh)
        snprintf(why, sizeof why, "the output went from %ux%u to %ux%u", s.feature_ow, s.feature_oh, ow, oh);
    else if (s.feature_preset != preset)
        snprintf(why, sizeof why, "preset %c, was %c (the DLSS model row)", upscaler_rows::preset_letter(preset),
                 upscaler_rows::preset_letter(s.feature_preset));
    else
        snprintf(why, sizeof why, "the render size %ux%u left its range, %ux%u to %ux%u", rw, rh, s.min_rw, s.min_rh,
                 s.feature_rw, s.feature_rh);
    if (s.feature) {
        NVSDK_NGX_Handle* old = s.feature;
        temporal_later([old] { NVSDK_NGX_VULKAN_ReleaseFeature(old); });
        s.feature = nullptr;
    }
    // (the quality mode whose range of render sizes holds this one: the network's 3/4 is DLSS's MaxQuality range)
    // (DLAA's when the render size is the output's)
    static const NVSDK_NGX_PerfQuality_Value scaled[] = {NVSDK_NGX_PerfQuality_Value_MaxQuality, NVSDK_NGX_PerfQuality_Value_DLAA,
                                                        NVSDK_NGX_PerfQuality_Value_Balanced, NVSDK_NGX_PerfQuality_Value_MaxPerf,
                                                        NVSDK_NGX_PerfQuality_Value_UltraPerformance};
    static const NVSDK_NGX_PerfQuality_Value same[] = {NVSDK_NGX_PerfQuality_Value_DLAA, NVSDK_NGX_PerfQuality_Value_MaxQuality};
    const bool aa = rw == ow && rh == oh;
    const NVSDK_NGX_PerfQuality_Value* modes = aa ? same : scaled;
    const size_t nmodes = aa ? 2 : 5;
    NVSDK_NGX_PerfQuality_Value mode = modes[0];
    unsigned max_w = 0, max_h = 0, min_w = 0, min_h = 0;
    bool found = aa;
    if (aa) max_w = min_w = ow, max_h = min_h = oh;   // (DLAA: the render size is the output's, one size)
    for (size_t i = 0; i < nmodes && !found; i++) {
        const NVSDK_NGX_PerfQuality_Value m = modes[i];
        unsigned w = 0, h = 0, xw = 0, xh = 0, nw = 0, nh = 0;
        float sharp = 0;
        if (NVSDK_NGX_FAILED(NGX_DLSS_GET_OPTIMAL_SETTINGS(s.caps, ow, oh, m, &w, &h, &xw, &xh, &nw, &nh, &sharp)) || !w) continue;
        if (rw >= nw && rh >= nh && rw <= xw && rh <= xh) {
            mode = m, max_w = xw, max_h = xh, min_w = nw, min_h = nh, found = true;
            break;
        }
    }
    if (!found) return *fail = "no DLSS mode takes this render size", 0;
    // (the DLSS model row's preset for every mode, K by default: NVIDIA's transformer model. 0: NVIDIA's own per mode)
    static_assert(NVSDK_NGX_DLSS_Hint_Render_Preset_K == 11 && NVSDK_NGX_DLSS_Hint_Render_Preset_L == 12 &&
                  NVSDK_NGX_DLSS_Hint_Render_Preset_M == 13 && NVSDK_NGX_DLSS_Hint_Render_Preset_Default == 0);
    for (const char* k : {NVSDK_NGX_Parameter_DLSS_Hint_Render_Preset_DLAA, NVSDK_NGX_Parameter_DLSS_Hint_Render_Preset_Quality,
                          NVSDK_NGX_Parameter_DLSS_Hint_Render_Preset_Balanced, NVSDK_NGX_Parameter_DLSS_Hint_Render_Preset_Performance,
                          NVSDK_NGX_Parameter_DLSS_Hint_Render_Preset_UltraPerformance,
                          NVSDK_NGX_Parameter_DLSS_Hint_Render_Preset_UltraQuality})
        NVSDK_NGX_Parameter_SetUI(s.params, k, preset);
    NVSDK_NGX_DLSS_Create_Params cp{};
    cp.Feature.InWidth = max_w, cp.Feature.InHeight = max_h, cp.Feature.InTargetWidth = ow, cp.Feature.InTargetHeight = oh;
    cp.Feature.InPerfQualityValue = mode;
    // (LDR colour, already tonemapped: no exposure; motion at the render size, not jittered; depth not reversed)
    cp.InFeatureCreateFlags = NVSDK_NGX_DLSS_Feature_Flags_MVLowRes;
    const auto t0 = std::chrono::steady_clock::now();
    ::mkwvk::rec::boundary(::mkwvk::rec::B_DIRECT);   // (NGX records into cmd itself: what this thread recorded through vk_work.h reaches cmd first)
    const NVSDK_NGX_Result r = NGX_VULKAN_CREATE_DLSS_EXT(cmd, 1, 1, &s.feature, s.params, &cp);
    const double made_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    note_work();   // (NGX's own commands, which vk_work.h does not see: the next full_barrier is not left out)
    if (NVSDK_NGX_FAILED(r) || !s.feature) {
        logf("vk: NVIDIA DLSS: its feature was not made (%#x) for %ux%u -> %ux%u", (unsigned)r, max_w, max_h, ow, oh);
        s.feature = nullptr;
        return *fail = "its feature was not made", -1;
    }
    s.feature_rw = max_w, s.feature_rh = max_h, s.feature_ow = ow, s.feature_oh = oh, s.min_rw = min_w, s.min_rh = min_h;
    s.feature_preset = preset;
    s.features_made++;
    logf("vk: NVIDIA DLSS: feature %llu made (%s; frame %llu, %.1f ms of CPU): %ux%u (%ux%u to %ux%u) -> %ux%u, mode %d, "
         "preset %c%s", (unsigned long long)s.features_made, why, (unsigned long long)texture_frame_no(), made_ms, rw, rh,
         min_w, min_h, max_w, max_h, ow, oh, (int)mode, upscaler_rows::preset_letter(preset),
         preset ? "" : " (NVIDIA's default)");
    *in_w = s.feature_rw, *in_h = s.feature_rh;
    return 2;   // (a new history)
}

bool start() { return ngx_init(); }

bool evaluate(VkCommandBuffer cmd, const TemporalFrame& f) {
    State& s = st();
    NVSDK_NGX_Resource_VK color = resource(f.color, false), depth = resource(f.depth, false), mv = resource(f.motion, false),
                          output = resource(f.output, true);
    NVSDK_NGX_VK_DLSS_Eval_Params ep{};
    ep.Feature.pInColor = &color, ep.Feature.pInOutput = &output;
    ep.pInDepth = &depth, ep.pInMotionVectors = &mv;
    ep.InJitterOffsetX = f.jitter[0], ep.InJitterOffsetY = f.jitter[1];   // (render pixels, x right and y down)
    ep.InRenderSubrectDimensions = {f.render_w, f.render_h};
    ep.InReset = f.reset ? 1 : 0;
    ep.InMVScaleX = ep.InMVScaleY = 1.0f;
    ::mkwvk::rec::boundary(::mkwvk::rec::B_DIRECT);   // (NGX records into cmd itself: what this thread recorded through vk_work.h reaches cmd first)
    const NVSDK_NGX_Result r = NGX_VULKAN_EVALUATE_DLSS_EXT(cmd, s.feature, s.params, &ep);
    note_work();   // (as at its creation: the barrier after it, and the game's next one, are recorded)
    if (NVSDK_NGX_FAILED(r)) {
        logf("vk: NVIDIA DLSS: its evaluation failed (%#x)", (unsigned)r);
        return false;
    }
    return true;
}

void release() {
    State& s = st();
    if (!s.feature) return;
    NVSDK_NGX_Handle* old = s.feature;
    temporal_later([old] { NVSDK_NGX_VULKAN_ReleaseFeature(old); });
    s.feature = nullptr;
    s.feature_rw = s.feature_rh = s.feature_ow = s.feature_oh = s.min_rw = s.min_rh = 0;
}

uint64_t memory() {
    State& s = st();
    unsigned long long ngx = 0;
    return s.caps && NVSDK_NGX_SUCCEED(NGX_DLSS_GET_STATS(s.caps, &ngx)) ? (uint64_t)ngx : 0;
}

const TemporalEngine kEngine{"NVIDIA DLSS", "DLSS", start, prepare, evaluate, release, memory};

}  // namespace

bool dlss_built() { return true; }
const TemporalEngine* dlss_engine() { return &kEngine; }

void dlss_instance_extensions(std::vector<const char*>& want, const std::vector<VkExtensionProperties>& all) {
    if (env_switch("RX_VK_DLSS") == 0) return;
    for (const auto& e : all)
        if (!strcmp(e.extensionName, VK_KHR_GET_PHYSICAL_DEVICE_PROPERTIES_2_EXTENSION_NAME)) {
            want.push_back(VK_KHR_GET_PHYSICAL_DEVICE_PROPERTIES_2_EXTENSION_NAME);
            return;
        }
}

void dlss_device_extensions(std::vector<const char*>& want, const std::vector<VkExtensionProperties>& all) {
    // (NGX's: VK_NVX_binary_import and VK_NVX_image_view_handle, with push descriptors and buffer device addresses,
    // which the replay enables already: core 1.2's bufferDeviceAddress stands for VK_EXT_buffer_device_address. The NVX ones
    // are on whenever the device has them, so the Insert menu's row needs no restart)
    if (env_switch("RX_VK_DLSS") == 0) return;
    bool both = true;
    for (const char* name : {VK_NVX_BINARY_IMPORT_EXTENSION_NAME, VK_NVX_IMAGE_VIEW_HANDLE_EXTENSION_NAME}) {
        bool have = false, listed = false;
        for (const auto& e : all) have |= !strcmp(e.extensionName, name);
        for (const char* w : want) listed |= !strcmp(w, name);
        if (have && !listed) want.push_back(name);
        both &= have;
    }
    // (NVIDIA's own extensions: without them this is not an NVIDIA GPU, or not one NGX runs on. With them, NGX says, in
    // dlss_probe or at the first upscale: a GTX has them too)
    if (!both) g_why = DLSS_NEEDS_RTX;
}

void dlss_probe() {
    if (dlss_why() != DLSS_OK || g_why.load(std::memory_order_relaxed) >= 0 || !dev.device) return;
    ngx_init();
}

#else  // (no NGX SDK in this build: DLSS is not there)

bool dlss_built() { return false; }
const TemporalEngine* dlss_engine() { return nullptr; }
void dlss_probe() {}
void dlss_instance_extensions(std::vector<const char*>&, const std::vector<VkExtensionProperties>&) {}
void dlss_device_extensions(std::vector<const char*>&, const std::vector<VkExtensionProperties>&) {}

#endif

} // namespace mkwvk
