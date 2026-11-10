# Sampler cache admission and retry

NVN samplers pass through an ID/generation table, a thread-local parameter/handle
cache and a global owning cache. Ignoring `vkCreateSampler` failure could admit
an undefined error-output handle, or retain null in those caches indefinitely.
Checking only the factory result would still let the outer ID table retain null.

Only successful handles now enter the owning or acceleration caches. The ID
table does not mark a failed creation resolved for that registration generation.
Failure of one key is bounded to one attempt per present; later presents can
retry the same ID, including on a fresh thread. Successful hits and unrelated
keys remain usable. Failure keys are cleared at a later present. If failure
tracking itself cannot allocate, new keys wait until the next present, while
already-owned successful handles still work.

A newly created sampler whose global cache insertion throws is destroyed before
returning null. An error-output handle is never returned or destroyed. The
parameter and thread-local handle tables are acceleration caches: allocation
failure there does not discard registered parameters or destroy a valid global
handle. Existing registration/version checks, immutable successful sampler
lifetimes, filter/LOD/compare/anisotropy/border/reduction policies and the
renderer API are unchanged. Existing replay locking serializes the shared cache
and failure tracking; no new worker or GPU wait is added.

Before either pushing descriptors or allocating/updating a descriptor set,
`bind_descriptors` rejects a combined-image-sampler array containing a failed
sampler. It leaves the pushed-state cache untouched and returns failure to
the existing draw, compute and mesh-fallback callers. A later rebuild can retry;
no replacement sampler changes the requested filtering policy. Storage images
continue to accept their unused null sampler.

`tests/test_sampler_admission.py` executes the complete actual sampler factory,
ID-cache consumer and parameter policy helpers, using the public NVN parameter
layout. Vulkan, registration/environment/hash inputs and the replay-lock boundary
are modeled. Standard containers use tagged throwing allocators to target each
cache operation. The owning-cache fault is armed after successful resource
creation, independent of an STL's sentinel/bucket allocation choices. The 108
cases cover failure/retry/cache chains, ownership and allocation rollback,
independent keys, registration changes, threads and unchanged sampler policies.
The actual complete descriptor-binding function and fingerprint helpers run
against modeled Vulkan calls too: cold and warm failures in an array's second
element, graphics/compute, pooled sets, both pushed-state layouts, full pushes,
next-present recovery and storage images. Rejected writes must produce no
allocation, update, bind or push and must preserve the prior fingerprint.

Run `python -I -B tests/run_all.py sampler_admission --strict`, or invoke the
test with `--headers <Vulkan include folder> --cxx <compiler>`; `--sanitize` is
supported on Linux. Game-free failure models do not prove native OOM/device-loss
recovery, image-quality changes, a full campaign or performance improvements.
