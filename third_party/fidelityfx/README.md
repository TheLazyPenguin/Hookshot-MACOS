# AMD FSR API headers (FidelityFX SDK v2.4.0)

Unmodified MIT-licensed headers from AMD's FidelityFX SDK, tag `v2.4.0`
(<https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK>, `Kits/FidelityFX/api/include` and
`Kits/FidelityFX/upscalers/include`). See `LICENSE.md`.

Only the headers are compiled in (`gpu/vk/vk_fsr4.cpp`, in a build with `HOOKSHOT_FSR=1`). AMD's signed
`amd_fidelityfx_loader_vk.dll` and `amd_fidelityfx_upscaler_vk.dll` (from `Kits/FidelityFX/signedbin` of the same release)
are not vendored: they are loaded at run time, from `RX_VK_FSR_DIR` or the folder of `hookshot.exe`, when the Upscaler row
is on AMD FSR 4.
