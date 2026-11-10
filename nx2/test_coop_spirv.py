"""Validate cooperative-matrix capability setup without a GPU or game files.

python nx2/test_coop_spirv.py --cxx clang++ --headers <SPIRV-Headers/include> --spirv-val <spirv-val>
Uses this repository's Sirit and the actual self-test builder/native-emitter setup.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--headers", "{spirv_headers}", "--spirv-val", "{spirv_val}"]
# (spirv-val: SPIRV-Tools comes with the Linux runner's packages, not on Windows)
RUN_ALL_SKIP = {"windows": "needs spirv-val: checked on Linux"}

ROOT = Path(__file__).resolve().parents[1]


def block(text, marker):
    start = text.index(marker)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', default='clang++')
    parser.add_argument('--headers', type=Path, required=True)
    parser.add_argument('--spirv-val', default='spirv-val')
    args = parser.parse_args()
    vk = ROOT / 'gpu/vk'
    source = (vk / 'vk_coopmat.cpp').read_text(encoding='utf-8')
    builder = source[source.index('struct TestShader {'):source.index('// one dispatch of a 32-lane shader')]
    emitter = (vk / 'eden/shader_recompiler/backend/spirv/emit_spirv.cpp').read_text(encoding='utf-8')
    setup = block(emitter, 'if (info.uses_cooperative_matrix && !mma_software)')
    fixture = '''#include <cstdio>
#include <cstdlib>
#include <functional>
#include <string>
#include <vector>
#include <sirit/sirit.h>
''' + builder + '''
std::vector<uint32_t> program(bool cooperative, bool mma_software, bool physical = false) {
    using namespace Sirit;
    Module ctx{0x00010600};
    ctx.AddCapability(spv::Capability::Shader);
    const auto addressing = physical ? spv::AddressingModel::PhysicalStorageBuffer64 : spv::AddressingModel::Logical;
    ctx.SetMemoryModel(addressing, spv::MemoryModel::GLSL450);
    if (physical) {
        ctx.AddCapability(spv::Capability::PhysicalStorageBufferAddresses);
        ctx.AddExtension("SPV_KHR_physical_storage_buffer");
    }
    struct { bool uses_cooperative_matrix; } info{cooperative};
''' + setup + '''
    const Id void_t = ctx.TypeVoid(), u32 = ctx.TypeUInt(32);
    const Id main = ctx.OpFunction(void_t, spv::FunctionControlMask::MaskNone, ctx.TypeFunction(void_t));
    ctx.AddLabel();
    // Native programs can contain device-scope barriers (emit_spirv_barriers.cpp).
    const auto semantics = spv::MemorySemanticsMask::AcquireRelease | spv::MemorySemanticsMask::UniformMemory |
        spv::MemorySemanticsMask::WorkgroupMemory | spv::MemorySemanticsMask::AtomicCounterMemory |
        spv::MemorySemanticsMask::ImageMemory;
    ctx.OpMemoryBarrier(ctx.Constant(u32, uint32_t(spv::Scope::Device)), ctx.Constant(u32, uint32_t(semantics)));
    ctx.OpReturn(); ctx.OpFunctionEnd();
    ctx.AddEntryPoint(spv::ExecutionModel::GLCompute, main, "main");
    ctx.AddExecutionMode(main, spv::ExecutionMode::LocalSize, 32U, 1U, 1U);
    auto code = ctx.Assemble();
    const auto model = cooperative && !mma_software ? spv::MemoryModel::VulkanKHR : spv::MemoryModel::GLSL450;
    for (size_t i = 5; i < code.size(); i += code[i] >> 16)
        if ((code[i] & 0xffff) == uint32_t(spv::Op::OpMemoryModel) &&
            (code[i + 1] != uint32_t(addressing) || code[i + 2] != uint32_t(model))) {
            std::fprintf(stderr, "addressing or memory model changed unexpectedly\\n"); std::exit(6);
        }
    return code;
}
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    const std::vector<std::vector<uint32_t>> modules{
        build_shader([](TestShader&){}), program(true, false), program(true, true), program(false, false),
        program(true, false, true), program(true, true, true), program(false, false, true)};
    for (unsigned i = 0; i < modules.size(); i++) {
        const std::string name = std::string(argv[1]) + "/case" + std::to_string(i) + ".spv";
        FILE* f = std::fopen(name.c_str(), "wb"); if (!f) return 3;
        const auto n = std::fwrite(modules[i].data(), 4, modules[i].size(), f);
        std::fclose(f); if (n != modules[i].size()) return 4;
    }
}
'''
    work = ROOT / 'work'
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='coop-spirv-', dir=work) as tmp:
        directory = Path(tmp).resolve()
        directory.relative_to(work.resolve())
        cpp = directory / 'fixture.cpp'
        cpp.write_text(fixture, encoding='utf-8')
        sirit = vk / 'sirit'
        exe = directory / 'fixture.exe'
        command = [args.cxx, '-std=c++20', '-O1', '-I' + str(sirit / 'include'), '-I' + str(sirit / 'src'),
                   '-I' + str(args.headers), str(cpp), *map(str, sorted((sirit / 'src').rglob('*.cpp'))), '-o', str(exe)]
        subprocess.run(command, check=True)
        subprocess.run([str(exe), str(directory)], check=True)
        for index, name in enumerate(('matrix self-test', 'native matrix with device barrier', 'software matrix', 'ordinary shader',
                                      'native matrix with physical addressing', 'software matrix with physical addressing',
                                      'ordinary shader with physical addressing')):
            subprocess.run([args.spirv_val, '--target-env', 'vulkan1.3', str(directory / ('case%d.spv' % index))], check=True)
            print('PASS:', name)


if __name__ == '__main__':
    main()
