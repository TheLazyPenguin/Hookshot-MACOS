# Binding imported buffers before publication

The host-pointer and non-sparse DMA-buf import factories used to ignore
`vkBindBufferMemory`'s result. An allocation could succeed while binding failed;
both factories would then query the unbound buffer's address and return success.

Both factories now check binding before publishing an import. Failed binding
uses the existing allocation-failure cleanup point to destroy the unused buffer
and free its successfully allocated/imported memory. Host-pointer failure clears
its resource handles, records the binding result and enters the existing range
hold. Allocation failure does not free an undefined output memory handle. A DMA
failure still permits the host-pointer fallback; it does not put that range on
hold before the fallback has had its attempt. No extra buffer-destruction site,
GPU wait, sparse-binding policy or renderer API change is introduced.

Rollback retains main's `destroy_import_buffer` ownership boundary, which releases
associated texel-buffer views before destroying the raw buffer. The fixture
executes that helper and verifies the modeled release hook precedes destruction
for every factory rollback; it does not model the view cache itself.

`tests/test_import_buffer_binding.py` executes the complete real factories and
their composition, plus the real failure-hold wrappers and `ImportHolds` class.
Vulkan, the host allocation calls, POSIX discovery and sparse-route delegation
are modeled. The platform branch is selected explicitly so both routes can run
on Windows and Linux without a driver or game. Thirty-four cases cover success,
creation/allocation/binding failures, resource ownership, invalid address-query
prevention, DMA-to-host fallback, both failures, and hold expiry/retry. Sparse
queue/fence submission itself is outside this change and is not modeled as proof
of native sparse synchronization.

Run `python -I -B tests/run_all.py import_buffer_binding --strict`, or invoke the
test directly with `--headers <Vulkan include folder> --cxx <compiler>`; the
direct runner supports `--sanitize` on Linux. These allocation failures are
authored game-free inputs, not a native OOM or device-loss reproduction. No
performance or campaign-coverage claim follows from them.
