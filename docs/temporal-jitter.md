# Temporal jitter sample

The host asks the renderer for one `MkwVkJitter` per host frame. Width, height and
sequence length belong to the same completed upscale; inactive samples contain
three zeros. The renderer callback was appended in host/backend API 14, so both
binaries must be rebuilt together. A renderer without the callback supplies no jitter.

The shared DLSS/FSR 4 chain and the separate FSR 3.1 path publish their metadata through a short, separate mutex. The host
does not acquire the upscaler's GPU/NGX resource lock or query window APIs. A
sample expires after 30 renderer frames, as before; disabled or failed DLSS/FSR 4 and
disabled FSR return an inactive sample. The replay callback selects a complete
eligible provider sample, and the host caches it for all views of its frame.
The host's frame cache has its own short lock: simultaneous view callers cannot
consume a cache whose renderer query is still running. Each caller copies the
complete sample before releasing that lock and doing projection math. The frame
counter is read under that same lock: a delayed caller cannot roll the cache
back after a newer frame has already latched its sample.

The scalar jitter option IDs remain reserved and available for individual
queries. Three independent scalar queries are not a coherent snapshot: a resize
or scale change can occur between them. The host uses the batch callback instead.

`tests/test_temporal_jitter.py` executes the actual producers, readers, replay
callback and host consumer with deterministic publication between queries,
provider/freshness/fallback checks and concurrent publication stress. It needs no
game, Vulkan device or NVIDIA SDK; it does not establish image quality or GPU timing.
