// (hookshot) NVIDIA Reflex through VK_NV_low_latency2, without NVIDIA's Streamline (vk_reflex.h).
//
// While the Insert menu's NVIDIA Reflex row (Off / On / On + Boost; RX_VK_REFLEX=0 / 1 / 2 over it) is on, the swapchain is
// made with latency mode on (VkSwapchainLatencyCreateInfoNV) and its sleep mode set from the row; turning the row on or off
// makes the swapchain again (reflex_swapchain_stale, at the next present). Off is the game as without Reflex: no latency
// mode, no markers, no sleep, no present ids, nothing logged. The device's extensions are enabled whenever it has them, so
// the row needs no restart: enabled alone they do nothing, nothing of them is used until the row is on. Each frame the driver gets markers with the
// present's id: the game's simulation start (and input) once the sleep returns, its end and the rendering's submission start
// at the game's present (do_present), the submission's end before the present's submit, and the present's start and end
// around vkQueuePresentKHR. vkLatencySleepNV after the present waits until the driver wants the next frame to start: with
// sleep mode off it returns at once.
//
// What the markers stand for is approximate: OoT simulates on its main thread and renders on its presentation thread, and the
// replay records the GPU work as the game submits it; the sleep holds the presentation thread, which the main thread waits for.
// With frame generation on, presents come from the display thread: Reflex is not used then.
//
// RX_VK_REFLEX_LOG=1: every 300 frames with Reflex on, the driver's own timings (vkGetLatencyTimingsNV) averaged in the log:
// simulation start to present end, and to the GPU's end of rendering.
#include "vk_reflex.h"

#include <algorithm>
#include <atomic>
#include <cstdlib>
#include <cstring>
#include <mutex>

#include "vk_framegen.h"
#include "vk_menu.h"
#include "vk_work.h"   // (last: RX_VK_RECORDER=defer drains before the latency-sleep wait; =thread does not need to, the driver signals it)

namespace mkwvk {

namespace {

struct Reflex {
    bool have_ext = false, ready = false;
    bool latency_next = false;           // (the swapchain being made has latency mode on: reflex_swapchain_info)
    bool latency = false;                // (the current one has)
    VkPhysicalDevicePresentIdFeaturesKHR present_id{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PRESENT_ID_FEATURES_KHR};
    VkSwapchainLatencyCreateInfoNV latency_info{VK_STRUCTURE_TYPE_SWAPCHAIN_LATENCY_CREATE_INFO_NV};
    PFN_vkSetLatencySleepModeNV set_mode = nullptr;
    PFN_vkLatencySleepNV sleep = nullptr;
    PFN_vkSetLatencyMarkerNV marker = nullptr;
    PFN_vkGetLatencyTimingsNV timings = nullptr;
    VkSwapchainKHR swapchain = VK_NULL_HANDLE;
    uint64_t swapchain_generation = 0;   // (a sleep may finish after this chain was replaced)
    VkSemaphore wake = VK_NULL_HANDLE;   // (timeline: the sleep's end)
    uint64_t wake_value = 0;
    uint64_t id = 1;                     // (the frame's present id)
    int mode = -1;                       // (as set on the swapchain)
    bool frame_marked = false;           // (this frame's start markers given: its other markers count)
    VkPresentIdKHR pid{VK_STRUCTURE_TYPE_PRESENT_ID_KHR};
    std::mutex mu;
};
Reflex& rx() {
    static Reflex r;
    return r;
}

int wanted_mode() {
    static const char* e = getenv("RX_VK_REFLEX");
    return std::clamp(e && *e ? atoi(e) : opts.reflex, 0, 2);
}

/// With r.mu held: the row on, the extension and its feature, a swapchain made with latency mode, and no frame generation (its
/// own display thread)
bool on() {
    Reflex& r = rx();
    return r.ready && r.swapchain && r.latency && wanted_mode() > 0 && !framegen_on();
}

void mark(VkLatencyMarkerNV m) {
    Reflex& r = rx();
    VkSetLatencyMarkerInfoNV i{VK_STRUCTURE_TYPE_SET_LATENCY_MARKER_INFO_NV};
    i.presentID = r.id, i.marker = m;
    r.marker(dev.device, r.swapchain, &i);
}

void apply_mode() {
    Reflex& r = rx();
    const int want = wanted_mode();
    if (want == r.mode) return;
    VkLatencySleepModeInfoNV m{VK_STRUCTURE_TYPE_LATENCY_SLEEP_MODE_INFO_NV};
    m.lowLatencyMode = want >= 1, m.lowLatencyBoost = want == 2, m.minimumIntervalUs = 0;
    const VkResult res = r.set_mode(dev.device, r.swapchain, &m);
    logf("vk: NVIDIA Reflex: %s%s", want == 0 ? "off" : want == 1 ? "on" : "on + boost",
         res == VK_SUCCESS ? "" : " (the driver refused the sleep mode)");
    r.mode = want;
}

void log_timings() {
    static const bool wanted = getenv("RX_VK_REFLEX_LOG") && atoi(getenv("RX_VK_REFLEX_LOG")) > 0;
    Reflex& r = rx();
    if (!wanted || !r.timings || r.id % 300) return;
    VkGetLatencyMarkerInfoNV g{VK_STRUCTURE_TYPE_GET_LATENCY_MARKER_INFO_NV};
    r.timings(dev.device, r.swapchain, &g);
    if (!g.timingCount) return;
    std::vector<VkLatencyTimingsFrameReportNV> t(g.timingCount, {VK_STRUCTURE_TYPE_LATENCY_TIMINGS_FRAME_REPORT_NV});
    g.pTimings = t.data();
    r.timings(dev.device, r.swapchain, &g);
    double sim_present = 0, gpu_end = 0, sim = 0;
    int n = 0;
    for (uint32_t i = 0; i < g.timingCount; i++) {
        const auto& f = t[i];
        if (!f.simStartTimeUs || !f.presentEndTimeUs || f.presentEndTimeUs < f.simStartTimeUs) continue;
        sim_present += (double)(f.presentEndTimeUs - f.simStartTimeUs);
        sim += f.simEndTimeUs > f.simStartTimeUs ? (double)(f.simEndTimeUs - f.simStartTimeUs) : 0.0;
        gpu_end += f.gpuRenderEndTimeUs > f.simStartTimeUs ? (double)(f.gpuRenderEndTimeUs - f.simStartTimeUs) : 0.0;
        n++;
    }
    if (n)
        logf("vk: NVIDIA Reflex (%s): over %d frames, simulation start to present end %.1f ms, to the GPU's end %.1f ms, "
             "simulation %.1f ms", r.mode == 0 ? "off" : r.mode == 1 ? "on" : "on + boost", n, sim_present / n / 1000.0,
             gpu_end / n / 1000.0, sim / n / 1000.0);
}

}  // namespace

void reflex_device_extensions(std::vector<const char*>& want, const std::vector<VkExtensionProperties>& all) {
    static const char* e = getenv("RX_VK_REFLEX");
    if (e && !strcmp(e, "-")) return;   // (RX_VK_REFLEX=-: the extensions not even enabled)
    bool ll = false, pid = false;
    for (const auto& x : all) {
        ll |= !strcmp(x.extensionName, VK_NV_LOW_LATENCY_2_EXTENSION_NAME);
        pid |= !strcmp(x.extensionName, VK_KHR_PRESENT_ID_EXTENSION_NAME);
    }
    if (!ll || !pid) return;
    for (const char* n : {VK_NV_LOW_LATENCY_2_EXTENSION_NAME, VK_KHR_PRESENT_ID_EXTENSION_NAME}) {
        bool listed = false;
        for (const char* w : want) listed |= !strcmp(w, n);
        if (!listed) want.push_back(n);
    }
    rx().have_ext = true;
}

void reflex_device_features(void**& tail) {
    Reflex& r = rx();
    if (!r.have_ext) return;
    *tail = &r.present_id, tail = &r.present_id.pNext;
}

void reflex_device_created() {
    Reflex& r = rx();
    if (!r.have_ext) return;
    if (!r.present_id.presentId) {
        logf("vk: NVIDIA Reflex: the device has no present ids: off");
        return;
    }
    r.set_mode = (PFN_vkSetLatencySleepModeNV)vkGetDeviceProcAddr(dev.device, "vkSetLatencySleepModeNV");
    r.sleep = (PFN_vkLatencySleepNV)vkGetDeviceProcAddr(dev.device, "vkLatencySleepNV");
    r.marker = (PFN_vkSetLatencyMarkerNV)vkGetDeviceProcAddr(dev.device, "vkSetLatencyMarkerNV");
    r.timings = (PFN_vkGetLatencyTimingsNV)vkGetDeviceProcAddr(dev.device, "vkGetLatencyTimingsNV");
    VkSemaphoreTypeCreateInfo tc{VK_STRUCTURE_TYPE_SEMAPHORE_TYPE_CREATE_INFO};
    tc.semaphoreType = VK_SEMAPHORE_TYPE_TIMELINE;
    VkSemaphoreCreateInfo sc{VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO};
    sc.pNext = &tc;
    r.ready = r.set_mode && r.sleep && r.marker && vkCreateSemaphore(dev.device, &sc, nullptr, &r.wake) == VK_SUCCESS;
    logf("vk: NVIDIA Reflex: %s", r.ready ? "available (VK_NV_low_latency2)" : "its functions are missing: off");
}

bool reflex_available() { return rx().ready; }

void reflex_swapchain_info(VkSwapchainCreateInfoKHR& ci) {
    Reflex& r = rx();
    r.latency_next = r.ready && wanted_mode() > 0;
    if (!r.latency_next) return;   // (Off: the swapchain as without Reflex)
    r.latency_info.pNext = ci.pNext;
    r.latency_info.latencyModeEnable = VK_TRUE;
    ci.pNext = &r.latency_info;
}

bool reflex_swapchain_stale() {
    Reflex& r = rx();
    std::lock_guard lk(r.mu);
    return r.ready && r.swapchain && r.latency != (wanted_mode() > 0);
}

void reflex_swapchain_created(VkSwapchainKHR swapchain) {
    Reflex& r = rx();
    if (!r.ready) return;
    std::lock_guard lk(r.mu);
    const bool was = r.latency;
    ++r.swapchain_generation;
    r.swapchain = swapchain, r.mode = -1, r.frame_marked = false, r.latency = r.latency_next;
    if (r.latency) apply_mode();
    else if (was) logf("vk: NVIDIA Reflex: off");
}

void reflex_swapchain_destroyed() {
    Reflex& r = rx();
    std::lock_guard lk(r.mu);
    ++r.swapchain_generation;
    r.swapchain = VK_NULL_HANDLE;
    r.latency = false;
    r.frame_marked = false;
    r.mode = -1;
}

void reflex_present_begins() {
    Reflex& r = rx();
    std::lock_guard lk(r.mu);
    if (!on() || !r.frame_marked) return;
    mark(VK_LATENCY_MARKER_SIMULATION_END_NV);
    mark(VK_LATENCY_MARKER_RENDERSUBMIT_START_NV);
}

void reflex_submit_ends() {
    Reflex& r = rx();
    std::lock_guard lk(r.mu);
    if (!on()) return;
    if (r.frame_marked) mark(VK_LATENCY_MARKER_RENDERSUBMIT_END_NV);
}

const void* reflex_present_id(const void* next) {
    Reflex& r = rx();
    std::lock_guard lk(r.mu);
    if (!on() || !r.frame_marked) return next;
    mark(VK_LATENCY_MARKER_PRESENT_START_NV);
    r.pid.pNext = next, r.pid.swapchainCount = 1, r.pid.pPresentIds = &r.id;
    return &r.pid;
}

void reflex_presented() {
    Reflex& r = rx();
    std::lock_guard lk(r.mu);
    if (!on()) return;
    if (r.frame_marked) mark(VK_LATENCY_MARKER_PRESENT_END_NV);
}

void reflex_sleep() {
    Reflex& r = rx();
    uint64_t generation, value;
    {
        std::lock_guard lk(r.mu);
        if (!on()) return;
        generation = r.swapchain_generation;
        apply_mode();   // (the menu's row may have changed)
        if (r.frame_marked) log_timings(), r.id++;
        VkLatencySleepInfoNV s{VK_STRUCTURE_TYPE_LATENCY_SLEEP_INFO_NV};
        s.signalSemaphore = r.wake, s.value = ++r.wake_value;
        value = s.value;
        if (r.sleep(dev.device, r.swapchain, &s) != VK_SUCCESS) return;
    }
    VkSemaphoreWaitInfo w{VK_STRUCTURE_TYPE_SEMAPHORE_WAIT_INFO};
    w.semaphoreCount = 1, w.pSemaphores = &r.wake, w.pValues = &value;
    vkWaitSemaphores(dev.device, &w, 100000000ull);   // (100 ms at most: a driver that never wakes it does not stop the game)
    std::lock_guard lk(r.mu);
    if (!on() || generation != r.swapchain_generation || value != r.wake_value) return;
    mark(VK_LATENCY_MARKER_SIMULATION_START_NV);
    mark(VK_LATENCY_MARKER_INPUT_SAMPLE_NV);
    r.frame_marked = true;
}

} // namespace mkwvk
