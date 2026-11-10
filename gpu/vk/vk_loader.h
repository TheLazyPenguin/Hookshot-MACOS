// The Vulkan functions the back end calls, loaded from vulkan-1.dll at start (no SDK, no import library): global,
// instance and device level. VK_NO_PROTOTYPES is set for the whole DLL (nx2/build.py).
#pragma once

#ifdef _WIN32
#define VK_USE_PLATFORM_WIN32_KHR
#define VKX_WIN32_SURFACE(X) X(vkCreateWin32SurfaceKHR)
#else
#define VKX_WIN32_SURFACE(X)   /* (linux: SDL makes the surface, host/posix/display_sdl.c) */
#endif
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <vulkan/vulkan.h>

#define VKX_GLOBAL(X)                                                                                                 \
    X(vkCreateInstance)                                                                                               \
    X(vkEnumerateInstanceExtensionProperties)                                                                         \
    X(vkEnumerateInstanceVersion)

#define VKX_INSTANCE(X)                                                                                               \
    X(vkDestroyInstance)                                                                                              \
    X(vkEnumeratePhysicalDevices)                                                                                     \
    X(vkGetPhysicalDeviceProperties)                                                                                  \
    X(vkGetPhysicalDeviceProperties2)                                                                                 \
    X(vkGetPhysicalDeviceFeatures2)                                                                                   \
    X(vkGetPhysicalDeviceQueueFamilyProperties)                                                                       \
    X(vkGetPhysicalDeviceMemoryProperties)                                                                            \
    X(vkGetPhysicalDeviceFormatProperties)                                                                            \
    X(vkGetPhysicalDeviceImageFormatProperties)                                                                            \
    X(vkGetPhysicalDeviceSparseImageFormatProperties)                                                                 \
    X(vkEnumerateDeviceExtensionProperties)                                                                           \
    X(vkCreateDevice)                                                                                                 \
    X(vkGetDeviceProcAddr)                                                                                            \
    VKX_WIN32_SURFACE(X)                                                                                              \
    X(vkDestroySurfaceKHR)                                                                                            \
    X(vkGetPhysicalDeviceSurfaceSupportKHR)                                                                           \
    X(vkGetPhysicalDeviceSurfaceCapabilitiesKHR)                                                                      \
    X(vkGetPhysicalDeviceSurfaceFormatsKHR)                                                                           \
    X(vkGetPhysicalDeviceSurfacePresentModesKHR)                                                                      \
    X(vkGetPhysicalDeviceCooperativeMatrixPropertiesKHR)

#define VKX_DEVICE(X)                                                                                                 \
    X(vkDestroyDevice)                                                                                                \
    X(vkGetDeviceQueue)                                                                                               \
    X(vkDeviceWaitIdle)                                                                                               \
    X(vkQueueSubmit2)                                                                                                 \
    X(vkQueueWaitIdle)                                                                                                \
    X(vkQueueBindSparse)                                                                                              \
    X(vkCreateSwapchainKHR)                                                                                           \
    X(vkDestroySwapchainKHR)                                                                                          \
    X(vkGetSwapchainImagesKHR)                                                                                        \
    X(vkAcquireNextImageKHR)                                                                                          \
    X(vkQueuePresentKHR)                                                                                              \
    X(vkCreateCommandPool)                                                                                            \
    X(vkDestroyCommandPool)                                                                                           \
    X(vkResetCommandPool)                                                                                             \
    X(vkAllocateCommandBuffers)                                                                                       \
    X(vkBeginCommandBuffer)                                                                                           \
    X(vkEndCommandBuffer)                                                                                             \
    X(vkCreateFence)                                                                                                  \
    X(vkDestroyFence)                                                                                                 \
    X(vkWaitForFences)                                                                                                \
    X(vkResetFences)                                                                                                  \
    X(vkCreateSemaphore)                                                                                              \
    X(vkDestroySemaphore)                                                                                             \
    X(vkWaitSemaphores)                                                                                               \
    X(vkGetSemaphoreCounterValue)                                                                                     \
    X(vkCreateImageView)                                                                                              \
    X(vkDestroyImageView)                                                                                             \
    X(vkCmdPipelineBarrier2)                                                                                          \
    X(vkCmdClearColorImage)                                                                                           \
    X(vkCmdClearDepthStencilImage)                                                                                    \
    X(vkCmdUpdateBuffer)                                                                                              \
    X(vkCmdCopyBuffer)                                                                                                \
    X(vkCmdBlitImage)                                                                                                 \
    X(vkCmdCopyBufferToImage)                                                                                         \
    X(vkCreateBuffer)                                                                                                 \
    X(vkDestroyBuffer)                                                                                                \
    X(vkCreateImage)                                                                                                  \
    X(vkDestroyImage)                                                                                                 \
    X(vkAllocateMemory)                                                                                               \
    X(vkFreeMemory)                                                                                                   \
    X(vkMapMemory)                                                                                                    \
    X(vkBindBufferMemory)                                                                                             \
    X(vkBindImageMemory)                                                                                              \
    X(vkGetBufferMemoryRequirements)                                                                                  \
    X(vkGetImageMemoryRequirements)                                                                                   \
    X(vkGetImageSparseMemoryRequirements)                                                                             \
    X(vkGetMemoryHostPointerPropertiesEXT)                                                                            \
    X(vkGetMemoryFdPropertiesKHR)                                                                                     \
    X(vkGetBufferDeviceAddress)

// shaders, pipelines, descriptors, draws
#define VKX_DEVICE2(X)                                                                                                \
    X(vkCreateShaderModule)                                                                                           \
    X(vkDestroyShaderModule)                                                                                          \
    X(vkCreateDescriptorSetLayout)                                                                                    \
    X(vkCreatePipelineLayout)                                                                                         \
    X(vkCreateGraphicsPipelines)                                                                                      \
    X(vkCreateComputePipelines)                                                                                       \
    X(vkDestroyPipeline)                                                                                              \
    X(vkCreateDescriptorPool)                                                                                         \
    X(vkResetDescriptorPool)                                                                                          \
    X(vkAllocateDescriptorSets)                                                                                       \
    X(vkUpdateDescriptorSets)                                                                                         \
    X(vkCreateSampler)                                                                                                \
    X(vkCmdBeginRendering)                                                                                            \
    X(vkCmdEndRendering)                                                                                              \
    X(vkCmdBindPipeline)                                                                                              \
    X(vkCmdBindDescriptorSets)                                                                                        \
    X(vkCmdBindVertexBuffers)                                                                                         \
    X(vkCmdBindIndexBuffer)                                                                                           \
    X(vkCmdDraw)                                                                                                      \
    X(vkCmdDrawIndexed)                                                                                               \
    X(vkCmdDrawIndirect)                                                                                              \
    X(vkCmdDrawIndexedIndirect)                                                                                       \
    X(vkCmdDrawIndirectCount)                                                                                         \
    X(vkCmdDrawIndexedIndirectCount)                                                                                  \
    X(vkCmdDispatch)                                                                                                  \
    X(vkCmdDispatchIndirect)                                                                                          \
    X(vkCmdSetViewport)                                                                                               \
    X(vkCmdSetScissor)                                                                                                \
    X(vkCmdSetBlendConstants)                                                                                         \
    X(vkCmdSetStencilReference)                                                                                       \
    X(vkCmdSetStencilCompareMask)                                                                                     \
    X(vkCmdSetStencilWriteMask)                                                                                       \
    X(vkCmdSetDepthBias)                                                                                              \
    X(vkCmdPushConstants)                                                                                             \
    X(vkCmdCopyImage)                                                                                                 \
    X(vkCmdCopyImageToBuffer)                                                                                         \
    X(vkCmdSetPrimitiveTopology)                                                                                      \
    X(vkCmdSetCullMode)                                                                                               \
    X(vkCmdSetFrontFace)                                                                                              \
    X(vkCmdSetDepthTestEnable)                                                                                        \
    X(vkCmdSetDepthWriteEnable)                                                                                       \
    X(vkCmdSetDepthCompareOp)                                                                                         \
    X(vkCmdSetStencilTestEnable)                                                                                      \
    X(vkCmdSetStencilOp)                                                                                              \
    X(vkCmdSetDepthBiasEnable)                                                                                        \
    X(vkCmdSetPrimitiveRestartEnable)                                                                                 \
    X(vkCmdSetRasterizerDiscardEnable)                                                                                \
    X(vkCmdDrawMeshTasksEXT)                                                                                          \
    X(vkCmdDrawMeshTasksIndirectEXT)

// textures, pipelines and the rest of the replay (extension functions are null when the device lacks them)
#define VKX_DEVICE3(X) \
    X(vkCmdDrawMeshTasksIndirectCountEXT) X(vkCmdPushDescriptorSetKHR) X(vkCreateBufferView) X(vkDestroyBufferView) \
    X(vkDestroySampler) X(vkDestroyDescriptorSetLayout) X(vkDestroyPipelineLayout) X(vkDestroyDescriptorPool) \
    X(vkCreatePipelineCache) X(vkDestroyPipelineCache) X(vkGetPipelineCacheData) X(vkMergePipelineCaches) X(vkCmdFillBuffer) \
    X(vkCmdResolveImage) X(vkCmdBeginConditionalRenderingEXT) X(vkCmdEndConditionalRenderingEXT) \
    X(vkCmdSetLineWidth) X(vkCmdSetDepthClampEnableEXT) X(vkCmdSetPolygonModeEXT) X(vkCmdSetColorWriteMaskEXT) \
    X(vkCmdSetColorBlendEnableEXT) X(vkCmdSetColorBlendEquationEXT) X(vkCmdSetLogicOpEnableEXT) \
    X(vkCmdSetAlphaToCoverageEnableEXT) X(vkCmdSetViewportWithCount) X(vkCmdSetScissorWithCount) \
    X(vkCmdBindVertexBuffers2) X(vkCmdWriteTimestamp2) X(vkCreateQueryPool) X(vkDestroyQueryPool) \
    X(vkCmdResetQueryPool) X(vkCmdBeginQuery) X(vkCmdEndQuery) X(vkCmdCopyQueryPoolResults) X(vkGetQueryPoolResults) \
    X(vkResetQueryPool) \
    X(vkCmdSetDepthClipEnableEXT) X(vkCmdSetLogicOpEXT) X(vkCmdClearAttachments) X(vkCmdSetDepthBoundsTestEnable) \
    X(vkCmdSetCheckpointNV) X(vkGetQueueCheckpointDataNV) X(vkGetDeviceFaultInfoEXT) X(vkCmdWriteBufferMarkerAMD)

namespace vkx {
#define VKX_DECLARE(f) extern PFN_##f f;
VKX_GLOBAL(VKX_DECLARE)
VKX_INSTANCE(VKX_DECLARE)
VKX_DEVICE(VKX_DECLARE)
VKX_DEVICE2(VKX_DECLARE)
#undef VKX_DECLARE
#define VKX_DECLARE3(f) extern PFN_##f f;
VKX_DEVICE3(VKX_DECLARE3)
#undef VKX_DECLARE3

/// vulkan-1.dll and the global functions; false when Vulkan is not installed
bool load_global();
void load_instance(VkInstance instance);
PFN_vkGetInstanceProcAddr instance_proc_addr();
void load_device(VkDevice device);
} // namespace vkx

using namespace vkx;
