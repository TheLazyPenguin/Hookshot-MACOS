# Presentation source crops

Direct presentation, capture, scaling and interpolation must sample the same valid
source region. `present_source_rect` is the common contract, independent of Vulkan:

- A null crop, or either nonpositive crop extent, selects the entire image, preserving
  the existing convention even when the unused origin fields are negative.
- An active crop with a negative or out-of-image origin is empty.
- Positive extents are clipped to the remaining source area by subtraction before
  addition. `x + width` in guest input must not overflow a signed integer.
- Empty sources and dimensions beyond signed 32-bit image offsets are rejected.

The content-aspect calculation uses the same clipped region. Direct/capture blits
clear their destination to opaque black for an empty source region instead of issuing
an invalid Vulkan blit or copying undefined pixels. Zero destination extent records
nothing. Scaling/interpolation decline an invalid crop before setup or allocation;
ordinary presentation supplies the black fallback. Valid crops retain their offsets,
filter and destination rectangle.

`tests/test_present_source_crop.py` executes the production blit, capture wrapper and
complete interpolation recorder with CPU API spies. It checks the command offsets,
interpolation copy push constants, clipped allocation size, invalid-input clear/skip,
full-image convention and thousands of deterministic edge-crossing crops. It needs
Vulkan headers and a C++20 compiler, but no GPU or game data. The independent scaler
fixture separately executes the production scaling function.
