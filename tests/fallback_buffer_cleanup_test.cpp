// Authored allocation/address failures, no Vulkan device or driver. The struct and
// initialization/BDA functions are included verbatim from current vk_draw.cpp.
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

using VkBuffer = uint64_t;
using VkBufferUsageFlags = uint32_t;
struct Allocation { unsigned id = 0; };
using VmaAllocation = Allocation*;
constexpr VkBuffer VK_NULL_HANDLE = 0;
constexpr VkBufferUsageFlags VK_BUFFER_USAGE_STORAGE_BUFFER_BIT = 1;
constexpr VkBufferUsageFlags VK_BUFFER_USAGE_TRANSFER_DST_BIT = 2;
constexpr VkBufferUsageFlags VK_BUFFER_USAGE_SHADER_DEVICE_ADDRESS_BIT = 4;
constexpr VkBufferUsageFlags VK_BUFFER_USAGE_INDIRECT_BUFFER_BIT = 8;
constexpr int VK_STRUCTURE_TYPE_BUFFER_DEVICE_ADDRESS_INFO = 1;
struct VkBufferDeviceAddressInfo { int sType; VkBuffer buffer = 0; };
struct { int device = 1; } dev;
namespace Shader::Backend::SPIRV {
constexpr uint64_t MESH_FALLBACK_CAPACITY = 5, MESH_FALLBACK_HEADER_WORDS = 8, MESH_FALLBACK_RECORD_WORDS = 16;
}
struct Program {
    uint32_t fallback_vertices_per_workgroup = 3;
    uint32_t fallback_record_words = 4;
    uint32_t fallback_payload_words = 2;
    uint32_t fallback_task_threads = 2;
    bool fallback_task = true;
};

static std::array<Allocation, 16> allocations;
static Allocation poison;
static std::unordered_map<VkBuffer, VmaAllocation> live;
static unsigned create_calls, destroy_calls, address_calls;
static unsigned fail_create, zero_address;
static void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
static bool create_buffer(uint64_t size, VkBufferUsageFlags, bool,
                          VkBuffer& buffer, VmaAllocation& allocation, void**) {
    require(size != 0, "fixture received a zero allocation size");
    ++create_calls;
    if (create_calls == fail_create) {
        // An output written on failure must never be treated as a confirmed allocation.
        buffer = 0xffff;
        allocation = &poison;
        return false;
    }
    require(create_calls < allocations.size(), "fixture allocation limit");
    buffer = create_calls;
    allocation = &allocations[create_calls];
    allocation->id = create_calls;
    require(live.emplace(buffer, allocation).second, "duplicate mock handle");
    return true;
}
[[maybe_unused]] static void destroy_buffer(VkBuffer buffer, VmaAllocation allocation) {
    const auto it = live.find(buffer);
    require(it != live.end() && it->second == allocation,
            "destroyed an unconfirmed or already-destroyed allocation");
    ++destroy_calls;
    live.erase(it);
}
static uint64_t vkGetBufferDeviceAddress(int device, const VkBufferDeviceAddressInfo* info) {
    require(device == 1 && info->sType == VK_STRUCTURE_TYPE_BUFFER_DEVICE_ADDRESS_INFO,
            "invalid authored BDA request");
    require(live.contains(info->buffer), "queried an unconfirmed allocation");
    return ++address_calls == zero_address ? 0 : info->buffer * 4096;
}

#include "fallback_actual.inc"

// (the buffers are a recording thread's, not a program's (#1383): a failure is not remembered, the next draw tries again, and
// with the injected failure spent that try succeeds; an invalid program still allocates nothing)
static void no_retry(const Program& p, FallbackBuffers*& out) {
    const auto calls = create_calls;
    const bool ok = fallback_buffers_of(p, out);
    if (!p.fallback_record_words || !p.fallback_vertices_per_workgroup)
        require(!ok && create_calls == calls, "an invalid program allocated on a retry");
    else
        require(ok && out && out->records_address, "a retry after a failure did not recover");
}
static void cleaned(const Program& p, unsigned expected_destroyed) {
    require(live.empty(), "failed initialization retained a successfully created buffer");
    require(destroy_calls == expected_destroyed, "wrong confirmed-allocation cleanup count");
    (void)p;
    require(fallback_buffers().empty(), "a failed pair was kept for later draws");
}
static void success_reuse(bool task) {
    Program p;
    p.fallback_task = task;
    FallbackBuffers* out = nullptr;
    require(fallback_buffers_of(p, out), "valid initialization failed");
    require(out && out->records_address, "successful result incomplete");
    require(out->records_bytes == 96, "expected a fixed record arena with an indirect command header");
    require(live.size() == (task ? 2u : 1u) && destroy_calls == 0,
            "successful allocations were destroyed");
    if (task) {
        require(out->payload_address != 0, "successful payload address missing");
        require(out->payload_bytes == 44, "expected a slot map and a payload for each task group, including a partial last group");
    }
    const auto calls = create_calls;
    auto* same = out;
    require(fallback_buffers_of(p, out) && out == same && create_calls == calls,
            "successful reuse changed");
}
static void run(const std::string& name) {
    Program p;
    FallbackBuffers* out = nullptr;
    if (name == "initial_allocation_failure") {
        fail_create = 1;
        require(!fallback_buffers_of(p, out), "first allocation failure was accepted");
        require(!out && live.empty() && destroy_calls == 0, "unconfirmed first output was destroyed");
        no_retry(p, out);
    } else if (name == "payload_allocation_failure") {
        fail_create = 2;
        require(!fallback_buffers_of(p, out), "payload allocation failure was accepted");
        require(!out, "failed result was published");
        cleaned(p, 1);
        no_retry(p, out);
    } else if (name == "records_address_zero") {
        zero_address = 1;
        require(!fallback_buffers_of(p, out), "zero records address was accepted");
        require(!out, "zero-address result was published");
        cleaned(p, 1);   // (the payload is not made once the records have no address)
        no_retry(p, out);
    } else if (name == "records_only_address_zero") {
        p.fallback_task = false;
        zero_address = 1;
        require(!fallback_buffers_of(p, out), "zero records-only address was accepted");
        cleaned(p, 1);
        no_retry(p, out);
    } else if (name == "payload_address_zero") {
        zero_address = 2;
        require(!fallback_buffers_of(p, out), "zero required payload address was accepted");
        require(!out, "zero-payload result was published");
        cleaned(p, 2);
        no_retry(p, out);
    } else if (name == "records_only_success") {
        success_reuse(false);
    } else if (name == "task_success") {
        success_reuse(true);
    } else if (name == "invalid_program") {
        p.fallback_record_words = 0;
        require(!fallback_buffers_of(p, out), "invalid program was accepted");
        require(!out && create_calls == 0 && destroy_calls == 0, "invalid program allocated resources");
        no_retry(p, out);
    } else if (name == "program_isolation") {
        fail_create = 2;
        require(!fallback_buffers_of(p, out), "first program payload failure was accepted");
        cleaned(p, 1);
        Program next;
        require(fallback_buffers_of(next, out) && out && out->records_address, "another program inherited failure");
        require(live.size() == 2 && destroy_calls == 1, "another program's buffers were freed or leaked");
    } else throw std::runtime_error("unknown authored case");
}
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    try {
        run(argv[1]);
        std::printf("PASS %s\n", argv[1]);
        return 0;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "FAIL %s: %s\n", argv[1], e.what());
        return 1;
    }
}
