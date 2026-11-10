"""Test SPIR-V to Metal Shading Language (MSL) translation via SPIRV-Cross."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GPU = ROOT / "gpu"
THIRD_PARTY = ROOT / "third_party"


class MetalSpirvMslTests(unittest.TestCase):
    def test_translate_spirv_to_msl_compiles_and_translates(self):
        clangxx = os.environ.get("CXX", "clang++")
        test_cpp = """
#include "gpu/metal/mtl_shader.h"
#include <cassert>
#include <iostream>

int main() {
    // 1. Test empty input error handling
    auto empty_res = mkwmtl::translate_spirv_to_msl(nullptr, 0, mkwmtl::ShaderType::Vertex);
    assert(!empty_res.ok);
    assert(!empty_res.error.empty());

    // 2. Test minimal valid SPIR-V shader:
    // Magic: 0x07230203, Version: 0x00010000, Generator: 0, Bound: 5, Schema: 0
    // OpCapability Shader (0x00020011, 1)
    // OpMemoryModel Logical GLSL450 (0x0003000e, 0, 1)
    // OpEntryPoint Vertex %4 "main" (0x0003000f, 0, 4, 0x6e69616d, 0)
    // OpTypeVoid %1 (0x00020013, 1)
    // OpTypeFunction %2 %1 (0x00030021, 2, 1)
    // OpFunction %1 %4 None %2 (0x00050036, 1, 4, 0, 2)
    // OpLabel %3 (0x000200f8, 3)
    // OpReturn (0x000100fd)
    // OpFunctionEnd (0x00010038)
    const uint32_t minimal_spv[] = {
        0x07230203, 0x00010000, 0x00000000, 0x00000005, 0x00000000,
        0x00020011, 0x00000001,
        0x0003000e, 0x00000000, 0x00000001,
        0x0004000f, 0x00000000, 0x00000004, 0x006e696d,
        0x00020013, 0x00000001,
        0x00030021, 0x00000002, 0x00000001,
        0x00050036, 0x00000001, 0x00000004, 0x00000000, 0x00000002,
        0x000200f8, 0x00000003,
        0x000100fd,
        0x00010038
    };

    auto res = mkwmtl::translate_spirv_to_msl(minimal_spv, sizeof(minimal_spv) / sizeof(uint32_t), mkwmtl::ShaderType::Vertex);
    if (!res.ok) {
        std::cerr << "Translation failed: " << res.error << std::endl;
        return 1;
    }

    assert(res.ok);
    assert(res.source.find("main0") != std::string::npos || res.source.find("vertex") != std::string::npos);
    assert(res.entry_point == "main0");

    std::cout << "PASS: SPIR-V to MSL translation succeeded" << std::endl;
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="hookshot-msl-test-") as tmpdir:
            src_file = Path(tmpdir) / "test.cpp"
            bin_file = Path(tmpdir) / "test_bin"
            src_file.write_text(test_cpp, encoding="utf-8")

            spv_cross_dir = THIRD_PARTY / "spirv-cross"
            mtl_src = str(GPU / "metal" / "mtl_shader.mm")
            # On Linux (non-Darwin CI), compile .mm as standard C++ without GNU objc runtime
            mtl_unit = ["-x", "c++", mtl_src] if sys.platform != "darwin" else [mtl_src]
            compile_cmd = [
                clangxx, "-std=c++20", "-O2",
                str(src_file),
                *mtl_unit,
                str(spv_cross_dir / "spirv_cross.cpp"),
                str(spv_cross_dir / "spirv_cross_parsed_ir.cpp"),
                str(spv_cross_dir / "spirv_parser.cpp"),
                str(spv_cross_dir / "spirv_cfg.cpp"),
                str(spv_cross_dir / "spirv_glsl.cpp"),
                str(spv_cross_dir / "spirv_msl.cpp"),
                f"-I{ROOT}",
                f"-I{GPU / 'vk'}",
                f"-I{GPU / 'metal'}",
                f"-I{spv_cross_dir}",
                "-o", str(bin_file)
            ]
            r = subprocess.run(compile_cmd, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"Compilation failed:\n{r.stderr}\n{r.stdout}")

            run_res = subprocess.run([str(bin_file)], capture_output=True, text=True)
            self.assertEqual(run_res.returncode, 0, f"Execution failed:\n{run_res.stderr}\n{run_res.stdout}")
            self.assertIn("PASS", run_res.stdout)


if __name__ == "__main__":
    unittest.main()
