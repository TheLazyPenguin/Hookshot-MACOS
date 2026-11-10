"""Create BC/raw views using the actual image flags and make_view; Windows Vulkan device required.

python nx2/test_bc_storage_views.py --headers <Vulkan-Headers/include> [--cxx clang++]
Enable the Khronos validation layer through VK_LAYER_PATH/VK_INSTANCE_LAYERS.
No game data, shader, or image contents are used; this checks creation, not storage-write fidelity.
"""
import argparse
from pathlib import Path
import subprocess,tempfile

RUN_ALL_ARGS = ["--headers", "{vulkan_headers}"]
# (a GPU)
RUN_ALL_SKIP = {"linux": "needs a Windows Vulkan device", "windows": "needs a Windows Vulkan device"}

ROOT=Path(__file__).resolve().parents[1]
def block(text,marker):
    start=text.index(marker);end=text.index('{',start)+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--headers',type=Path,required=True);p.add_argument('--cxx',default='clang++');a=p.parse_args()
    text=(ROOT/'gpu/vk/vk_texture.cpp').read_text(encoding='utf-8')
    start=text.index('    const VkFormatProperties fp = format_props(x.format);')
    end=text.index('    if (x.type == VK_IMAGE_TYPE_2D',start)
    flags=text[start:end]
    fixture=r'''#define WIN32_LEAN_AND_MEAN
#define VK_NO_PROTOTYPES
#include <windows.h>
#include <vulkan/vulkan.h>
#include <cstdio>
#include <cstdlib>
#include <vector>
#define CHECK(x) do{if(!(x)){std::fprintf(stderr,"FAIL:%d %s\n",__LINE__,#x);std::exit(1);}}while(0)
#define API_LIST(X) X(vkCreateInstance) X(vkDestroyInstance) X(vkEnumeratePhysicalDevices) X(vkGetPhysicalDeviceProperties) X(vkGetPhysicalDeviceFeatures) X(vkGetPhysicalDeviceQueueFamilyProperties) X(vkGetPhysicalDeviceMemoryProperties) X(vkGetPhysicalDeviceFormatProperties) X(vkGetPhysicalDeviceImageFormatProperties) X(vkCreateDevice) X(vkDestroyDevice) X(vkCreateImage) X(vkDestroyImage) X(vkGetImageMemoryRequirements) X(vkAllocateMemory) X(vkFreeMemory) X(vkBindImageMemory) X(vkCreateImageView) X(vkDestroyImageView)
#define DECLARE(n) PFN_##n n;
API_LIST(DECLARE)
struct {VkDevice device;VkPhysicalDevice physical;} dev{};
struct Texture {VkImage image;VkFormat format;VkImageUsageFlags usage;VkSampleCountFlagBits samples;VkImageType type;} ;
VkFormatProperties format_props(VkFormat f){VkFormatProperties p{};vkGetPhysicalDeviceFormatProperties(dev.physical,f,&p);return p;}
''' + block(text,'bool is_bc(VkFormat f) {')+'\n'+block(text,'bool is_astc(VkFormat f) {')+'\n'+block(text,'VkImageView make_view(')+r'''
int main() {
    HMODULE loader=LoadLibraryA("vulkan-1.dll");CHECK(loader);
#define LOAD(n) n=(PFN_##n)GetProcAddress(loader,#n);CHECK(n);
    API_LIST(LOAD)
    VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};app.apiVersion=VK_API_VERSION_1_3;
    VkInstanceCreateInfo ici{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};ici.pApplicationInfo=&app;
    VkInstance instance{};CHECK(vkCreateInstance(&ici,nullptr,&instance)==VK_SUCCESS);
    uint32_t count=0;CHECK(vkEnumeratePhysicalDevices(instance,&count,nullptr)==VK_SUCCESS && count);
    std::vector<VkPhysicalDevice> devices(count);CHECK(vkEnumeratePhysicalDevices(instance,&count,devices.data())==VK_SUCCESS);
    dev.physical=devices[0];
    for(auto d:devices){VkPhysicalDeviceProperties p{};vkGetPhysicalDeviceProperties(d,&p);if(p.vendorID==0x1002)dev.physical=d;}
    VkPhysicalDeviceProperties props{};vkGetPhysicalDeviceProperties(dev.physical,&props);std::printf("device: %s\n",props.deviceName);
    vkGetPhysicalDeviceQueueFamilyProperties(dev.physical,&count,nullptr);std::vector<VkQueueFamilyProperties> queues(count);
    vkGetPhysicalDeviceQueueFamilyProperties(dev.physical,&count,queues.data());uint32_t family=0;
    while(family<count && !(queues[family].queueFlags & VK_QUEUE_GRAPHICS_BIT))family++;CHECK(family<count);
    float priority=1;VkDeviceQueueCreateInfo qi{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};qi.queueFamilyIndex=family;qi.queueCount=1;qi.pQueuePriorities=&priority;
    VkPhysicalDeviceFeatures features{};vkGetPhysicalDeviceFeatures(dev.physical,&features);CHECK(features.textureCompressionBC);
    VkDeviceCreateInfo di{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};di.queueCreateInfoCount=1;di.pQueueCreateInfos=&qi;di.pEnabledFeatures=&features;
    CHECK(vkCreateDevice(dev.physical,&di,nullptr,&dev.device)==VK_SUCCESS);
    VkPhysicalDeviceMemoryProperties memory{};vkGetPhysicalDeviceMemoryProperties(dev.physical,&memory);
    struct Case{VkFormat compressed,raw;int bytes;} cases[]={{VK_FORMAT_BC1_RGBA_UNORM_BLOCK,VK_FORMAT_R32G32_UINT,8},
        {VK_FORMAT_BC3_UNORM_BLOCK,VK_FORMAT_R32G32B32A32_UINT,16},{VK_FORMAT_BC4_UNORM_BLOCK,VK_FORMAT_R16G16B16A16_UINT,8},
        {VK_FORMAT_BC5_UNORM_BLOCK,VK_FORMAT_R32G32B32A32_UINT,16},{VK_FORMAT_BC7_UNORM_BLOCK,VK_FORMAT_R32G32B32A32_UINT,16}};
    int storage_views=0;
    for(auto c:cases){
        Texture x{};x.format=c.compressed;x.type=VK_IMAGE_TYPE_2D;x.samples=VK_SAMPLE_COUNT_1_BIT;bool depth=false;int bpb=c.bytes;
''' +flags+r'''
        const bool storage=(x.usage & VK_IMAGE_USAGE_STORAGE_BIT)!=0;
        VkImageCreateInfo ci{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};ci.flags=flags;ci.imageType=VK_IMAGE_TYPE_2D;ci.format=x.format;
        ci.extent={32,16,1};ci.mipLevels=3;ci.arrayLayers=2;ci.samples=x.samples;ci.tiling=VK_IMAGE_TILING_OPTIMAL;ci.usage=x.usage;
        CHECK(vkCreateImage(dev.device,&ci,nullptr,&x.image)==VK_SUCCESS);
        VkMemoryRequirements req{};vkGetImageMemoryRequirements(dev.device,x.image,&req);uint32_t mt=0;
        while(mt<memory.memoryTypeCount && !(req.memoryTypeBits & (1u<<mt)))mt++;CHECK(mt<memory.memoryTypeCount);
        VkMemoryAllocateInfo ai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};ai.allocationSize=req.size;ai.memoryTypeIndex=mt;
        VkDeviceMemory mem{};CHECK(vkAllocateMemory(dev.device,&ai,nullptr,&mem)==VK_SUCCESS);CHECK(vkBindImageMemory(dev.device,x.image,mem,0)==VK_SUCCESS);
        VkComponentMapping cm{};
        auto sampled=make_view(&x,VK_IMAGE_VIEW_TYPE_2D_ARRAY,c.compressed,VK_IMAGE_ASPECT_COLOR_BIT,0,3,0,2,cm,VK_IMAGE_USAGE_SAMPLED_BIT);CHECK(sampled);
        auto raw=make_view(&x,VK_IMAGE_VIEW_TYPE_2D,c.raw,VK_IMAGE_ASPECT_COLOR_BIT,1,1,1,1,cm,VK_IMAGE_USAGE_STORAGE_BIT);CHECK(bool(raw)==storage);storage_views+=bool(raw);
        CHECK(!make_view(&x,VK_IMAGE_VIEW_TYPE_2D,c.raw,VK_IMAGE_ASPECT_COLOR_BIT,0,2,0,1,cm,VK_IMAGE_USAGE_STORAGE_BIT));
        CHECK(!make_view(&x,VK_IMAGE_VIEW_TYPE_2D_ARRAY,c.raw,VK_IMAGE_ASPECT_COLOR_BIT,0,1,0,2,cm,VK_IMAGE_USAGE_STORAGE_BIT));
        CHECK(!make_view(&x,VK_IMAGE_VIEW_TYPE_2D,c.raw,VK_IMAGE_ASPECT_COLOR_BIT,0,1,0,1,cm,0));
        CHECK(!make_view(&x,VK_IMAGE_VIEW_TYPE_2D,c.raw,VK_IMAGE_ASPECT_COLOR_BIT,0,1,0,1,cm,VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT));
        if(raw)vkDestroyImageView(dev.device,raw,nullptr);vkDestroyImageView(dev.device,sampled,nullptr);vkDestroyImage(dev.device,x.image,nullptr);vkFreeMemory(dev.device,mem,nullptr);
    }
    vkDestroyDevice(dev.device,nullptr);vkDestroyInstance(instance,nullptr);FreeLibrary(loader);
    CHECK(storage_views>0);std::printf("PASS: five BC formats, %d raw storage views, sampled arrays/mips, rejected empty/unsupported usages\n",storage_views);
}
'''
    work=ROOT/'work';work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bc-views-',dir=work) as temp:
        directory=Path(temp).resolve();directory.relative_to(work.resolve());cpp=directory/'fixture.cpp';exe=directory/'fixture.exe';cpp.write_text(fixture,encoding='utf-8')
        subprocess.run([a.cxx,'-std=c++20','-O2','-I'+str(a.headers),str(cpp),'-o',str(exe)],check=True)
        r=subprocess.run([str(exe)],capture_output=True,text=True);print(r.stdout+r.stderr,end='');r.check_returncode()
        assert 'Validation Error' not in r.stderr+r.stdout
if __name__=='__main__':main()
