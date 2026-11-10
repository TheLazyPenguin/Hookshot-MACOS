"""Validate real texture-pass unsigned image types without game files or a GPU.

python nx2/test_unsigned_image_types.py --headers <SPIRV-Headers/include> --spirv-val spirv-val [--cxx clang++]
Builds the same Eden IR/SPIR-V and Sirit sources as the renderer, with its compatibility headers.
"""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}", "--headers", "{spirv_headers}", "--spirv-val", "{spirv_val}"]
# (spirv-val: SPIRV-Tools comes with the Linux runner's packages, not on Windows)
RUN_ALL_SKIP = {"windows": "needs spirv-val: checked on Linux"}

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', default='clang++')
    parser.add_argument('--headers', type=Path, required=True)
    parser.add_argument('--spirv-val', default='spirv-val')
    args = parser.parse_args()
    vk = ROOT / 'gpu/vk'
    sources = sorted({p for directory in ('eden/shader_recompiler/backend/spirv',
                      'eden/shader_recompiler/frontend/ir', 'eden/shader_recompiler/ir_opt', 'sirit/src')
                      for p in (vk / directory).rglob('*.cpp')})
    flags = ['-std=c++20', '-O1', '-D_CRT_SECURE_NO_WARNINGS', '-DVK_NO_PROTOTYPES', '-DMKWVK_INCLUDES=2']
    for header in ('algorithm', 'cstdio', 'cstdlib', 'cstring', 'functional', 'string', 'vector'):
        flags += ['-include', header]
    flags += ['-I' + str(p) for p in (vk / 'compat', ROOT / 'gpu/compat', vk / 'eden',
              ROOT / 'gpu/third_party/suyu', vk / 'sirit/include', vk / 'sirit/src', args.headers)]
    work = ROOT / 'work'
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='unsigned-image-types-', dir=work) as temp:
        folder = Path(temp).resolve()
        exe = folder / 'fixture.exe'
        subprocess.run([args.cxx, *flags, str(ROOT / 'tests/unsigned_image_types_ir.cpp'),
                        *map(str, sources), '-o', str(exe)], check=True)
        emitted = subprocess.run([str(exe), str(folder)], check=True, capture_output=True, text=True)
        print(emitted.stderr, end='')
        cases = ('r32-read', 'r32-write', 'buffer-r32-write', 'atomic-r32-add',
                 'atomic-r32-smin', 'typeless-read', 'typeless-write')
        for case in cases:
            floating, integer = (folder / f'{case}-{kind}.spv' for kind in ('float', 'int'))
            for module in (floating, integer):
                subprocess.run([args.spirv_val, '--target-env', 'vulkan1.3', str(module)], check=True)
            if not case.startswith('typeless-'):
                assert floating.read_bytes() == integer.read_bytes(), f'{case}: unsigned format depends on Env answer'
        counts = dict(line.split(' questions=') for line in emitted.stderr.splitlines())
        assert len(counts) == 14, emitted.stderr
        for case in cases:
            for kind in ('float', 'int'):
                expected = '1' if case.startswith('typeless-') else '0'
                assert counts[f'{case}-{kind}'] == expected, emitted.stderr
    print('PASS: explicit unsigned image types ignore Env answers; Typeless queries retained; 14 modules validate')



if __name__ == '__main__':
    main()

