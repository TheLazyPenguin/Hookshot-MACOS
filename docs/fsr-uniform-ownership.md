# Native FSR constants belong to a recording

Native FSR upscaling and interpolation used a mapped four-frame uniform ring.
Its next evaluation could overwrite constants while an earlier queued dispatch
still read them. Four CPU evaluations are not a GPU completion guarantee.

Each evaluation now reserves an aligned slice of its recording's existing upload
stream. Recording slots wait on their own fence, or flush/wait their held batch,
before their stream is reset. Additional evaluations in the same recording use
additional slices; stream growth retains earlier allocations. This follows the
same physical recording lifetime for serial, split and worker recordings without
adding a per-frame wait or expanding an arbitrary fixed ring.

Reservation precedes temporal state changes and GPU commands. An unavailable
recording, missing mapping or exhausted stream rejects the evaluation before it
consumes history, initial-layout or LUT state. Existing renderer fallback can run.
Both native backends flush their own completed mapped slice before using it,
including on noncoherent memory. Shader constant layouts and FSR passes remain
the same; the upscaler's Lanczos upload uses the slice's buffer and offset too.
This is an internal C++ upload interface, with no host/renderer ABI change.

The game-free fixture executes the production stream allocator/reset, recording wait/begin, reservation,
constant layouts/uploads, all constant buffer bindings and the consumer admission
prefix. Authored constant payloads are read later, independently of CPU writes,
across nine evaluations, growth, distinct worker slots and completed slot reuse.
Allocation failure, retry, alignment and coherent/noncoherent cases are included.
The admission-prefix test stubs image preparation; it does not execute the entire
FSR shader chain or parallel scheduler. Native smoke is still required, alongside
causal controls and the complete source suite. These checks do not claim a native
GPU fault reproduction, campaign coverage or a performance improvement.
