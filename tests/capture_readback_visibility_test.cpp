#define _CRT_SECURE_NO_WARNINGS
#include <vulkan/vulkan.h>
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <vector>

constexpr uint32_t kShotW = 344, kShotH = 144, kLogW = 320, kLogH = 180;
struct Allocation { std::vector<uint8_t> cpu, gpu; bool copied = false, host = false; } normal, made, binary;
using VmaAllocation = Allocation*;
void* shot_maps[2]{};
VmaAllocation shot_allocs[2]{};
void* made_map{};
VmaAllocation made_buf_alloc{};
struct LogSlot { VmaAllocation alloc{}; void* map{}; bool used{}; int64_t at{}; uint32_t seq{}, kind{}; VkBuffer buf{}; };
LogSlot log_slots[3];
std::vector<uint8_t> captured;
bool gpu_done = false;
bool coherent = false;
bool implicit_host = false;
int waits = 0, invalidations = 0, pngs = 0;
[[noreturn]] void device_lost() { std::abort(); }
void require(bool ok, const char* why) {
    if (!ok) { std::fprintf(stderr, "%s\n", why); std::exit(1); }
}
void complete() {
    gpu_done = true;
    if (coherent)
        for (auto a : {&normal, &made, &binary})
            if (a->copied && a->host) std::memcpy(a->cpu.data(), a->gpu.data(), a->gpu.size());
}
void wait_value(uint64_t value) { require(value == 17, "wrong GPU value waited"); complete(); ++waits; }
void invalidate_mapped(VmaAllocation allocation, uint64_t size) {
    require(gpu_done, "cache invalidated before GPU completion");
    require(allocation && size == allocation->gpu.size(), "wrong allocation/range invalidated");
    if (!coherent && allocation->host) std::memcpy(allocation->cpu.data(), allocation->gpu.data(), size);
    ++invalidations;
}
VKAPI_ATTR VkResult VKAPI_CALL vkWaitForFences(VkDevice, uint32_t n, const VkFence*, VkBool32, uint64_t) {
    require(n == 1, "wrong fence count"); complete(); ++waits; return VK_SUCCESS;
}
VKAPI_ATTR void VKAPI_CALL vkCmdCopyImageToBuffer(VkCommandBuffer, VkImage, VkImageLayout, VkBuffer buffer,
                                                 uint32_t count, const VkBufferImageCopy* copy) {
    auto a = reinterpret_cast<Allocation*>(buffer);
    require(count == 1 && copy->bufferOffset == 0 && copy->bufferRowLength == 0 &&
            copy->bufferImageHeight == 0 && (uint64_t)copy->imageExtent.width * copy->imageExtent.height * 4 == a->gpu.size(),
            "wrong capture copy range");
    a->copied = true; a->host = implicit_host;
}
VKAPI_ATTR void VKAPI_CALL vkCmdPipelineBarrier2(VkCommandBuffer, const VkDependencyInfo* info) {
    for (uint32_t i = 0; i < info->bufferMemoryBarrierCount; ++i) {
        const auto& b = info->pBufferMemoryBarriers[i];
        auto a = reinterpret_cast<Allocation*>(b.buffer);
        require(a && a->copied && b.offset == 0 && b.size == a->gpu.size() &&
                b.srcQueueFamilyIndex == VK_QUEUE_FAMILY_IGNORED && b.dstQueueFamilyIndex == VK_QUEUE_FAMILY_IGNORED,
                "wrong host barrier copy/range/order");
        const auto stages = VK_PIPELINE_STAGE_2_COPY_BIT | VK_PIPELINE_STAGE_2_ALL_TRANSFER_BIT | VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT;
        if ((b.srcStageMask & stages) && (b.srcAccessMask & (VK_ACCESS_2_TRANSFER_WRITE_BIT | VK_ACCESS_2_MEMORY_WRITE_BIT)) &&
            (b.dstStageMask & VK_PIPELINE_STAGE_2_HOST_BIT) && (b.dstAccessMask & VK_ACCESS_2_HOST_READ_BIT))
            a->host = true;
    }
}
/* HOST_BARRIER */
void record_captures() {
    struct { VkCommandBuffer cmd{}; } r, f;
    VkImage shot_image{}, made_image{}, log_image{};
    VkBuffer shot_bufs[2] = {VK_NULL_HANDLE, reinterpret_cast<VkBuffer>(&normal)};
    VkBuffer made_buf = reinterpret_cast<VkBuffer>(&made);
    int64_t presents = 1;
    // Each block is the actual production copy and the dependency following it.
    { /* NORMAL_COPY */ }
    { /* MADE_COPY */ }
    LogSlot& l = log_slots[1];
    l.buf = reinterpret_cast<VkBuffer>(&binary);
    { /* LOG_COPY */ }
}
void write_png(const char*, const uint8_t* bytes, uint32_t w, uint32_t h) {
    require(w == kShotW && h == kShotH, "PNG dimensions changed");
    require(std::equal(made.gpu.begin(), made.gpu.end(), bytes), "generated screenshot read stale CPU cache");
    ++pngs;
}
/* COLLECT */
void read_log_after_fence() {
    struct { VkDevice device{}; } dev;
    struct { VkFence done{}; } f;
    const int log_slot = 1;
    /* FENCE */
}
/* SHOT_PIXELS */
void read_shot(bool generated, bool owned = false) {
    struct { bool on=false; int64_t presents=0; std::shared_ptr<std::vector<uint8_t>> pixels; } pending;
    if (owned) {
        pending.on = true; pending.presents = 1; pending.pixels = shot_pixels(17, 1);
        std::fill(normal.cpu.begin(), normal.cpu.end(), 0);
    }
    /* TAKE */
    if (!generated) {
        auto px = take(17, 1);
        require(*px == normal.gpu, "normal screenshot read stale CPU cache");
        return;
    }
    bool shot = true;
    VkImage made_src = reinterpret_cast<VkImage>(uintptr_t(123));
    uint64_t value = 17;
    int64_t presents = 1;
    const char* shots = "private-test";
    /* MADE */
}
void seed(Allocation& allocation, size_t bytes, uint8_t value) {
    allocation.cpu.assign(bytes, 0);
    allocation.gpu.assign(bytes, value);
}
int main(int argc, char** argv) {
    require(argc == 4, "expected phase, cache and host visibility mode");
    coherent = !std::strcmp(argv[2], "coherent");
    implicit_host = !std::strcmp(argv[3], "implicit");
    seed(normal, size_t(kShotW) * kShotH * 4, 91);
    seed(made, size_t(kShotW) * kShotH * 4, 173);
    seed(binary, size_t(kLogW) * kLogH * 4, 27);
    shot_maps[1] = normal.cpu.data(); shot_allocs[1] = &normal;
    made_map = made.cpu.data(); made_buf_alloc = &made;
    record_captures();
    if (!std::strcmp(argv[1], "normal") || !std::strcmp(argv[1], "owned")) {
        read_shot(false, !std::strcmp(argv[1], "owned"));
        require(waits == 1 && invalidations == 1, "normal completion/visibility contract");
    } else if (!std::strcmp(argv[1], "made")) {
        read_shot(true);
        require(waits == 1 && invalidations == 2 && pngs == 1, "generated completion/visibility contract");
    } else {
        log_slots[1] = {&binary, binary.cpu.data(), true, 123456789, 42, 1};
        read_log_after_fence();
        require(captured.size() == 16 + binary.gpu.size(), "binary record size changed");
        require(std::equal(binary.gpu.begin(), binary.gpu.end(), captured.begin() + 16), "binary log read stale CPU cache");
        require(!log_slots[1].used && waits == 1 && invalidations == 1, "binary completion/visibility contract");
        int64_t timestamp{}; uint32_t seq{}, kind{};
        std::memcpy(&timestamp, captured.data(), 8); std::memcpy(&seq, captured.data() + 8, 4);
        std::memcpy(&kind, captured.data() + 12, 4);
        require(timestamp == 123456789 && seq == 42 && kind == 1, "binary metadata changed");
        const int before = invalidations;
        framelog_collect(1); require(invalidations == before, "unused slot invalidated");
    }
    std::printf("%s %s %s production copy/read observes GPU bytes after host dependency/completion/invalidation\n", argv[1], argv[2], argv[3]);
}
