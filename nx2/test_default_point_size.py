"""Check actual vertex runtime setup and Eden's fixed-size emitter; no game/GPU required.

python nx2/test_default_point_size.py --headers <SPIRV-Headers/include> [--cxx clang++] [--spirv-val spirv-val]
"""
import argparse
from pathlib import Path
import subprocess,tempfile

RUN_ALL_ARGS = ["--headers", "{spirv_headers}", "--spirv-val", "{spirv_val}"]
# (spirv-val: SPIRV-Tools comes with the Linux runner's packages, not on Windows)
RUN_ALL_SKIP = {"windows": "needs spirv-val: checked on Linux"}

ROOT=Path(__file__).resolve().parents[1]
def block(text,marker):
    start=text.index(marker);end=text.index('{',start)+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--headers',type=Path,required=True);p.add_argument('--cxx',default='clang++');p.add_argument('--spirv-val',default='spirv-val');a=p.parse_args()
    source=(ROOT/'gpu/vk/vk_shader.cpp').read_text(encoding='utf-8')
    start=source.index('            Shader::RuntimeInfo vrt{};');end=source.index('            //',start)
    setup=source[start:end]
    helper=block((ROOT/'gpu/vk/eden/shader_recompiler/backend/spirv/emit_spirv_special.cpp').read_text(encoding='utf-8'),'void SetFixedPipelinePointSize(')
    fixture=r'''#include <array>
#include <cstdio>
#include <cstdlib>
#include <optional>
#include <string>
#include <vector>
#include <sirit/sirit.h>
#define CHECK(x) do{if(!(x)){std::fprintf(stderr,"FAIL:%d %s\n",__LINE__,#x);std::exit(1);}}while(0)
using namespace Sirit;
namespace Shader {namespace IR {enum Attribute {PointSize};} struct RuntimeInfo {std::optional<float> fixed_state_point_size;};}
struct EmitContext:Module {Shader::RuntimeInfo runtime_info;Id output_point_size;Id Const(float f){return Constant(TypeFloat(32),f);}};
''' +helper+r'''
std::vector<uint32_t> run(bool writes) {
    struct {struct {struct {std::array<bool,1> stores;}info;}program;} vertex{};auto vs=&vertex;vs->program.info.stores[0]=writes;
''' +setup+r'''
    CHECK(writes ? !vrt.fixed_state_point_size : vrt.fixed_state_point_size==1.0f);
    EmitContext ctx;ctx.runtime_info=vrt;ctx.AddCapability(spv::Capability::Shader);
    ctx.SetMemoryModel(spv::AddressingModel::Logical,spv::MemoryModel::GLSL450);
    const Id f32=ctx.TypeFloat(32),ptr=ctx.TypePointer(spv::StorageClass::Output,f32);
    ctx.output_point_size=ctx.AddGlobalVariable(ptr,spv::StorageClass::Output);ctx.Decorate(ctx.output_point_size,spv::Decoration::BuiltIn,spv::BuiltIn::PointSize);
    const Id void_t=ctx.TypeVoid(),main=ctx.OpFunction(void_t,spv::FunctionControlMask::MaskNone,ctx.TypeFunction(void_t));ctx.AddLabel();
    if(writes)ctx.OpStore(ctx.output_point_size,ctx.Const(2.0f));
    SetFixedPipelinePointSize(ctx);ctx.OpReturn();ctx.OpFunctionEnd();ctx.AddEntryPoint(spv::ExecutionModel::Vertex,main,"main",ctx.output_point_size);
    auto words=ctx.Assemble();unsigned stores=0;for(size_t i=5;i<words.size();i+=words[i]>>16)stores+=(words[i]&65535)==62;
    CHECK(stores==1);return words;
}
int main(int argc,char**argv){CHECK(argc==2);for(bool writes:{false,true}){auto words=run(writes);std::string path=std::string(argv[1])+"/"+(writes?"shader":"default")+".spv";FILE*f=std::fopen(path.c_str(),"wb");CHECK(f);CHECK(std::fwrite(words.data(),4,words.size(),f)==words.size());std::fclose(f);}puts("PASS: missing PointSize writes default1; explicit shader size retained with no extra store");}
'''
    work=ROOT/'work';work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='point-size-',dir=work) as temp:
        d=Path(temp).resolve();d.relative_to(work.resolve());cpp=d/'fixture.cpp';exe=d/'fixture.exe';cpp.write_text(fixture,encoding='utf-8')
        sirit=ROOT/'gpu/vk/sirit'
        sources=sorted((sirit/'src').glob('*.cpp'))+sorted((sirit/'src/instructions').glob('*.cpp'))
        subprocess.run([a.cxx,'-std=c++20','-O1','-D_CRT_SECURE_NO_WARNINGS','-I'+str(a.headers),'-I'+str(sirit/'include'),'-I'+str(sirit/'src'),str(cpp),*map(str,sources),'-o',str(exe)],check=True)
        subprocess.run([str(exe),str(d)],check=True)
        for module in d.glob('*.spv'):subprocess.run([a.spirv_val,'--target-env','vulkan1.3',str(module)],check=True)
if __name__=='__main__':main()
