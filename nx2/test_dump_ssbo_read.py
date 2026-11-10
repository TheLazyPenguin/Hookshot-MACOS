"""Check that optional SSBO diagnostics never read an unbound guest address.
Run: python nx2/test_dump_ssbo_read.py [--cxx clang++]
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "g++"]

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cxx',default='clang++')
    a=p.parse_args()
    source=(ROOT/'gpu/vk/vk_draw.cpp').read_text(encoding='utf-8')
    start=source.index('const bool read = ',source.index('if (dump_on() && dump_ssbo_wanted(p.key)) {'))
    read=source[start:source.index(';',start)+1]
    fixture=r'''
#include <cstdint>
#include <cstdio>
#include <vector>
unsigned calls=0;
struct Host { bool gpu_read(uint64_t,void*,uint64_t){++calls;return true;} } instance;
Host* host=&instance;
bool sample(bool b,uint64_t addr,unsigned size) {
    std::vector<uint32_t> words(size);
    const uint64_t base=addr;
''' + read + r'''
    return read;
}
int main() {
    if(sample(false,0x1001234000ull,16) || calls){std::puts("FAIL: unbound address read by dump");return 1;}
    if(sample(true,0,16) || calls)return 2;
    if(sample(true,0x1001234000ull,0) || calls)return 3;
    if(!sample(true,0x1001234000ull,16) || calls!=1)return 4;
    std::puts("PASS: unbound, null, empty and bound diagnostic reads");
}
'''
    work=ROOT/'work';work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dump-ssbo-',dir=work) as t:
        folder=Path(t).resolve();folder.relative_to(work.resolve())
        cpp,exe=folder/'fixture.cpp',folder/'fixture.exe'
        cpp.write_text(fixture,encoding='utf-8')
        subprocess.run([a.cxx,'-std=c++20','-O2',str(cpp),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)


if __name__=='__main__':main()
