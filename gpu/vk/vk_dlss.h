// NVIDIA DLSS Super Resolution, one of the temporal upscaler's engines (vk_temporal.h; vk_dlss.cpp). Built in only with
// NVIDIA's NGX SDK (HOOKSHOT_NGX, scripts/ngx_sdk.py: Linux and Windows); without it these say DLSS is not there and the
// game's network runs.
#pragma once

#include <vector>

#include "vk_internal.h"

namespace mkwvk {

struct TemporalEngine;

/// Whether this build has DLSS in it (HOOKSHOT_NGX)
bool dlss_built();
/// Why DLSS cannot be chosen here (the Insert menu's Upscaler row says it), DLSS_OK when it can or is not known yet
enum DlssWhy { DLSS_OK, DLSS_NOT_BUILT, DLSS_ENV_OFF, DLSS_NEEDS_RTX, DLSS_NEEDS_DRIVER, DLSS_NO_RUNTIME,
               DLSS_RUNTIME_NOT_ASCII, DLSS_WHY_COUNT };
DlssWhy dlss_why();
/// Asks NGX once whether DLSS runs on this device, so dlss_why knows before the first upscale (the menu, when it opens).
/// Nothing off an NVIDIA device with NGX's extensions, or in a build without DLSS
void dlss_probe();
/// The instance's extensions DLSS needs, added to `want` when the loader has them (all: what it has)
void dlss_instance_extensions(std::vector<const char*>& want, const std::vector<VkExtensionProperties>& all);
/// The device's extensions DLSS needs, added to `want` when the device has them
void dlss_device_extensions(std::vector<const char*>& want, const std::vector<VkExtensionProperties>& all);
/// DLSS as the temporal upscaler's engine (DLSS and DLAA on the Upscaler row); nullptr in a build without it
const TemporalEngine* dlss_engine();

} // namespace mkwvk
