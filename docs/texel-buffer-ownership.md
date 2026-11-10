# Imported texel-buffer view ownership

A formatted-buffer view describes a particular Vulkan buffer, offset, range and
format. A guest GPU address is not that identity: its mapping can change, and an
import may be replaced or returned under the existing memory-pressure policy.

The old static guest-address cache returned before `gpu_buffer`, so cache hits
also skipped the import's `last_value` use stamp. It ignored creation failure and
kept its entries when the backing was destroyed. These behaviors are reproduced
without a game in `tests/test_texel_buffer_ownership.py`.

The cache now resolves/stamps the backing on every request, then looks up the
exact format/offset/clamped-range key under that `VkBuffer`. Sampled and storage
uses share the same Vulkan view, while storage uses still call
`texture_gpu_wrote`. Missing mapping and invalid alignment/range do not enter the
cache. A failed creation is retried on a later present, with at most one failed
attempt per backing per present; existing successful views remain usable. Error
output handles are neither returned nor destroyed. Metadata allocation failure
returns no view; a newly created view whose insertion fails is destroyed.

All eight raw imported-buffer destruction sites in `vk_memory.cpp` use one
wrapper that releases the owner's views before destroying its buffer. This
includes allocation rollback, redundant background imports, completed retired
imports and completed active-import eviction. The existing completion values,
keep-retired/vendor policy and import-pressure thresholds are unchanged. There
is no additional GPU wait. Old views stay available until that backing reaches
its existing destruction point; numerical handle reuse starts an empty cache.

The view registry has its own mutex because unpublished imports may be dropped
by the import worker. Lookup takes `pools_mu` inside `gpu_buffer` before taking
the view mutex; release never takes `pools_mu`. Published imports remain protected
by their recorded use values. This does not make destruction concurrent with a
still-recording user safe or replace the renderer's submission lifetime rules.

The game-free fixture executes the real view consumer, `gpu_buffer`, release
wrapper, retired-import reaper and active-eviction completion loop. Only Vulkan,
guest mapping, pool lookup and completion inputs are modeled. A throwing
allocator exercises real `std::map` allocation/commit failures. Cases cover
backing remap, exact keys, cache-hit liveness, late mapping, allocation failure,
bounded retry, independent owners, deferred release, handle reuse, storage,
alignment/limits and concurrent lookup/unpublished-import release.

Run through `python -I -B tests/run_all.py texel_buffer_ownership --strict`, or
directly with `--headers <Vulkan include folder> --cxx <compiler>`. The direct
runner also supports `--sanitize` on Linux. The fixture does not reproduce native
GPU memory pressure, a device loss, a full campaign or a performance gain.
