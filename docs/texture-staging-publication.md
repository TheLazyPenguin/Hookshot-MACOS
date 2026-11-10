# Texture staging cache publication

Texture staging arenas use mapped sequential-write host memory. That memory is
not required to be coherent: writing the pointer alone does not publish encoded
ASTC blocks or CPU-converted texels to the GPU.

Both staging consumers now flush the completed allocation-relative slice before
its GPU use. Staging carries its VMA allocation alongside the buffer/offset, and
slice starts respect `nonCoherentAtomSize` as well as the consumer alignment.
This keeps a rounded cache flush from sharing an atom with another slice already
being read by a submitted parallel segment. VMA handles allocation offsets, cache
rounding and coherent-memory no-ops. No additional queue wait is introduced.

CPU uploads publish after conversion workers join, before the slice is added to
the pending image copy. ASTC uploads publish after gathering their layers, before
the GPU decoder is recorded. This also covers uploads redirected into an earlier
parallel init command buffer, without depending on a later worker's submit hook.
Arena sizes, allocation fallback, lifetime/reuse, format conversion, shader paths,
descriptor policy and the renderer ABI remain unchanged.

The game-free fixture executes actual staging allocation and the actual ASTC
gather/publication prefix and CPU publication/copy-description region. Authored
CPU/device caches distinguish coherent and noncoherent memory; it does not execute
the full CPU converters or ASTC shader. Cases cover nonzero offsets, multiple
slices/arenas, completion-based reuse, 1024-byte atoms, failed allocation and empty
flushes. A source-order guard keeps CPU publication after worker joins. The range
helper itself is extracted from production. These checks do not establish a
physical noncoherent GPU reproduction or campaign/performance coverage.

Run `tests/test_texture_staging_publication.py --headers <Vulkan include> --cxx <compiler>`.
Linux additionally supports `--sanitize` for AddressSanitizer/UndefinedBehaviorSanitizer.
