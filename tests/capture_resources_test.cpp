#include <vulkan/vulkan.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <map>

using VmaAllocation = void*;
struct { VkExtent2D swap_extent{1720, 720}; VkDevice device{}; VkPhysicalDeviceProperties props{}; } dev;
VkImage off_image{}, shot_image{};
VkImageView shot_view{};
VkImage made_image{};
VkBuffer made_buf{};
VmaAllocation made_image_alloc{}, made_buf_alloc{};
void* made_map{};
VmaAllocation off_alloc{}, shot_image_alloc{}, shot_allocs[2]{};
VkBuffer shot_bufs[2]{};
void* shot_maps[2]{};
const uint32_t kShotW = (uint32_t)std::atoi("3440"), kShotH = (uint32_t)std::atoi("1440");
int calls = 0, fail_at = 0;
uintptr_t serial = 0;
std::set<uintptr_t> live;
std::map<VkImageView, VkImage> views;
void require(bool ok, const char* why) {
    if (!ok) { std::fprintf(stderr, "%s\n", why); std::exit(1); }
}
template<class T> bool make(T& handle, VmaAllocation& allocation) {
    if (++calls == fail_at) return false;
    live.insert(++serial);
    handle = reinterpret_cast<T>(serial);
    allocation = reinterpret_cast<void*>(serial);
    return true;
}
void logf(const char*, ...) { require(false, "valid capture sizing rejected"); }
bool create_image(const VkImageCreateInfo& ci, VkImage& image, VmaAllocation& allocation) {
    require(ci.extent.width && ci.extent.height, "empty image");
    return make(image, allocation);
}
bool create_buffer(uint64_t size, VkBufferUsageFlags, bool, VkBuffer& buffer,
                   VmaAllocation& allocation, void** map) {
    require(size == uint64_t(kShotW) * kShotH * 4, "readback byte size");
    if (!make(buffer, allocation)) return false;
    *map = allocation;
    return true;
}
void destroy_image(VkImage image, VmaAllocation allocation) {
    for (const auto& view : views) require(view.second != image, "image destroyed before its view");
    require(reinterpret_cast<uintptr_t>(image) == reinterpret_cast<uintptr_t>(allocation), "image ownership");
    require(live.erase(reinterpret_cast<uintptr_t>(image)) == 1, "image double free");
}
void destroy_buffer(VkBuffer buffer, VmaAllocation allocation) {
    require(reinterpret_cast<uintptr_t>(buffer) == reinterpret_cast<uintptr_t>(allocation), "buffer ownership");
    require(live.erase(reinterpret_cast<uintptr_t>(buffer)) == 1, "buffer double free");
}
VKAPI_ATTR VkResult VKAPI_CALL vkCreateImageView(VkDevice, const VkImageViewCreateInfo* ci,
                                                const VkAllocationCallbacks*, VkImageView* view) {
    require(ci->image && live.count(reinterpret_cast<uintptr_t>(ci->image)), "view of an unmade image");
    VmaAllocation unused{};
    if (!make(*view, unused)) return VK_ERROR_OUT_OF_DEVICE_MEMORY;
    views[*view] = ci->image;
    return VK_SUCCESS;
}
VKAPI_ATTR void VKAPI_CALL vkDestroyImageView(VkDevice, VkImageView view, const VkAllocationCallbacks*) {
    require(views.erase(view) == 1 && live.erase(reinterpret_cast<uintptr_t>(view)) == 1, "view double free");
}
/* ACTUAL_FUNCTION */
int commands = 0;
VkImage made_src{};
void image_barrier(VkCommandBuffer, VkImage image, VkImageLayout, VkImageLayout) {
    require(image && live.count(reinterpret_cast<uintptr_t>(image)), "barrier on unmade image");
    ++commands;
}
void blit_crop(VkCommandBuffer, VkImage src, uint32_t, uint32_t, const int*, VkImage dst,
               VkImageLayout, uint32_t, uint32_t) {
    require(src && dst && live.count(reinterpret_cast<uintptr_t>(dst)), "blit on unmade image");
    ++commands;
}
VKAPI_ATTR void VKAPI_CALL vkCmdCopyImageToBuffer(VkCommandBuffer, VkImage image, VkImageLayout,
                                                 VkBuffer buffer, uint32_t n, const VkBufferImageCopy*) {
    require(image && buffer && live.count(reinterpret_cast<uintptr_t>(buffer)) && n == 1,
            "copy on unmade readback");
    ++commands;
}
void record_made() {
    struct { VkCommandBuffer cmd{}; } r;
    uint32_t mw = 320, mh = 180;
    /* ACTUAL_RECORDING */
}
VKAPI_ATTR void VKAPI_CALL vkCmdPipelineBarrier2(VkCommandBuffer, const VkDependencyInfo* info) {
    require(info->bufferMemoryBarrierCount == 1, "capture host dependency missing");
    const auto& b = info->pBufferMemoryBarriers[0];
    require(b.buffer && live.count(reinterpret_cast<uintptr_t>(b.buffer)) && b.offset == 0 &&
            b.size == uint64_t(kShotW) * kShotH * 4 && b.dstStageMask == VK_PIPELINE_STAGE_2_HOST_BIT &&
            b.dstAccessMask == VK_ACCESS_2_HOST_READ_BIT, "host dependency on unmade or incorrect readback");
    ++commands;
}
void cleanup() {
    if (shot_view) vkDestroyImageView(dev.device, shot_view, nullptr);
    shot_view = {};
    if (off_image) destroy_image(off_image, off_alloc);
    if (shot_image) destroy_image(shot_image, shot_image_alloc);
    for (int i = 0; i < 2; ++i) {
        if (shot_bufs[i]) destroy_buffer(shot_bufs[i], shot_allocs[i]);
        shot_bufs[i] = {}; shot_allocs[i] = {}; shot_maps[i] = {};
    }
    off_image = {}; shot_image = {}; off_alloc = {}; shot_image_alloc = {};
}
int main() {
    dev.props.limits.maxImageDimension2D = 16384;
    for (int failure = 1; failure <= 5; ++failure) {
        calls = 0; fail_at = failure;
        require(!offscreen_init(), "failed setup accepted");
        require(!off_image && !shot_image && !shot_view && !shot_bufs[0] && !shot_bufs[1], "partial capture handles published");
        require(!off_alloc && !shot_image_alloc && !shot_allocs[0] && !shot_allocs[1]
                && !shot_maps[0] && !shot_maps[1], "partial capture allocation/map published");
        require(live.empty(), "partial capture resources leaked");
        calls = 0; fail_at = 0;
        require(offscreen_init(), "retry did not recover");
        require(off_image && shot_image && shot_view && shot_bufs[0] && shot_bufs[1]
                && shot_maps[0] && shot_maps[1], "ready capture incomplete");
        const int before = calls;
        require(offscreen_init() && calls == before, "ready setup allocated again");
        cleanup(); require(live.empty(), "cleanup leaked");
    }
    std::puts("capture allocation failures, retry and ready reuse passed");
    for (int failure = 1; failure <= 2; ++failure) {
        calls = 0; fail_at = failure;
        require(!made_shot_init(), "failed made capture accepted");
        require(!made_image && !made_buf && !made_image_alloc && !made_buf_alloc && !made_map,
                "partial made capture published");
        require(live.empty(), "made capture allocation leaked");
        calls = 0; fail_at = 0;
        require(made_shot_init() && made_image && made_buf && made_map, "made capture retry failed");
        const int before = calls;
        require(made_shot_init() && calls == before, "ready made capture allocated again");
        destroy_image(made_image, made_image_alloc); destroy_buffer(made_buf, made_buf_alloc);
        made_image = {}; made_buf = {}; made_image_alloc = {}; made_buf_alloc = {}; made_map = {};
        require(live.empty(), "made capture cleanup leaked");
    }
    std::puts("made-frame capture failures, retry and ready reuse passed");
    for (int failure = 1; failure <= 2; ++failure) {
        calls = 0; fail_at = failure; commands = 0;
        made_src = reinterpret_cast<VkImage>(uintptr_t(0xffff));
        record_made();
        require(!made_src && !commands && live.empty(), "failed made shot recorded or scheduled a read");
        calls = 0; fail_at = 0;
        made_src = reinterpret_cast<VkImage>(uintptr_t(0xffff));
        record_made();
        require(made_src && made_map && commands == 5, "recovered made shot copy/host dependency was not recorded");
        destroy_image(made_image, made_image_alloc); destroy_buffer(made_buf, made_buf_alloc);
        made_image = {}; made_buf = {}; made_image_alloc = {}; made_buf_alloc = {}; made_map = {};
    }
    std::puts("production made-shot recorder suppresses failed captures and recovers");
}
