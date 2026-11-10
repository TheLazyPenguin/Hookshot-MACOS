"""Real TexturePass/Collect/Emit conditional descriptor-index regression; synthetic inputs only."""
# SPDX-License-Identifier: GPL-3.0-or-later
# Build pattern retained from test_depth_sample_types.py.
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--headers", "{spirv_headers}", "--spirv-val", "{spirv_val}"]
# (spirv-val: SPIRV-Tools comes with the Linux runner's packages, not on Windows)
RUN_ALL_SKIP = {"windows": "needs spirv-val: checked on Linux"}

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', default='clang++')
    parser.add_argument('--headers', type=Path, required=True)
    parser.add_argument('--spirv-val', default='spirv-val')
    parser.add_argument('--source', type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.source.resolve()
    vk = root / 'gpu/vk'
    sources = sorted({p for directory in ('eden/shader_recompiler/backend/spirv',
                      'eden/shader_recompiler/frontend/ir', 'eden/shader_recompiler/ir_opt', 'sirit/src')
                      for p in (vk / directory).rglob('*.cpp')})
    flags = ['-std=c++20', '-O1', '-D_CRT_SECURE_NO_WARNINGS', '-DVK_NO_PROTOTYPES', '-DMKWVK_INCLUDES=2']
    for header in ('algorithm', 'cstdio', 'cstdlib', 'cstring', 'functional', 'string', 'vector'):
        flags += ['-include', header]
    flags += ['-I' + str(p) for p in (vk / 'compat', root / 'gpu/compat', vk / 'eden',
              root / 'gpu/third_party/suyu', vk / 'sirit/include', vk / 'sirit/src', args.headers)]
    with tempfile.TemporaryDirectory(prefix='texture-phi-') as temp:
        folder = Path(temp).resolve()
        exe = folder / 'fixture.exe'
        subprocess.run([args.cxx, *flags, str(ROOT / 'tests/texture_phi_dominance_ir.cpp'),
                        *map(str, sources), '-o', str(exe)], check=True)
        emitted = subprocess.run([str(exe), str(folder)], capture_output=True, text=True)
        print(emitted.stdout, end='', flush=True)
        print(emitted.stderr, end='', flush=True)
        emitted.check_returncode()
        failures = []
        for name in ('same-block', 'diamond', 'offset-phi', 'repeated-condition'):
            print(name, 'sha256', hashlib.sha256((folder / (name + '.spv')).read_bytes()).hexdigest(), flush=True)
            result = subprocess.run([args.spirv_val, '--target-env', 'vulkan1.3', str(folder / (name + '.spv'))], capture_output=True, text=True)
            print(name, 'validator-exit', result.returncode, result.stdout, result.stderr, flush=True)
            if result.returncode:
                failures.append(name + ': SPIR-V validation')
        if 'IR_DOMINANCE=FAIL' in emitted.stdout:
            failures.append('rewritten IR directly consumes a branch-local index')
        if 'SELECTION=FAIL' in emitted.stdout:
            failures.append('rewritten index selects the wrong incoming texture')
        if failures:
            raise AssertionError('; '.join(failures))
    print('PASS: conditional handle indices preserve SSA dominance; positive control validates')

if __name__ == '__main__':
    main()
