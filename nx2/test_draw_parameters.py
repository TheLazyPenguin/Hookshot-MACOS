"""Validate the actual DrawParameters capability block across input/profile combinations; no game or GPU.

python nx2/test_draw_parameters.py --headers <SPIRV-Headers/include> [--cxx clang++] [--spirv-val spirv-val]
"""
import argparse
from pathlib import Path
import subprocess,tempfile

RUN_ALL_ARGS = ["--headers", "{spirv_headers}", "--spirv-val", "{spirv_val}"]
# (spirv-val: SPIRV-Tools comes with the Linux runner's packages, not on Windows)
RUN_ALL_SKIP = {"windows": "needs spirv-val: checked on Linux"}

ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--headers',type=Path,required=True);p.add_argument('--cxx',default='clang++');p.add_argument('--spirv-val',default='spirv-val');a=p.parse_args()
    source=(ROOT/'gpu/vk/eden/shader_recompiler/backend/spirv/emit_spirv.cpp').read_text(encoding='utf-8')
    end=source.index('ctx.AddCapability(spv::Capability::DrawParameters);')
    start=source.rfind('\n    if (',0,end)+1;end=source.index('\n    }',end)+6
    capability=source[start:end]
    fixture='''#include <array>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include <sirit/sirit.h>
namespace IR { enum Attribute { InstanceId, VertexId, BaseInstance, BaseVertex, DrawID }; }
std::vector<uint32_t> program(unsigned mask,bool supported) {
    using namespace Sirit;
    // (EmitContext's own members the block reads: a task program's DrawIndex, and the mesh fallback (compute) that has none;
    // both off here, as for every vertex program)
    struct Ctx : Module { using Module::Module; bool wants_mesh_first{}, mesh_fallback{}; } ctx{0x00010600};ctx.AddCapability(spv::Capability::Shader);
    ctx.SetMemoryModel(spv::AddressingModel::Logical,spv::MemoryModel::GLSL450);
    struct { bool support_vertex_instance_id; } profile{supported};
    struct { std::array<bool,5> loads; } info{};
    for(unsigned i=0;i<5;i++)info.loads[i]=(mask>>i)&1;
'''+capability+'''
    const Id u32=ctx.TypeUInt(32),ptr=ctx.TypePointer(spv::StorageClass::Input,u32),void_t=ctx.TypeVoid();
    std::vector<Id> inputs;
    auto input=[&](spv::BuiltIn builtin){
        Id v=ctx.AddGlobalVariable(ptr,spv::StorageClass::Input);ctx.Decorate(v,spv::Decoration::BuiltIn,builtin);inputs.push_back(v);
    };
    // DefineInputs emits these directly, or synthesizes Base* for Vulkan's Instance/VertexIndex path.
    if(info.loads[IR::BaseInstance] || (!supported && info.loads[IR::InstanceId]))input(spv::BuiltIn::BaseInstance);
    if(info.loads[IR::BaseVertex] || (!supported && info.loads[IR::VertexId]))input(spv::BuiltIn::BaseVertex);
    if(info.loads[IR::DrawID])input(spv::BuiltIn::DrawIndex);
    const Id main=ctx.OpFunction(void_t,spv::FunctionControlMask::MaskNone,ctx.TypeFunction(void_t));
    ctx.AddLabel();ctx.OpReturn();ctx.OpFunctionEnd();ctx.AddEntryPoint(spv::ExecutionModel::Vertex,main,"main",inputs);
    return ctx.Assemble();
}
int main(int argc,char**argv) {
    if(argc!=2)return 1;
    for(unsigned support=0;support<2;support++)for(unsigned mask=0;mask<32;mask++) {
        auto code=program(mask,support!=0);std::string name=std::string(argv[1])+"/"+std::to_string(support*32+mask)+".spv";
        FILE*f=std::fopen(name.c_str(),"wb");if(!f)return 2;
        auto n=std::fwrite(code.data(),4,code.size(),f);std::fclose(f);if(n!=code.size())return 3;
    }
}
'''
    work=ROOT/'work';work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='draw-parameters-',dir=work) as temp:
        directory=Path(temp).resolve();directory.relative_to(work.resolve());cpp=directory/'fixture.cpp';exe=directory/'fixture.exe';cpp.write_text(fixture,encoding='utf-8');sirit=ROOT/'gpu/vk/sirit'
        subprocess.run([a.cxx,'-std=c++20','-O1','-I'+str(sirit/'include'),'-I'+str(sirit/'src'),'-I'+str(a.headers),str(cpp),*map(str,sorted((sirit/'src').rglob('*.cpp'))),'-o',str(exe)],check=True)
        subprocess.run([str(exe),str(directory)],check=True)
        for case in range(64):subprocess.run([a.spirv_val,'--target-env','vulkan1.3',str(directory/f'{case}.spv')],check=True)
    print('PASS:64 draw-parameter input/profile combinations')
if __name__=='__main__':main()
