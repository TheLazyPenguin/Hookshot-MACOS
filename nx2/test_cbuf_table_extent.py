"""Check actual uniform binding ranges include generated global-buffer table reads.
python nx2/test_cbuf_table_extent.py [--cxx clang++]
No GPU or game files are needed.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "g++"]

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cxx',default='clang++');a=p.parse_args()
    source=(ROOT/'gpu/vk/vk_draw.cpp').read_text(encoding='utf-8')
    start=source.index('VkDescriptorBufferInfo uniform_range(')
    start=source.index('uint32_t used = index < Shader::Info::MAX_CBUFS',start)
    stop=source.index('if (index == 0 || index == 2)',start)
    used=source[start:stop]
    begin=source.index('const uint32_t n =',stop);end=source.index(';',begin)+1
    rounded=source[begin:end]
    fixture=r'''
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <vector>
struct Descriptor { uint32_t cbuf_index,cbuf_offset,count; };
struct Info { static constexpr uint32_t MAX_CBUFS=18;bool uses_global_memory=false;
    std::array<uint32_t,MAX_CBUFS> constant_buffer_used_sizes{};std::vector<Descriptor> storage_buffers_descriptors; };
namespace Shader { using Info=::Info; }
struct Stage { Info info; };
uint32_t extent(const Stage& st,uint32_t index) {
''' + used + rounded + r'''
    return n;
}
int main() {
    unsigned cases=0;
    for(uint32_t size : {0x690u,0x6a0u,0x780u,0x790u}) {
        Stage st;st.info.uses_global_memory=true;st.info.constant_buffer_used_sizes[0]=size;
        st.info.storage_buffers_descriptors={{0,0x880,3}};
        if(extent(st,0)!=0x8b0){std::fprintf(stderr,"generated table needs0x8b0; bound0x%x\n",extent(st,0));return 1;}
        ++cases;
        st.info.uses_global_memory=false;
        if(extent(st,0)!=size)return 2;
        ++cases;
    }
    Stage st;st.info.uses_global_memory=true;st.info.constant_buffer_used_sizes[4]=0x100;
    st.info.storage_buffers_descriptors={{0,0x880,3},{4,0xe0,16},{2,0x20,1}};
    if(extent(st,4)!=0x1e0 || extent(st,2)!=0x30)return 3;
    cases+=2;
    st.info.constant_buffer_used_sizes[0]=0xa00;
    if(extent(st,0)!=0xa00)return 4;
    st.info.storage_buffers_descriptors.clear();st.info.constant_buffer_used_sizes[0]=0;
    if(extent(st,0)!=16 || extent(st,99)!=16)return 5;
    cases+=3;
    std::printf("PASS: %u generated-table, stage-range, non-global, bank and minimum-size cases\n",cases);
}
'''
    work=ROOT/'work';work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cbuf-extent-',dir=work) as t:
        folder=Path(t).resolve();folder.relative_to(work.resolve());cpp=folder/'fixture.cpp';exe=folder/'fixture.exe';cpp.write_text(fixture,encoding='utf-8')
        subprocess.run([a.cxx,'-std=c++20','-O2',str(cpp),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)


if __name__=='__main__':main()
