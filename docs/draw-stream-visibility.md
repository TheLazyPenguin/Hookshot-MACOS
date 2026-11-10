# Draw-stream visibility

A recording's CPU-written uniform, vertex/index conversion and buffer-copy streams
are published through VMA before their commands reach the GPU. Host-visible
sequential-write allocations need not be coherent; queue submission alone does not
flush their CPU caches.

The flush names the recording slot, including slots filled by worker threads. It
covers each stream used before growth and the current used prefix. Earlier stream
capacities are flushed in full (including unused padding); later retained streams
from an earlier recording are left alone. Existing VMA cache-range alignment and
coherent-memory handling apply. No per-draw flush or new allocation policy is added.

Both ordinary/batched submissions and successful parallel segments publish their
streams. Failed segments keep their existing no-submit policy. Descriptor lifetime,
slot completion/reuse and batching behavior remain unchanged. The internal draw
helper does not change the host/renderer API.

`tests/test_draw_stream_visibility.py` runs production growth/reservation/copy,
recording reset and complete serial submit code, plus the actual parallel segment
submission tail, with independent expected GPU input bytes and separate host
caches. Worker-to-main slot identity, retained-stream reuse, failed growth, empty
recordings, batching and skipped segments are covered. Vulkan queue/fence behavior
is modeled; this is not physical noncoherent hardware, a concurrency sanitizer,
shader execution or campaign coverage. Global fallback buffers and mixed CPU/GPU
argument rings have separate lifetimes and are outside this stream contract.
