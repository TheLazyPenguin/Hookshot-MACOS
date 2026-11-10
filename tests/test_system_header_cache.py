"""Exercise the actual system-header cache check with authored headers and real GNU Make dependencies.

Run: python -I -B tests/test_system_header_cache.py --cc clang
No game, SDK headers, object compilation or executables are used.
"""
import argparse
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

RUN_ALL_ARGS = ["--cc", "clang"]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'third_party/a64-kit/tools'))
SOURCE = Path(os.environ.get('HOOKSHOT_HEADER_CACHE_SOURCE', ROOT / 'nx2/make_game.py'))
spec = importlib.util.spec_from_file_location('make_game_header_cache', SOURCE)
make_game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_game)
REAL_RUN, REAL_RMTREE, REAL_TEMPORARY = subprocess.run, shutil.rmtree, tempfile.TemporaryDirectory
COMPILER = None


class HeaderCacheTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(COMPILER, 'Pass an explicit --cc compiler supporting -M')
        self.temporary = tempfile.TemporaryDirectory(prefix='hookshot-headers-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.addCleanup(self.check_boundary)
        self.work = self.root / 'work'
        self.work.mkdir()
        self.version = None
        self.external = self.root / 'external'
        self.external.mkdir()
        self.dependency_failure = False
        self.probes = []
        self.removed = []

    def check_boundary(self):
        self.assertEqual(self.root.parent, Path(tempfile.gettempdir()).resolve())
        self.assertTrue(all(p.resolve().is_relative_to(self.root) for p in self.root.rglob('*')))

    def install(self, tag, extra_header=None):
        tools = self.root / 'versions' / tag / 'HookshotBuilder/tools'
        include = tools / 'include'
        include.mkdir(parents=True)
        for name in ('stdio.h', 'stdlib.h', 'windows.h'):
            text = '#include <' + extra_header + '>\n' if name == 'stdio.h' and extra_header else '\n'
            (include / name).write_text(text, encoding='ascii')
        if extra_header:
            (self.external / extra_header).write_text('\n', encoding='ascii')
        return tools

    def cache(self):
        for relative in ('objcache/key.o', 'sa/build/obj/probe.o'):
            path = self.work / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'authored cached-object sentinel')

    def cache_bytes(self):
        return {str(p.relative_to(self.work)): p.read_bytes() for top in ('objcache', 'sa/build/obj')
                for p in (self.work / top).rglob('*') if p.is_file()}

    def check(self, tools):
        test = self
        class Toolchain:
            @staticmethod
            def find(name):
                test.assertEqual(name, 'clang')
                return COMPILER

            @staticmethod
            def need(path):
                test.assertEqual(path, COMPILER)
                return path

            @staticmethod
            def native_target():
                return ['-nostdinc', '-I' + str(tools / 'include'), '-I' + str(test.external)]

        def run(command, **kwargs):
            self.assertEqual(command[0], COMPILER)
            self.assertTrue('-M' in command or command[1:] == ['--version'], command)
            if '-M' in command and self.dependency_failure:
                return subprocess.CompletedProcess(command, 1, '', 'authored dependency failure')
            if command[1:] == ['--version'] and self.version is not None:
                return subprocess.CompletedProcess(command, 0, self.version + '\n', '')
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.BELOW_NORMAL_PRIORITY_CLASS | subprocess.CREATE_NO_WINDOW
            result = REAL_RUN(command, **kwargs)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            if '-M' in command:
                self.probes.append(result.stdout)
                self.assertIn('stdio.h', result.stdout)
            return result

        def rmtree(path, **kwargs):
            target = Path(path).resolve()
            self.assertTrue(target.is_relative_to(self.root))
            if target in ((self.work / 'objcache').resolve(), (self.work / 'sa/build/obj').resolve()):
                self.removed.append(target)
            return REAL_RMTREE(target, **kwargs)

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(make_game, 'ROOT', str(tools)))
            stack.enter_context(mock.patch.object(make_game, 'LINUX', False))
            stack.enter_context(mock.patch.dict(sys.modules, {'toolchain': Toolchain}))
            stack.enter_context(mock.patch.object(make_game.tempfile, 'TemporaryDirectory',
                                                 side_effect=lambda: REAL_TEMPORARY(dir=self.root)))
            stack.enter_context(mock.patch.object(make_game.subprocess, 'run', side_effect=run))
            stack.enter_context(mock.patch.object(make_game.shutil, 'rmtree', side_effect=rmtree))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            make_game.drop_stale_objects(str(self.work))

    def test_relocated_install_with_spaces_keeps_cached_bytes(self):
        first, second = self.install('version one'), self.install('version two')
        self.check(first)
        self.assertIn('\\ ', self.probes[-1])  # Actual clang -M output, not a rewritten dependency model.
        self.cache()
        before = self.cache_bytes()
        self.check(second)
        self.assertEqual(self.cache_bytes(), before, 'Actual compiler dependencies:\n' + self.probes[-1])
        self.assertFalse(self.removed)

    def test_relocated_install_without_spaces_keeps_cached_bytes(self):
        first, second = self.install('version-one'), self.install('version-two')
        self.check(first)
        self.cache()
        before = self.cache_bytes()
        self.check(second)
        self.assertEqual(self.cache_bytes(), before)
        self.assertFalse(self.removed)

    def test_relocated_install_with_make_special_characters_keeps_cached_bytes(self):
        first, second = self.install('version #$ one'), self.install('version #$ two')
        self.check(first)
        self.assertIn(r'\#$$\ ', self.probes[-1])
        self.cache()
        before = self.cache_bytes()
        self.check(second)
        self.assertEqual(self.cache_bytes(), before)
        self.assertFalse(self.removed)

    def test_same_install_with_spaces_keeps_cached_bytes(self):
        tools = self.install('version one')
        self.check(tools)
        self.cache()
        before = self.cache_bytes()
        self.check(tools)
        self.assertEqual(self.cache_bytes(), before)

    def test_compiler_version_change_invalidates_objects(self):
        tools = self.install('version one')
        self.version = 'authored clang version 1'
        self.check(tools)
        self.cache()
        self.version = 'authored clang version 2'
        self.check(tools)
        self.assertFalse(self.cache_bytes())
        self.assertEqual(len(self.removed), 2)

    def test_external_header_set_change_invalidates_objects(self):
        first = self.install('version one', 'first.h')
        second = self.install('version two', 'second.h')
        self.check(first)
        self.cache()
        self.check(second)
        self.assertFalse(self.cache_bytes())
        self.assertEqual(len(self.removed), 2)

    def test_failed_dependency_probe_preserves_objects(self):
        tools = self.install('version one')
        self.check(tools)
        self.cache()
        before = self.cache_bytes()
        self.dependency_failure = True
        self.check(tools)
        self.assertEqual(self.cache_bytes(), before)
        self.assertFalse(self.removed)

    def test_linux_dispatch_keeps_upstream_header_check(self):
        self.cache()
        before = self.cache_bytes()
        with mock.patch.object(make_game, 'LINUX', True), \
             mock.patch.object(make_game, '_drop_stale_linux') as linux_check, \
             mock.patch.object(make_game.subprocess, 'run', side_effect=AssertionError('Windows probe reached on Linux')):
            make_game.drop_stale_objects(str(self.work))
        linux_check.assert_called_once_with(str(self.work))
        self.assertEqual(self.cache_bytes(), before)


class MakeDependencyWordsTests(unittest.TestCase):
    def test_compiler_make_escapes(self):
        cases = [
            (r't.o: C:/first\ path/stdio.h C:/second\ path/windows.h',
             ['t.o:', 'C:/first path/stdio.h', 'C:/second path/windows.h']),
            (r't.o: C:\SDK\include\stdio.h \\server\share\windows.h',
             ['t.o:', r'C:\SDK\include\stdio.h', r'\\server\share\windows.h']),
            (r't.o: C:\dir\\\ leading\ name\header.h',
             ['t.o:', r'C:\dir\ leading name\header.h']),
            ('t.o: /first\\ path/stdio.h \\\n /second\\ path/windows.h',
             ['t.o:', '/first path/stdio.h', '/second path/windows.h']),
            ('t.o: /first\\ path/stdio.h \\\r\n /second\\ path/windows.h',
             ['t.o:', '/first path/stdio.h', '/second path/windows.h']),
            (r't.o: C:/a\#b/$$value.h C:\dir\\#hash.h',
             ['t.o:', 'C:/a#b/$value.h', r'C:\dir\#hash.h']),
        ]
        for encoded, decoded in cases:
            with self.subTest(encoded=encoded):
                self.assertEqual(make_game.makefile_words(encoded), decoded)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', required=True)
    args, remaining = parser.parse_known_args()
    COMPILER = shutil.which(args.cc) or args.cc
    unittest.main(argv=[sys.argv[0], *remaining])
