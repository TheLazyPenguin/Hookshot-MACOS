"""Check Sirit keeps independently decorated structures separate.
python nx2/test_spirv_struct_identity.py --headers <SPIRV-Headers/include> --spirv-val spirv-val
No GPU or game files needed. Requires a configured C++ compiler.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--headers", "{spirv_headers}", "--spirv-val", "{spirv_val}"]
# (spirv-val: SPIRV-Tools comes with the Linux runner's packages, not on Windows)
RUN_ALL_SKIP = {"windows": "needs spirv-val: checked on Linux"}

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--headers',type=Path,required=True);p.add_argument('--spirv-val',required=True);p.add_argument('--cxx',default='clang++');a=p.parse_args()
    fixture=r'''
#include <sirit/sirit.h>
#include <cstdio>
#include <string>
#include <vector>
using namespace Sirit;
int main(int argc,char** argv) {
    if(argc!=2)return 1;
    for(unsigned local=0;local<2;local++) {
        Module m{0x00010600};m.AddCapability(spv::Capability::Shader);m.AddCapability(spv::Capability::Int64);
        m.AddCapability(spv::Capability::PhysicalStorageBufferAddresses);
        m.SetMemoryModel(spv::AddressingModel::PhysicalStorageBuffer64,spv::MemoryModel::GLSL450);
        const Id u32=m.TypeUInt(32),u64=m.TypeUInt(64),void_t=m.TypeVoid(),zero=m.Constant(u32,0U);
        std::vector<Id> interfaces;
        // Mirrors first-task, Private local memory, and global-memory wrapper declarations.
        auto block=[&]{Id t=m.TypeStruct(u32);m.Decorate(t,spv::Decoration::Block);m.MemberDecorate(t,0U,spv::Decoration::Offset,0U);return t;};
        const Id first=block();
        if(local) {
            const Id element=m.TypeStruct(u32),array=m.TypeArray(element,m.Constant(u32,4U));
            interfaces.push_back(m.AddGlobalVariable(m.TypePointer(spv::StorageClass::Private,array),spv::StorageClass::Private));
        }
        const Id global=block(),member=m.TypePointer(spv::StorageClass::PhysicalStorageBuffer,u32);
        const Id first_ptr=m.TypePointer(spv::StorageClass::PhysicalStorageBuffer,first);
        const Id global_ptr=m.TypePointer(spv::StorageClass::PhysicalStorageBuffer,global);
        const Id fn=m.OpFunction(void_t,spv::FunctionControlMask::MaskNone,m.TypeFunction(void_t));m.AddLabel();
        const Id address=m.Constant(u64,uint64_t{16});
        m.OpLoad(u32,m.OpAccessChain(member,m.OpConvertUToPtr(first_ptr,address),zero),spv::MemoryAccessMask::Aligned,4U);
        const Id ptr=m.OpAccessChain(member,m.OpConvertUToPtr(global_ptr,address),zero);
        m.OpStore(ptr,zero,spv::MemoryAccessMask::Aligned,4U);
        m.OpAtomicIAdd(u32,ptr,m.Constant(u32,1U),zero,zero);
        m.OpReturn();m.OpFunctionEnd();m.AddEntryPoint(spv::ExecutionModel::GLCompute,fn,"main",interfaces);
        m.AddExecutionMode(fn,spv::ExecutionMode::LocalSize,1U,1U,1U);
        auto words=m.Assemble();std::string path=std::string(argv[1])+"/"+std::to_string(local)+".spv";
        FILE* f=std::fopen(path.c_str(),"wb");if(!f)return 2;
        const auto written=std::fwrite(words.data(),4,words.size(),f);std::fclose(f);if(written!=words.size())return 3;
        // Scalar and pointer declarations must retain their existing reuse.
        if(m.TypeUInt(32).value!=u32.value || m.TypePointer(spv::StorageClass::PhysicalStorageBuffer,u32).value!=member.value)return 4;
    }
}
'''
    work=ROOT/'work';work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='struct-identity-',dir=work) as temp:
        folder=Path(temp).resolve();cpp=folder/'fixture.cpp';exe=folder/'fixture.exe';cpp.write_text(fixture,encoding='utf-8');sirit=ROOT/'gpu/vk/sirit'
        subprocess.run([a.cxx,'-std=c++20','-O1','-I'+str(sirit/'include'),'-I'+str(sirit/'src'),'-I'+str(a.headers),str(cpp),*map(str,sorted((sirit/'src').rglob('*.cpp'))),'-o',str(exe)],check=True)
        subprocess.run([str(exe),str(folder)],check=True)
        for case in range(2):subprocess.run([a.spirv_val,'--target-env','vulkan1.3',str(folder/f'{case}.spv')],check=True)
    print('PASS: two physical-buffer modules, with/without Private local memory; scalar/pointer reuse preserved')


if __name__=='__main__':main()
