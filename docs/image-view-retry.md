# Recovering transient texture view failures

A failed image-view allocation used to enter the texture's view cache as a null
handle. A later request then returned that null without trying the driver again,
even after memory became available. This affected general sample/storage/attachment
views and the ASTC and GPU-unswizzle storage-view caches.

Successful views still enter the same texture-owned cache. Host/device allocation
failures remain uncached; after one failed attempt, uncached views of that texture
wait until the next texture frame before trying again. Existing valid cache entries
remain usable and other textures are independent. Unsupported configurations keep
their permanent negative-cache behavior. A successful block-texel single-layer
compatibility fallback still wins; if both attempts fail and either reports OOM,
the failure remains transient.

If the cache cannot commit a newly created view, that view is destroyed immediately
because no recorded work owns it. The texture backs off for the rest of the frame.
Previously cached handles retain their existing deferred destruction/lifetime.
Formats, swizzles, subresources, queue waits and the renderer ABI are unchanged.

This does not change the higher-level failed texture-upload generation policy:
some uploads are intentionally tried again only after a storage write. It makes
the next actual view request retryable, not a promise of immediate whole-texture
recovery. Formatted buffer views have a separate cache/lifetime contract and are
outside this change. Device-loss recovery is also outside this allocation policy.

The game-free fixture executes the actual factory, complete general texture_view,
ASTC all/layer functions and the GPU-unswizzle cache/early-return region. Authored
Vulkan failures and throwing cache storage cover48 cases across six consumer
routes, including bounded retry, permanent failures, independent textures/keys,
rollback, BC fallback and unchanged view descriptions. Format capabilities and
driver allocations are modeled; this does not establish native GPU-OOM recovery,
driver validation, visual campaign coverage or performance.

Run `tests/test_image_view_retry.py --headers <Vulkan include> --cxx <compiler>`.
Linux additionally supports `--sanitize` for AddressSanitizer/UndefinedBehaviorSanitizer.
