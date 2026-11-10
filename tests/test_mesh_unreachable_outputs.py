"""A mesh shader's branch to no known target leaves with no outputs, not OpUnreachable (backend/spirv/emit_spirv.cpp).

When a recompiled indirect branch reaches a target none of its table's entries match, the translator emitted
OpUnreachable. Mesa compiles that as a return, and RADV's mesh lowering then reads its vertex and primitive counts
before anything set them: GS_ALLOC_REQ asks for a garbage count and the GPU waits for primitives that never come (seen
on a PS5 with RADV, the code shared with Mesa on PC; issue 1000). Executing OpUnreachable is undefined anyway. In a
native mesh shader the case now stores the zero-outputs marker and returns, and PatchMeshInstructions turns the marker
into OpSetMeshOutputsEXT 0 0. The compute fallback and the other stages keep OpUnreachable.

Traverse's case and PatchMeshInstructions are cut into a Sirit fixture: a mesh shader with one branch to that case and
one to an epilogue (its own OpSetMeshOutputsEXT marker). Its SPIR-V must have no OpUnreachable, two
OpSetMeshOutputsEXT, the first of them 0 0, and pass spirv-val. Nothing runs on a GPU.

    python -I -B tests/test_mesh_unreachable_outputs.py --headers <SPIRV-Headers/include> [--cxx g++] [--spirv-val spirv-val]
"""
import argparse
from pathlib import Path
import struct
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}", "--headers", "{spirv_headers}", "--spirv-val", "{spirv_val}"]
# (spirv-val: SPIRV-Tools comes with the Linux runner's packages, not on Windows)
RUN_ALL_SKIP = {"windows": "needs spirv-val: checked on Linux"}

ROOT = Path(__file__).resolve().parents[1]
SPIRV = ROOT / "gpu" / "vk" / "eden" / "shader_recompiler" / "backend" / "spirv"


def block(text, marker, start=0):
    at = text.index(marker, start)
    end = text.index("{", at) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return at, end


FIXTURE = r"""
#include <array>
#include <cstdint>
#include <cstdio>
#include <stdexcept>
#include <vector>
#include <sirit/sirit.h>
using u32 = std::uint32_t;
using Sirit::Id;
struct LogicError : std::runtime_error { using std::runtime_error::runtime_error; };
enum class Stage { VertexB, Mesh };
struct EmitContext : Sirit::Module {
    using Sirit::Module::Module;
    Stage stage{Stage::Mesh};
    bool mesh_fallback{};
    Id u32_zero_value{};
    std::array<Id, 2> mesh_outputs_marker{};
    bool mesh_zero_outputs_marker{};
    std::array<Id, 4> mesh_tasks_marker{};
};
static void unreachable_case(EmitContext& ctx) {
@@CASE@@
}
@@PATCH@@
int main(int argc, char** argv) {
    EmitContext ctx{0x00010600};
    ctx.AddCapability(spv::Capability::Shader);
    ctx.AddCapability(spv::Capability::MeshShadingEXT);
    ctx.AddExtension("SPV_EXT_mesh_shader");
    ctx.SetMemoryModel(spv::AddressingModel::Logical, spv::MemoryModel::GLSL450);
    const Id u32t{ctx.TypeInt(32, false)}, boolt{ctx.TypeBool()}, voidt{ctx.TypeVoid()};
    ctx.u32_zero_value = ctx.Constant(u32t, 0u);
    const Id main{ctx.OpFunction(voidt, spv::FunctionControlMask::MaskNone, ctx.TypeFunction(voidt))};
    ctx.AddLabel();
    const Id lost{ctx.OpLabel()}, epilogue{ctx.OpLabel()};
    ctx.OpSelectionMerge(epilogue, spv::SelectionControlMask::MaskNone);
    ctx.OpBranchConditional(ctx.ConstantTrue(boolt), lost, epilogue);
    ctx.AddLabel(lost);
    unreachable_case(ctx);   // (the branch with no target)
    ctx.AddLabel(epilogue);   // (MeshEpilogue's marker: OpSetMeshOutputsEXT max_vertices, count)
    const Id vertices{ctx.Constant(u32t, 3u)}, count{ctx.Constant(u32t, 1u)};
    ctx.OpStore(vertices, count);
    ctx.mesh_outputs_marker = {vertices, count};
    ctx.OpReturn();
    ctx.OpFunctionEnd();
    ctx.AddEntryPoint(spv::ExecutionModel::MeshEXT, main, "main");
    ctx.AddExecutionMode(main, spv::ExecutionMode::LocalSize, 1u, 1u, 1u);
    ctx.AddExecutionMode(main, spv::ExecutionMode::OutputVertices, 3u);
    ctx.AddExecutionMode(main, spv::ExecutionMode::OutputPrimitivesEXT, 1u);
    ctx.AddExecutionMode(main, spv::ExecutionMode::OutputTrianglesEXT);
    std::vector<u32> code{ctx.Assemble()};
    PatchMeshInstructions(code, ctx);
    std::printf("zero %u vertices %u count %u\n", ctx.u32_zero_value.value, vertices.value, count.value);
    FILE* f = std::fopen(argv[1], "wb");
    std::fwrite(code.data(), 4, code.size(), f);
    std::fclose(f);
    return argc < 2;
}
"""


def instructions(words):
    i = 5
    while i < len(words):
        n = words[i] >> 16
        yield words[i] & 0xFFFF, words[i + 1:i + n]
        i += n


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headers", type=Path, required=True)
    parser.add_argument("--cxx", default="g++")
    parser.add_argument("--spirv-val", default="spirv-val")
    args = parser.parse_args()
    emit = (SPIRV / "emit_spirv.cpp").read_text(encoding="utf-8")
    case = emit.index("case IR::AbstractSyntaxNode::Type::Unreachable:")
    guard = "if (ctx.stage == Stage::Mesh && !ctx.mesh_fallback) {"
    if not emit[emit.index("\n", case):].lstrip().startswith(guard):
        raise SystemExit("FAIL: the Unreachable case does not start with the native mesh shader's exit")
    at, end = block(emit, guard, case)
    _, end = block(emit, "else", end)
    if "ctx.OpUnreachable();" not in emit[at:end]:
        raise SystemExit("FAIL: the other stages lost OpUnreachable")
    patch_at, patch_end = block(emit, "void PatchMeshInstructions(")
    if "bool mesh_zero_outputs_marker{};" not in (SPIRV / "spirv_emit_context.h").read_text(encoding="utf-8"):
        raise SystemExit("FAIL: EmitContext has no mesh_zero_outputs_marker")
    fixture = FIXTURE.replace("@@CASE@@", emit[at:end]).replace("@@PATCH@@", emit[patch_at:patch_end])
    sirit = ROOT / "gpu" / "vk" / "sirit"
    with tempfile.TemporaryDirectory(prefix="mesh-unreachable-") as tmp:
        tmp = Path(tmp)
        cpp, exe, spv = tmp / "fixture.cpp", tmp / "fixture", tmp / "mesh.spv"
        cpp.write_text(fixture, encoding="utf-8")
        r = subprocess.run([args.cxx, "-std=c++20", "-O1", "-I" + str(sirit / "include"), "-I" + str(sirit / "src"),
                            "-I" + str(args.headers), str(cpp), *map(str, sorted((sirit / "src").rglob("*.cpp"))), "-o", str(exe)],
                           capture_output=True, text=True, timeout=600)
        if r.returncode:
            print(r.stdout + r.stderr)
            raise SystemExit("the fixture did not build")
        r = subprocess.run([str(exe), str(spv)], capture_output=True, text=True, timeout=30)
        print(r.stdout + r.stderr, end="")
        if r.returncode:
            raise SystemExit("FAIL: the fixture stopped (the marker was not patched?)")
        zero, vertices, count = (int(w) for w in r.stdout.split()[1::2])
        data = spv.read_bytes()
        words = list(struct.unpack("<%dI" % (len(data) // 4), data))
        ops = list(instructions(words))
        OP_UNREACHABLE, OP_STORE, OP_SET_MESH_OUTPUTS = 255, 62, 5295
        if any(op == OP_UNREACHABLE for op, _ in ops):
            raise SystemExit("FAIL: the mesh shader still has OpUnreachable")
        sets = [operands for op, operands in ops if op == OP_SET_MESH_OUTPUTS]
        if sets != [[zero, zero], [vertices, count]]:
            raise SystemExit("FAIL: expected OpSetMeshOutputsEXT 0 0, then the epilogue's: %s" % sets)
        if any(op == OP_STORE and operands[:1] in ([zero], [vertices]) for op, operands in ops):
            raise SystemExit("FAIL: a marker OpStore is left")
        r = subprocess.run([args.spirv_val, "--target-env", "vulkan1.3", str(spv)], capture_output=True, text=True, timeout=60)
        if r.returncode:
            print(r.stdout + r.stderr)
            raise SystemExit("FAIL: spirv-val")
    print("PASS: a mesh shader's branch with no target sets no outputs and returns; the SPIR-V validates")


if __name__ == "__main__":
    main()
