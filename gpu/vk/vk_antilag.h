// AMD Anti-Lag 2 through VK_AMD_anti_lag (vk_antilag.cpp): the driver delays the start of the game's next frame so that its
// input is sampled later and the frame waits less in the queue, for less delay from input to the screen.
#pragma once

#include <vector>

#include "vk_internal.h"

namespace mkwvk {

/// The extension it needs (VK_AMD_anti_lag), added to `want` when the device has it
void antilag_device_extensions(std::vector<const char*>& want, const std::vector<VkExtensionProperties>& all);
/// Its feature (antiLag) into the device's feature chain (*tail), before the features are queried
void antilag_device_features(void**& tail);
/// After the device is made: whether Anti-Lag 2 can run (the feature there), its function loaded
void antilag_device_created();
/// Anti-Lag 2 can run on this device: the Insert menu's row offers it only then
bool antilag_available();
/// Before the present: the frame's present stage
void antilag_present();
/// After the present: the next frame's input stage, where the driver waits until that frame should start
void antilag_input();

} // namespace mkwvk
