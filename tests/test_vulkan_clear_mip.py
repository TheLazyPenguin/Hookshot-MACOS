"""Execute production region resolution and partial clears with instrumented Vulkan commands."""
import argparse
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}", "--headers", "{vulkan_headers}"]

ROOT = Path(__file__).resolve().parents[1]


def block(source, marker):
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="clang++")
    parser.add_argument("--headers", required=True, type=Path)
    parser.add_argument("--source", type=Path, default=ROOT / "gpu/vk/vk_xfer.cpp")
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    source = args.source.read_text(encoding="utf-8")
    texture = (ROOT / "gpu/vk/vk_texture.cpp").read_text(encoding="utf-8")
    fixture = r'''
#define VK_NO_PROTOTYPES
#include <vulkan/vulkan_core.h>
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr,"FAIL:%d %s\n",__LINE__,#x); std::exit(1); } } while (0)
struct Texture {
    VkImage image=(VkImage)1; VkImageType type=VK_IMAGE_TYPE_2D; VkFormat format=VK_FORMAT_R8G8B8A8_UNORM;
    VkImageAspectFlags aspect=VK_IMAGE_ASPECT_COLOR_BIT;
    uint64_t gpu=0x1000;
    uint32_t width=64,height=32,depth=1,layers=4,levels=4,skip=0;
    int nvn_format=1; bool bc=false,astc=false,sparse=false,gpu_written=false,released=false,only_cleared=false;
} tex;
struct nvn_tex { uint64_t gpu=0x1000; };
struct nvn_view { bool set_levels=false,set_layers=false; uint8_t base_level=0,nlevels=0; uint16_t min_layer=0,nlayers=0; };
struct NVNcopyRegion { int32_t xoffset=0,yoffset=0,zoffset=0,width=0,height=0,depth=1; };
struct NvnState {};
union Color { float f[4]; uint32_t u[4]; };
struct nvn_p_clear_tex { const nvn_tex* tex; nvn_view view{}; bool has_view=true; NVNcopyRegion r{}; uint32_t mask=15; Color c{}; };
enum class ViewUse { Attachment };
unsigned selected_mip, expected_mip, first_layer, clear_count, whole_count, touched[4][4];
void warn(int, const char*) {}
template<typename... T> void logf(const char*,T...) {}
Texture* texture_get(const nvn_tex*,bool) { return &tex; }
int view_nvn_format(const nvn_tex*,const nvn_view*) { return 1; }
int nvn_block_size(int,int* w,int* h) { *w=*h=1; return 4; }
void texture_resident(Texture*,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t) {}
void end_pass(VkCommandBuffer) {}
void full_barrier(VkCommandBuffer) {}
struct GprofSpan { GprofSpan(VkCommandBuffer,const char*) {} };
void texture_written(Texture* t) { t->gpu_written=true; }
''' + "\n".join(block(texture, m) for m in ("unsigned view_level(", "unsigned image_level(", "unsigned view_layer(")) + r'''
VkImageView texture_view(Texture* t,const nvn_tex*,const nvn_view* view,VkImageViewType,ViewUse) {
    selected_mip=image_level(t,view_level(view)); first_layer=view_layer(view);
    CHECK(view->nlevels==1 && view->nlayers==1);
    return (VkImageView)1;
}
void vkCmdBeginRendering(VkCommandBuffer,const VkRenderingInfo* info) {
    if (selected_mip != expected_mip) std::fprintf(stderr,"selected mip %u instead of %u\n",selected_mip,expected_mip);
    CHECK(selected_mip==expected_mip);
    CHECK(info->renderArea.extent.width==std::max(1u,tex.width>>selected_mip));
    CHECK(info->renderArea.extent.height==std::max(1u,tex.height>>selected_mip));
}
void vkCmdClearAttachments(VkCommandBuffer,uint32_t,const VkClearAttachment*,uint32_t,const VkClearRect*) {
    ++clear_count; ++touched[selected_mip][first_layer];
}
void vkCmdEndRendering(VkCommandBuffer) {}
void vkCmdClearColorImage(VkCommandBuffer,VkImage,VkImageLayout,const VkClearColorValue*,uint32_t,const VkImageSubresourceRange* r) {
    CHECK(r->baseMipLevel==expected_mip); ++whole_count;
}
void vkCmdClearDepthStencilImage(VkCommandBuffer,VkImage,VkImageLayout,const VkClearDepthStencilValue*,uint32_t,const VkImageSubresourceRange*) { CHECK(false); }
''' + block(source, "struct Sub {") + ";\n" + block(source, "bool resolve(") + "\n" + block(source, "void clear_tex(") + r'''
void run(uint32_t skip,uint32_t logical,uint32_t layer,bool whole) {
    tex=Texture{}; tex.skip=skip; std::memset(touched,0,sizeof touched); clear_count=whole_count=0;
    expected_mip=logical-skip;
    nvn_tex input; nvn_p_clear_tex p{&input}; p.view.set_levels=true; p.view.base_level=(uint8_t)logical; p.view.nlevels=1;
    p.view.set_layers=true; p.view.min_layer=(uint16_t)layer; p.view.nlayers=2;
    p.r.xoffset=whole ? 0 : 1; p.r.yoffset=whole ? 0 : 1;
    p.r.width=whole ? (int32_t)(tex.width>>expected_mip) : 2;
    p.r.height=whole ? (int32_t)(tex.height>>expected_mip) : 2; p.r.depth=2;
    NvnState state; clear_tex(VK_NULL_HANDLE,state,p);
    CHECK(tex.gpu_written);
    CHECK(whole ? whole_count==1 && clear_count==0 : whole_count==0 && clear_count==2);
    if (!whole) for (unsigned mip=0;mip<4;++mip) for(unsigned l=0;l<4;++l)
        CHECK(touched[mip][l]==unsigned(mip==expected_mip && l>=layer && l<layer+2));
}
int main() {
    run(1,2,1,false); run(2,3,1,false); run(1,1,0,false);
    run(0,2,1,false); run(0,0,0,false); run(1,2,1,true);
    std::puts("PASS: 6 partial/whole clear scenarios, mip mapping and independent array layers");
}
'''
    with tempfile.TemporaryDirectory(prefix="hookshot-clear-mip-") as directory:
        cpp, exe = Path(directory) / "test.cpp", Path(directory) / "test.exe"
        cpp.write_text(fixture, encoding="utf-8")
        flags = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all"] if args.sanitize else []
        subprocess.run([args.cxx,"-std=c++20","-O1","-Wall","-Werror",
                        "-Wno-missing-field-initializers",*flags,
                        "-I"+str(args.headers),str(cpp),"-o",str(exe)],check=True)
        subprocess.run([str(exe)],check=True,timeout=10)


if __name__ == "__main__":
    main()
