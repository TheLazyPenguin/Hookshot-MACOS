"""Execute create()'s image initialization with Vulkan command spies; no GPU/loader.
Covers Segmentree's initialization dependency fix in PR #228.
Run in a compiler environment: python -I -B nx2/test_texture_init_barrier.py --cxx clang++ --headers path/to/include
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--headers", "{vulkan_headers}"]

ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cxx', default='clang++')
    p.add_argument('--headers', required=True, type=Path)
    p.add_argument('--source', type=Path, default=ROOT / 'gpu/vk/vk_texture.cpp')
    a = p.parse_args()
    text = a.source.read_text(encoding='utf-8')
    start = text.index('    // into GENERAL, and cleared', text.index('Texture* create('))
    fragment = text[start:text.index('    Texture* p = tex.get();', start)]
    fixture = r'''
#define VK_NO_PROTOTYPES
#include <vulkan/vulkan_core.h>
#include <cstdio>
#include <cstdlib>
#define CHECK(v) do {if (!(v)) {std::fprintf(stderr,"FAIL:%d %s\n",__LINE__,#v);std::exit(1);}} while(0)
int commands, clears, dependencies;
VkImage image = reinterpret_cast<VkImage>(1);
VkCommandBuffer upload_cmd() {return reinterpret_cast<VkCommandBuffer>(1);}
bool is_bc(VkFormat f) {return f == VK_FORMAT_BC3_UNORM_BLOCK;}
bool is_astc(VkFormat f) {return f == VK_FORMAT_ASTC_4x4_UNORM_BLOCK;}
void vkCmdPipelineBarrier2(VkCommandBuffer, const VkDependencyInfo* di) {
    CHECK(di->imageMemoryBarrierCount == 1);
    const auto& b = *di->pImageMemoryBarriers;
    CHECK(b.image == image && b.newLayout == VK_IMAGE_LAYOUT_GENERAL);
    CHECK(b.subresourceRange.baseMipLevel == 0 && b.subresourceRange.levelCount == VK_REMAINING_MIP_LEVELS);
    CHECK(b.subresourceRange.baseArrayLayer == 0 && b.subresourceRange.layerCount == VK_REMAINING_ARRAY_LAYERS);
    CHECK(b.srcQueueFamilyIndex == VK_QUEUE_FAMILY_IGNORED && b.dstQueueFamilyIndex == VK_QUEUE_FAMILY_IGNORED);
    if (b.oldLayout == VK_IMAGE_LAYOUT_UNDEFINED) {CHECK(commands == 0);}
    else {
        CHECK(commands == 2 && clears == 1 && b.oldLayout == VK_IMAGE_LAYOUT_GENERAL);
        CHECK(b.srcStageMask & VK_PIPELINE_STAGE_2_ALL_TRANSFER_BIT);
        CHECK(b.srcAccessMask & VK_ACCESS_2_TRANSFER_WRITE_BIT);
        CHECK(b.dstStageMask & VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT);
        CHECK((b.dstAccessMask & (VK_ACCESS_2_MEMORY_READ_BIT | VK_ACCESS_2_MEMORY_WRITE_BIT)) ==
              (VK_ACCESS_2_MEMORY_READ_BIT | VK_ACCESS_2_MEMORY_WRITE_BIT));
        dependencies++;
    }
    commands++;
}
void clear(VkImage i, VkImageLayout layout, uint32_t n, const VkImageSubresourceRange* range) {
    CHECK(commands == 1 && i == image && layout == VK_IMAGE_LAYOUT_GENERAL && n == 1);
    CHECK(range->levelCount == VK_REMAINING_MIP_LEVELS && range->layerCount == VK_REMAINING_ARRAY_LAYERS);
    clears++;commands++;
}
void vkCmdClearDepthStencilImage(VkCommandBuffer, VkImage i, VkImageLayout l, const VkClearDepthStencilValue*, uint32_t n, const VkImageSubresourceRange* r) {clear(i,l,n,r);}
void vkCmdClearColorImage(VkCommandBuffer, VkImage i, VkImageLayout l, const VkClearColorValue*, uint32_t n, const VkImageSubresourceRange* r) {clear(i,l,n,r);}
void run(VkFormat format, bool depth) {
    commands = clears = dependencies = 0;
    struct {VkImage image;VkFormat format;VkImageAspectFlags aspect;} x{image,format,VkImageAspectFlags(depth ? VK_IMAGE_ASPECT_DEPTH_BIT : VK_IMAGE_ASPECT_COLOR_BIT)};
''' + fragment + r'''
    const bool compressed = is_bc(format) || is_astc(format);
    CHECK(clears == !compressed && dependencies == !compressed);
    CHECK(commands == (compressed ? 1 : 3));
}
int main() {
    run(VK_FORMAT_R8_UNORM,false);run(VK_FORMAT_R8G8B8A8_UNORM,false);
    run(VK_FORMAT_D32_SFLOAT,true);run(VK_FORMAT_BC3_UNORM_BLOCK,false);run(VK_FORMAT_ASTC_4x4_UNORM_BLOCK,false);
    puts("PASS: actual create initialization orders colour/depth clears before dependent commands; BC/ASTC excluded");
}
'''
    with tempfile.TemporaryDirectory(prefix='hookshot-init-spy-') as temp:
        cpp = Path(temp) / 'spy.cpp'
        exe = Path(temp) / 'spy.exe'
        cpp.write_text(fixture, encoding='utf-8')
        subprocess.run([a.cxx, '-std=c++20', '-I' + str(a.headers), str(cpp), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)

if __name__ == '__main__':
    main()
