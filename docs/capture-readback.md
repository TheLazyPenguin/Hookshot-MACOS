# Capture copies and CPU visibility

Normal screenshots, generated-frame screenshots and binary frame-log slots are
GPU-written mapped staging buffers. Their contents reach CPU consumers through
three distinct requirements:

1. Record a copy-write to host-read dependency for the copied buffer range.
2. Wait for its owning GPU submission or presentation-slot fence.
3. Invalidate that allocation range before reading a non-coherent host cache.

`capture_host_read_barrier` uses COPY/TRANSFER_WRITE to HOST/HOST_READ, offset0
and the complete copied byte count, with no queue ownership transfer. Each
capture producer records it immediately after its copy. Existing timeline/fence
waits remain in place. `invalidate_mapped` delegates cache atom alignment and
coherent-memory handling to VMA.

`shot_pixels` owns normal screenshot bytes after the timeline wait. A pending
screenshot already copied to CPU memory keeps using that snapshot if its parity
slot is reused; it must not invalidate or reread the reused GPU slot. Generated
screenshots invalidate their own allocation after the same completed value.
Frame-log collection invalidates only a used slot after its fence wait and
preserves timestamp, sequence and kind metadata.

The source-sliced regression executes the actual three copy/dependency tails
and the CPU consumers against authored device bytes, host-domain availability
and coherent/non-coherent caches. Four phases (normal, owned snapshot, made,
binary log), two cache modes and two host-visibility modes give16 scenarios.
Permissive host visibility remains a positive control; explicit visibility
detects a missing producer dependency even on coherent memory. These models
verify protocol and ownership, not physical non-coherent GPU memory or driver
behavior. PNG encoding and generic device-loss/wait-error handling are outside
this test; no performance or intended visual change is claimed.

References: [Khronos host readback](https://docs.vulkan.org/guide/latest/synchronization_examples.html#cpu-read-back-of-data-written-by-a-compute-shader)
and [VMA cache management](https://gpuopen-librariesandsdks.github.io/VulkanMemoryAllocator/html/memory_mapping.html).
