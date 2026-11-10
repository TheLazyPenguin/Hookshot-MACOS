// The Vulkan back end's shared state (gpu/vk).
#pragma once

#include <cstdint>
#include <array>
#include <atomic>
#include <mutex>
#include <string>
#include <vector>

#include "vk_loader.h"
#include "vk_api.h"

#if defined(_MSC_VER) && (defined(_M_X64) || defined(_M_IX86))
#include <intrin.h>
#define HOOKSHOT_RDTSC() ((uint64_t)__rdtsc())
#define HOOKSHOT_PAUSE() _mm_pause()
#elif defined(__x86_64__) || defined(__i386__)
#include <x86intrin.h>
#define HOOKSHOT_RDTSC() ((uint64_t)__rdtsc())
#define HOOKSHOT_PAUSE() _mm_pause()
#endif

typedef struct VmaAllocation_T* VmaAllocation;   // (vk_mem_alloc.h's handle)

namespace mkwvk {

extern std::vector<std::string> gpu_device_names;
extern const MkwVkHost* host;
void logf(const char* fmt, ...);
void queue_flush_locked();   // (vk_replay.cpp, RX_VK_BATCH: held submits out; dev.present_mu held)
void queue_flush();          // (the same, taking dev.present_mu)
// (hookshot) held submits out, then vkDeviceWaitIdle with the present queue's lock taken too (dev.present_mu held): the device's
// every queue is synchronized by the host around it
void device_wait_idle_locked();

struct Device {
    VkInstance instance = VK_NULL_HANDLE;
    VkPhysicalDevice physical = VK_NULL_HANDLE;
    VkPhysicalDeviceProperties props{};
    VkPhysicalDeviceMemoryProperties memory{};
    VkPhysicalDeviceFeatures features{};
    VkDevice device = VK_NULL_HANDLE;
    uint32_t queue_family = 0;
    VkQueue queue = VK_NULL_HANDLE;
    // extensions in use
    bool mesh_shader = false, mesh_queries = false, external_memory_host = false, external_memory_fd = false, dma_buf_import = false, pipeline_library = false,
         graphics_pipeline_library = false, custom_border_color = false, dynamic_state3 = false,
         depth_clip_control = false, null_descriptor = false, index_uint8 = false, push_descriptor = false,
         conditional_rendering = false, provoking_vertex = false, vertex_divisor = false, stencil_export = false, memory_budget = false,
         checkpoints = false,   // (RX_VK_CHECKPOINTS: VK_NV_device_diagnostic_checkpoints)
         buffer_marker = false, // (RX_VK_CHECKPOINTS=1 without the NV extension: VK_AMD_buffer_marker, AMD and Intel)
         device_fault = false,  // (VK_EXT_device_fault: what a lost device faulted on)
         sparse_images = false, // (sparse resident 2D images on the queue: the terrain's huge arrays)
         sparse_buffers = false, // (sparse-bound buffers on the queue: a pool imported as several dma-bufs)
         view_2d_of_3d = false, // (VK_EXT_image_2d_view_of_3d: a 3D texture a 2D sample instruction reads)
         coop_matrix = false,   // (VK_KHR_cooperative_matrix with its feature)
         native_mma = false;    // (HMMA on it: the cooperative matrix test passed, vk_coopmat.cpp)
    bool eds3_polygon = false, eds3_clamp = false, eds3_blend = false, eds3_a2c = false;
    bool swapchain_colorspace = false;   // (hookshot) VK_EXT_swapchain_colorspace: HDR10 surfaces are listed
    bool hdr = false;                    // (hookshot) the swapchain is HDR10 (ST 2084, Rec. 2020): framegen_hdr writes it
    bool mesh_fallback = false;   // (hookshot) no VK_EXT_mesh_shader: task and mesh programs as compute shaders (vk_shader.cpp)
    bool task_mesh_fallback = false;
    bool uses_mesh_fallback(bool has_task) const {
        return mesh_fallback || (task_mesh_fallback && has_task);
    }
    VkPhysicalDeviceVulkan12Features vk12{};
    VkPhysicalDeviceVulkan13Features vk13{};
    VkShaderStageFlags sg32_stages = 0;   // (stages that run at 32 lanes when asked: the size the translated programs assume)
    uint32_t subgroup_size = 32, subgroup_max = 32;   // (the lanes a stage not pinned runs at, and the most it can have)
    VkDriverId driver_id{};
    uint32_t max_push_descriptors = 0;
    // no window (HOS_HEADLESS): presents go to an image of their own, which RX_VK_SHOTS can write out
    bool offscreen = false;
    // the window
    VkSurfaceKHR surface = VK_NULL_HANDLE;
    VkSwapchainKHR swapchain = VK_NULL_HANDLE;
    VkFormat swap_format = VK_FORMAT_UNDEFINED;
    VkExtent2D swap_extent{};
    std::vector<VkImage> swap_images;
    // (hookshot) how many of its images may be held acquired at once with no acquire timeout: the count less the surface's
    // minImageCount (the Vulkan spec's limit). vk_framegen.cpp's present ahead holds two
    uint32_t swap_spare = 0;
    std::vector<VkImageView> swap_views;   // (hookshot) a view of each, for Dear ImGui's overlays (VK_NULL_HANDLE: none)
    VkFormat swap_view_format = VK_FORMAT_UNDEFINED;   // (their format: the UNORM one of an sRGB swapchain when it can be)
    bool swap_mutable = false;   // (VK_KHR_swapchain_mutable_format: an sRGB swapchain's images viewed as UNORM)
    std::vector<VkSemaphore> swap_rendered;   // present waits belong to acquired images, not frame slots
    std::mutex present_mu;   // (the swapchain: presents and resizes)
    std::atomic<uint64_t> swap_resize{0};   // (a new window size, width << 32 | height: the next present makes the swapchain)
    // (hookshot) a queue of a compute family for vkQueuePresentKHR alone (vk_main.cpp create_device; RX_VK_PRESENT_QUEUE=0 / 1).
    // VK_NULL_HANDLE: presents go on `queue` under present_mu. Its own lock: taken after present_mu, never before it
    VkQueue present_queue = VK_NULL_HANDLE;
    std::mutex present_queue_mu;
    uint32_t present_family = 0;   // (present_queue's family, the swapchain's images shared with it)
};
extern Device dev;

/// A range of guest memory as the GPU sees it: a buffer (an imported pool), the offset in it, and its device address
struct BufferRef {
    VkBuffer buffer = VK_NULL_HANDLE;
    uint64_t offset = 0, size = 0;
    VkDeviceAddress address = 0;
    explicit operator bool() const {
        return buffer != VK_NULL_HANDLE;
    }
};
bool memory_init();                                   // vk_memory.cpp
void memory_cpu_owned(uint64_t guest, uint64_t size);   // (hookshot: words the replay writes on the CPU, left out of write-backs)
// (hookshot) The replay's own CPU writes of guest memory, by GPU address: every one goes through guest_cpu_write (or, for a
// write made in pieces, host->gpu_write and then guest_cpu_wrote over the whole range), so that the write-back diff's shadows
// hear of it before this submission's write-back (vk_memory.cpp, "the write-back's diff"). tests/test_wb_diff_cpu_writes.py
int guest_cpu_write(uint64_t gpu, const void* src, uint64_t n);
void guest_cpu_wrote(uint64_t gpu, uint64_t n);
void memory_table_begin();                         // (hookshot: a recording's page table changes held back for its upload commands)
bool memory_table_flush();
uint64_t memory_guest_pages();                        // (hookshot: the device address of guest memory's page table, 0: none)
void memory_sync();                                   // (at each submit: pools the game made or let go)
BufferRef gpu_buffer(uint64_t gpu, uint64_t size);   // (empty when no pool holds the range)
/// A range as a binding of the replay sees it: the pool's VRAM mirror when it has one (vk_memory.cpp), else the
/// imported pool. written: the GPU may write it (copied back to guest memory at the submission's end).
BufferRef gpu_buffer_bind(uint64_t gpu, uint64_t size, bool written);
BufferRef stream_copy(const void* src, uint64_t n);   // vk_draw.cpp: bytes in the recording's stream, as a binding
/// Authored constants in the recording's stream: never recycled until its recording completes.
/// Fill mapped, then flush memory through binding.offset + binding.size before GPU use.
struct UniformUpload {
    BufferRef binding;
    uint8_t* mapped = nullptr;
    VmaAllocation memory = nullptr;
};
UniformUpload uniform_upload(uint64_t size);   // empty: no recording or no room; no history consumed
/// Changes when a read binding remembered earlier must be looked up again (a pool left, a mirror was made, a new submission)
uint64_t gpu_bind_stamp();
/// Around each submission's recording: mirrors wanted since the last one are made (begin), what the GPU wrote into
/// mirrors goes back to guest memory (end, outside any pass, before the closing barrier)
void memory_begin_submission();
void memory_sync_mirrors_before_segments();   // (hookshot: vk_memory.cpp)
bool probe_on();                                // (hookshot: vk_draw.cpp, RX_VK_PROBE)
bool probe_serial();
void probe_dump_all(const char* why);
void probe_log(uint64_t frame);
void memory_end_submission(VkCommandBuffer cmd);
/// The game made a memory pool (gpu address, bytes): imported in the background, before it is used
/// RX_VK_CHECKPOINTS: the draws the GPU reached, logged once the device is lost (vk_draw.cpp)
void checkpoints_report();
/// The device is lost: that report once, then the process ends (vk_replay.cpp)
[[noreturn]] void device_lost();
/// VK_AMD_buffer_marker's buffer, for RX_VK_CHECKPOINTS on a device without the NV checkpoints (vk_draw.cpp)
void buffer_markers_init();
void coopmat_init();   // vk_coopmat.cpp (once the device is made)
/// A marker of another kind of GPU work (m: mirror sync, b: write-back, u: texture upload, g: GPU unswizzle; key: its
/// pool or texture), RX_VK_CHECKPOINTS
void checkpoint_mark(VkCommandBuffer cmd, uint64_t key, char kind);

/// Parallel replay (vk_replay.cpp, RX_VK_PARALLEL): while segments of a submission are recorded on several threads,
/// what they share (textures and their uploads, programs, pipelines, samplers, pools and memory stamps) is used under
/// one lock; the per-draw caches are each thread's own
extern std::atomic<bool> par_active;
extern std::atomic<int64_t> par_lock_wait_ns, par_locks;   // (contention: the time threads waited for it)
std::recursive_mutex& par_mutex();
int64_t par_now_ns();
struct ParLock {
    bool on;
    explicit ParLock(bool want = true) : on(want && par_active.load(std::memory_order_relaxed)) {
        if (!on) return;
        par_locks.fetch_add(1, std::memory_order_relaxed);
        if (par_mutex().try_lock()) return;
        const int64_t t0 = par_now_ns();
        par_mutex().lock();
        par_lock_wait_ns.fetch_add(par_now_ns() - t0, std::memory_order_relaxed);
    }
    ~ParLock() {
        if (on) par_mutex().unlock();
    }
    ParLock(const ParLock&) = delete;
    ParLock& operator=(const ParLock&) = delete;
};
void memory_pool_created(uint64_t gpu, uint64_t size);
/// Whether guest memory in [lo, hi) is in an imported pool, live or retired (the GPU may read or write it)
int memory_guest_imported(uint64_t lo, uint64_t hi);
void memory_stats(int64_t* mirrors, uint64_t* mirror_mb, int64_t* sync_bytes, int64_t* sync_copies, int64_t* wb_bytes);
// Page write generations (vk_memory.cpp, after totk-pc-recomp's vk_memory.c): at each submit the guest pages the CPU
// wrote since the last one (the soft write watch) are stamped with a new generation; a texture uploaded at
// generation g is stale when a page of its storage carries a newer one. GPU writes into guest memory that textures
// may be read from (storage buffers, buffer copies) are stamped the same way.
void memory_collect_written();
/// RX_VK_CAPTURE (on with the mirrors; =0 off): at a submit, on the submitting thread, the pages the CPU wrote since the
/// last one, and a copy of them as they are then; the replay stamps them and fills the mirrors from that copy
void memory_capture_submit();
/// The replay of the next submit: its capture (false: none, the pages are collected now as before)
bool memory_take_capture(uint64_t value, uint64_t completed);
bool memory_capture_now(uint64_t value, uint64_t completed);   // (hookshot: made and taken at once)
/// The submission the replay records next (bindings note it: a pool's mirror is in use until it is done)
void memory_recording_value(uint64_t value, uint64_t completed);
/// RX_VK_TEX_CAPTURE (on with the capture; =0 off): the storage of a texture uploaded from guest memory joins the
/// capture (its pool up to 256 MB, else its 2 MB regions), and what the capture took of it is kept for the uploads
void memory_note_texture_upload(uint64_t guest, uint64_t size);
/// Whether [guest, guest + n) has pages kept as a capture took them
bool memory_has_shadow(uint64_t guest, uint64_t n);
/// A read of guest memory by the replay as the submission being recorded had it: the pages a kept capture holds from
/// there (the game writes several submits ahead of the replay), the rest from guest memory. False when unreadable
bool memory_read_as_submitted(uint64_t gpu, void* dst, uint64_t n);
uint64_t memory_capture_view();          // (bumped when a capture is published or any page is stamped)
uint32_t memory_page_stamp(uint64_t gpu); // (that address's page only)
uint64_t gpu_pool_end(uint64_t gpu);   // (hookshot) where the memory pool holding that address ends, 0: in none (vk_memory.cpp)
uint64_t gpu_pool_start(uint64_t gpu); // (EvilOOT) and where it begins
bool create_buffer_cached(uint64_t size, VkBufferUsageFlags usage, VkBuffer& buffer, VmaAllocation& allocation,
                          void** mapped, bool dedicated = false);   // (vk_vma.cpp: cached host memory, mapped)
void flush_mapped(VmaAllocation allocation, uint64_t size);
void flush_mapped_range(VmaAllocation allocation, uint64_t offset, uint64_t size);
void invalidate_mapped(VmaAllocation allocation, uint64_t size);   // (the CPU is to read what the GPU wrote: a no-op in coherent memory)
void memory_stamp_gpu(uint64_t guest, uint64_t size);   // (a GPU write: memory_stamp, and the pages noted)
void memory_protect_gpu(uint64_t guest, uint64_t size);  // (RX_VK_PROTECT_BARE=1: pages a shader writes through a table pointer)
/// (vk_replay.cpp) guest memory as the stream's place sees it: as submitted, the stream's uniform updates before it over it
bool ub_read(uint64_t addr, void* dst, uint64_t n);
/// [guest, guest + n) as of the submit being replayed: live itself, or scratch holding it with the kept pages over it
const uint8_t* memory_as_submitted(uint64_t guest, const uint8_t* live, uint64_t n, std::vector<uint8_t>& scratch);
void memory_drop_shadow(uint64_t guest, uint64_t size);   // (a write the capture did not take: the copies go)
/// (EvilBoyce) the newest submission value whose write-back reaches into [guest, guest + size) (0: none ever); *ever set
/// when any write-back ever did
uint64_t memory_writeback_value(uint64_t guest, uint64_t size, bool* ever);
void memory_note_readback(uint64_t guest, uint64_t size);   // (PR 430) a CPU read of GPU results: see memory_rb_refresh
bool memory_rb_refresh(VkCommandBuffer up);
void memory_rb_recording_begun();   // (hookshot) at a recording's start, on its thread: the submission it joins (memory_rb_refresh)
void memory_rb_segments_begin(uint64_t base, uint64_t n);   // (and a parallel replay's segments: their order, base on)
/// (hookshot) a range a program may write in the mirror that is not bound as written (not copied back): memory_rb_refresh
void memory_note_gpu_write(uint64_t gpu, uint64_t size);
/// (vk_replay.cpp) The GPU's progress on the recordings' timeline, and a wait for it to reach v
uint64_t vk_timeline_completed();
/// A future submission completion covering images retired during replay; zero: no safe value.
uint64_t vk_retirement_value();
void vk_timeline_wait(uint64_t v);
uint32_t memory_generation();
/// 1: a page of [guest, guest + size) was written after generation gen; 0: none was
bool memory_written_since(uint64_t guest, uint64_t size, uint32_t gen);
void memory_stamp(uint64_t guest, uint64_t size);   // a write the watch does not see (GPU writes, host writes)
/// The page runs of [guest, guest + size) written after gen, as byte ranges from guest (appended to out)
void memory_written_runs(uint64_t guest, uint64_t size, uint32_t gen, std::vector<std::pair<uint64_t, uint64_t>>& out);
uint64_t memory_pages_collected();                  // (statistics)

/// An NVN format as Vulkan stores it (vk_formats.cpp): ASTC is decoded to RGBA8, block_w x block_h
/// Bytes per block and block size of an NVN format (ASTC blocks are 16 bytes)
int nvn_block_size(int format, int* bw, int* bh);

struct VkFormatInfo {
    VkFormat format;
    bool astc;
    int block_w, block_h;
};
VkFormatInfo vk_format(int nvn_format);
bool is_depth_format(VkFormat f);
bool has_stencil(VkFormat f);

// device memory (vk_vma.cpp, Vulkan Memory Allocator)
bool vma_init(PFN_vkGetInstanceProcAddr gipa);
/// (textures: from the textures' own pool, the one image_compact_* moves allocations in: vk_texture.cpp's compaction)
bool create_image(const VkImageCreateInfo& ci, VkImage& image, VmaAllocation& allocation, bool dedicated = false, bool target = false,
                  bool textures = false);
// (hookshot) the textures' pool compacted: VMA's defragmentation, a pass at a time (vk_texture.cpp's compact_step)
struct ImageMove {
    VmaAllocation src;   // (the allocation to move: it stays the texture's, and points at the new place once the pass ends)
};
/// The free space inside the textures' pool's blocks, and what the blocks hold in all; false without the pool
bool textures_pool_usage(uint64_t* block_bytes, uint64_t* free_bytes);
bool image_compact_begin(uint64_t max_bytes_a_pass, uint32_t max_moves_a_pass);
bool image_compact_active();
/// A pass begun: the moves VMA asks for. False: nothing left to move, the compaction is over (then *freed_bytes and
/// *freed_blocks say what went back to the driver in all)
bool image_compact_pass(std::vector<ImageMove>& moves, uint64_t* freed_bytes, uint32_t* freed_blocks);
/// The new image of move i bound at its new place; false: not bound (the caller destroys the image and ignores the move)
bool image_compact_bind(size_t i, VkImage image);
void image_compact_ignore(size_t i);
/// The pass ended (its old images destroyed by the caller, nothing of the pool freed since it began). False: that was
/// the last one; then *freed_bytes and *freed_blocks say what went back to the driver in all
bool image_compact_pass_end(uint64_t* freed_bytes, uint32_t* freed_blocks);
void destroy_image(VkImage image, VmaAllocation allocation);
/// What an allocation really takes (VkMemoryRequirements.size: padding, alignment, the driver's metadata), 0 for none
uint64_t allocation_size(VmaAllocation allocation);
/// (dedicated: its own memory object, not a share of a 64 MB block: for the 16 to 32 MB ones that fit two to a block and leave
/// the rest of it free; RX_VK_BLOCK_BUFFERS=1: as before)
bool create_buffer(uint64_t size, VkBufferUsageFlags usage, bool host_visible, VkBuffer& buffer,
                   VmaAllocation& allocation, void** mapped, bool dedicated = false);
void destroy_buffer(VkBuffer buffer, VmaAllocation allocation);
/// A buffer in VRAM only (within the driver's budget), or false
bool create_device_buffer(uint64_t size, VkBufferUsageFlags usage, VkBuffer& buffer, VmaAllocation& allocation, bool dedicated = false);
/// Device-local memory this process uses and what the driver allows it now (VK_EXT_memory_budget), summed over the
/// device-local heaps; false when unknown
bool vram_usage(uint64_t* used, uint64_t* budget, uint64_t* block_free = nullptr);
/// vram_usage asked of the driver now (VMA asks again for a new frame index), for the status line; false when the driver
/// gives no budget (VK_EXT_memory_budget): used is then the game's own allocations
bool vram_usage_now(uint64_t* used, uint64_t* budget);
void vma_log_heaps();
void vma_log_image_blocks();   // (the image pools' blocks: what they hold, and their free ranges)
PFN_vkGetInstanceProcAddr instance_proc();   // vk_main.cpp

bool create_swapchain(uint32_t width, uint32_t height);
bool replay_start();                          // vk_replay.cpp
bool precompile_wanted();                     // vk_draw.cpp
void precompile_run(void (*progress)(size_t done, size_t total));
bool prepare_run(void (*progress)(size_t done, size_t total), bool background);
bool prepare_is_update();
void prepare_background();
void state_list_run();                        // (an update: the state list's pipelines noted before precompile_run)
void predict_run(void (*progress)(size_t done, size_t total));   // (after a prepare_run that prepared: the notes' predictions)
/// (hookshot) The window was closed while the shaders were prepared: prepare_run and precompile_run take nothing more and return,
/// what is done kept (the program cache, the driver's) and not counted as a start that ended inside them
void prepare_stop();
bool prepare_stopped();
void fill_replay_table(MkwVkRenderer& t);     // vk_replay.cpp

} // namespace mkwvk

// ---- a scoped timer per phase of the replay (logged per frame with the frame statistics) ----
namespace mkwvk {
enum ProfPhase { PROF_SUBMIT, PROF_PRESENT, PROF_DRAW, PROF_DESC, PROF_TEXGET, PROF_UPLOAD, PROF_PIPE, PROF_PROGRAM,
                 PROF_CMDS, PROF_DISPATCH, PROF_MEMSYNC, PROF_QSUBMIT, PROF_SLOTWAIT, PROF_COUNT };
extern int64_t prof_ns[PROF_COUNT];
/// Nanoseconds from a performance-counter reading. An integer number of nanoseconds per tick is a multiply, so a
/// reading past 2^53 does not lose its low bits the way the double divide does.
inline int64_t perf_ticks_to_ns(int64_t ticks, int64_t freq) {
    if (freq > 0 && 1000000000LL % freq == 0)
        return ticks * (1000000000LL / freq);
    if (freq <= 0) return 0;
    return (int64_t)((double)ticks * 1e9 / (double)freq);
}
// A cheap nanosecond clock for the per-phase replay timers. Ten QueryPerformanceCounter reads a draw were ~4% of
// the GPU thread (gpu/render/rx_internal.h). The hot path reads the invariant TSC; the counter calibrates the scale once.
inline int64_t prof_now() {
#if defined(HOOKSHOT_RDTSC)
    struct Scale { double ns_per; bool ok; };
    static const Scale scale = [] {
        LARGE_INTEGER f, a, b;
        QueryPerformanceFrequency(&f);
        const uint64_t c0 = HOOKSHOT_RDTSC();
        QueryPerformanceCounter(&a);
        volatile int sink = 0;
        for (int i = 0; i < 400000; i++) { HOOKSHOT_PAUSE(); sink += 1; }
        const uint64_t c1 = HOOKSHOT_RDTSC();
        QueryPerformanceCounter(&b);
        const int64_t dns = perf_ticks_to_ns(b.QuadPart - a.QuadPart, f.QuadPart);
        Scale s;
        s.ok = c1 > c0 && dns > 0 && sink > 0;
        s.ns_per = s.ok ? (double)dns / (double)(c1 - c0) : 0.0;
        return s;
    }();
    if (scale.ok) return (int64_t)((double)HOOKSHOT_RDTSC() * scale.ns_per);
#endif
    LARGE_INTEGER t;
    QueryPerformanceCounter(&t);
    static const int64_t freq = [] { LARGE_INTEGER f; QueryPerformanceFrequency(&f); return f.QuadPart; }();
    return perf_ticks_to_ns(t.QuadPart, freq);
}
// (hookshot) The per-draw phases (PROF_HOT) run a few thousand times a frame, and each timer is two counter reads: ~25k
// reads a frame were ~2% of the replay thread. One draw in eight is timed, picked at random per thread, and counted eight
// times: the outermost PROF_HOT on the thread picks, and those nested in it follow, so a phase never reads more than the
// one around it. What is slow and rare inside (a program or pipeline made, a texture created or uploaded, a wait) is timed
// by PROF / PROF_EXACT and counted once as it is, sampled draw or not: the PROF_HOT scopes around it weigh only the rest.
// Every scope timed (prof_full): RX_VK_PROF_ALL=1, RX_VK_SLOW_LOG, and while RX_VK_BENCH replays its frame.
inline std::atomic<int> prof_full{getenv("RX_VK_PROF_ALL") || getenv("RX_VK_SLOW_LOG") ? 1 : 0};
struct ProfThread {
    uint32_t rng;    // (xorshift32, seeded at the thread's first pick)
    int open, k;     // (the PROF_HOT scopes open, and the outermost one's weight: 0 not timed)
    int64_t exact;   // (the nanoseconds PROF / PROF_EXACT timed on this thread so far)
};
inline thread_local ProfThread prof_t;
struct ProfScope {
    int phase;   // (-1: PROF_EXACT, no phase of its own)
    int64_t t0, x0;
    explicit ProfScope(int p) : phase(p), t0(prof_now()), x0(prof_t.exact) {}
    ~ProfScope() {
        const int64_t dt = prof_now() - t0;
        if (phase >= 0) prof_ns[phase] += dt;
        prof_t.exact = x0 + dt;   // (what was exact inside is part of dt: not counted twice)
    }
};
/// A thread's first state: splitmix64 of a counter, so the threads' sequences are unrelated; never 0, xorshift's fixed point
inline uint32_t prof_seed() {
    static std::atomic<uint64_t> threads{0};
    uint64_t z = (threads.fetch_add(1, std::memory_order_relaxed) + 1) * 0x9E3779B97F4A7C15ull;
    z = (z ^ z >> 30) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ z >> 27) * 0x94D049BB133111EBull;
    return (uint32_t)((z ^ z >> 31) >> 32) | 1u;
}
inline int prof_pick(ProfThread& t) {   // (the weight: 8 one time in eight, else 0; 1 when every scope is timed)
    if (prof_full.load(std::memory_order_relaxed)) return 1;
    if (!t.rng) t.rng = prof_seed();
    t.rng ^= t.rng << 13, t.rng ^= t.rng >> 17, t.rng ^= t.rng << 5;
    return t.rng >> 29 ? 0 : 8;   // (the top bits: xorshift's low ones are its weakest)
}
struct ProfScopeHot {
    int phase, k;
    int64_t t0, x0;
    explicit ProfScopeHot(int p) : phase(p) {
        ProfThread& t = prof_t;
        if (!t.open++) t.k = prof_pick(t);
        k = t.k, x0 = t.exact, t0 = k ? prof_now() : 0;
    }
    ~ProfScopeHot() {
        ProfThread& t = prof_t;
        const int64_t x = t.exact - x0;   // (timed exactly inside: once, as it is)
        if (k) prof_ns[phase] += (prof_now() - t0 - x) * k + x;
        else if (x) prof_ns[phase] += x;
        t.open--;
    }
};
} // namespace mkwvk
#define PROF(phase) ::mkwvk::ProfScope prof_scope_##phase(::mkwvk::phase)
#define PROF_HOT(phase) ::mkwvk::ProfScopeHot prof_scope_##phase(::mkwvk::phase)   // (the per-draw phases: sampled, above)
#define PROF_EXACT() ::mkwvk::ProfScope prof_scope_exact(-1)   // (a slow, rare path inside them: timed exactly, above)
