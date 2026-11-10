# Per-recording allocation admission and retry

Recording streams carry CPU-authored shader banks, copied UBOs and generated
indices. Their buffer, VMA allocation, mapping and ownership entry must all exist
before a reservation can authorize a CPU write or return a binding.

`stream_insert` commits a complete mapped stream to its recording's container.
Failed creation, missing mapping or container allocation releases only the new
resource. Initial stream creation is independent of descriptor-pool retry, so a
failed pool cannot append another primary stream on every recording. A failed
primary stream remains absent and can be retried on the slot's next recording.
The active stream is explicitly empty until that succeeds; reservations reject
it rather than treating its requested capacity as allocated memory.

Growth preserves earlier streams because already-recorded bindings reference
them. Its cursor, ownership and counters change only after the new entry commits.
Reservation and MiB rounding check representability before arithmetic can wrap.
Successful growth sizes, cached-stream reuse, initial sizes, retention and the
opt-out policy are preserved.

Driver-bank cache generations and grid metadata commit after a successful
upload, or after a confirmed identical-byte cache hit. Failed reservation keeps
the previous generation attached to its previous bytes, so retry rebuilds the
changed bank instead of incorrectly treating stale bytes as current.

The descriptor allocation fallback rejects a missing pool. A new extra pool is
owned only after its first set allocation and the ownership entry both succeed.
Failure destroys that new pool, including any set allocated from it, before any
descriptor update/bind occurs. Existing pools remain valid for retry; a missing
primary pool can be retried by the next recording. Push-descriptor behavior and
the renderer interface are unchanged.

`tests/test_recording_admission.py` executes actual allocation/reservation/reset
functions and the descriptor allocation tail against authored VMA/Vulkan calls.
Only the container boundary is adapted to inject allocation exceptions. Cases
cover healthy byte copies, initial/growth failures, absent mappings, commit
failure, pool/set failure, retry, old binding/pool preservation, parallel slots,
aligned bounds, overflow, disabled growth and retention. Global defaults are
seeded outside this per-recording contract. The tests model resource failures;
they do not prove native driver OOM recovery, campaign behavior or performance.
Global default images/buffers, device loss and other resource families retain
their existing behavior. No cache visibility policy is changed here.

References: [VMA allocation ownership](https://gpuopen-librariesandsdks.github.io/VulkanMemoryAllocator/html/group__group__alloc.html)
and [Vulkan descriptor allocation](https://docs.vulkan.org/refpages/latest/refpages/source/vkAllocateDescriptorSets.html).
