"""Game-free C++ library preflight checks (the Visual Studio route of nx2/make_game.py).

In a Visual Studio developer command prompt, or on Linux with any C++20 compiler:
    python -I -B tests/test_cpp_preflight.py --cxx clang++
Repeat --cxx-arg for target flags. The end-to-end case takes the Visual Studio route on any host.
The partial-library fixture is authored here; it is not a copy of an old vendor library.
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

RUN_ALL_ARGS = ["--cxx", "g++"]


# The override runs the same regression against the exact original production source.
SOURCE = Path(os.environ.get("HOOKSHOT_CPP_TEST_SOURCE", Path(__file__).resolve().parents[1] / "nx2" / "make_game.py"))
spec = importlib.util.spec_from_file_location("make_game_under_test", SOURCE)
make_game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_game)
COMPILER, COMPILER_FLAGS = None, []

OLD_FORMAT_PROBE = '\n'.join((
    "#include <format>", "#include <string>",
    'std::string t(int v) { return std::vformat("{}", std::make_format_args(v)); }', ""))


class Toolchain:
    def __init__(self, compiler, flags=()):
        self.compiler, self.flags = compiler, list(flags)

    def find(self, name):
        if name not in ("clang++", "clang"):   # (check_mingw asks for clang since PR 434)
            raise AssertionError("Unexpected tool requested: " + name)
        return self.compiler

    def need(self, path):
        return path

    def native_target(self):
        return list(self.flags)


class CppPreflightTests(unittest.TestCase):
    def setUp(self):
        if COMPILER is None:
            self.fail("Run this check as a script with --cxx (and, on Windows, a configured developer environment)")
        self.temporary = tempfile.TemporaryDirectory(prefix="hookshot-cpp-preflight-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.addCleanup(self.assert_owned_fixture)
        self.toolchain = Toolchain(COMPILER, COMPILER_FLAGS)

    def assert_owned_fixture(self):
        self.assertEqual(self.root.parent, Path(tempfile.gettempdir()).resolve())
        self.assertTrue(all(path.resolve().is_relative_to(self.root) for path in self.root.rglob("*")))

    def partial_library(self):
        partial = self.root / "partial-library"
        partial.mkdir()
        # Formatting is available, while range algorithms are not. The declarations
        # suffice for compile-only use, so no executable or vendor library is needed.
        headers = {
            "string": "#pragma once\nnamespace std { struct string {}; }\n",
            "format": ('#pragma once\n#include <string>\nnamespace std {\n'
                       'struct format_args {};\ntemplate<class T> format_args make_format_args(T&);\n'
                       'string vformat(const char*, format_args);\n}\n'),
            "algorithm": "#pragma once\nnamespace std::ranges {}\n",
            "vector": ('#pragma once\n#include <initializer_list>\nnamespace std {\n'
                       'template<class T> struct vector {\nvector(initializer_list<T>);\n'
                       'T* begin();\nT* end();\n};\n}\n'),
        }
        for name, text in headers.items():
            (partial / name).write_text(text, encoding="ascii")
        return Toolchain(COMPILER, [*COMPILER_FLAGS, "-I" + str(partial)])

    def test_supported_library_compiles_the_production_probe(self):
        make_game.check_cpp_library(self.toolchain)

    def test_ranges_gap_passes_old_probe_but_fails_production_preflight(self):
        toolchain = self.partial_library()
        source = self.root / "old-format-probe.cpp"
        source.write_text(OLD_FORMAT_PROBE, encoding="ascii")
        result = subprocess.run([toolchain.compiler, *toolchain.native_target(), "-std=c++20", "-c", str(source),
                                 "-o", str(self.root / "old-format-probe.o")],
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as stopped:
            make_game.check_cpp_library(toolchain)
        self.assertEqual(stopped.exception.code, 1)
        self.assertIn("ranges", output.getvalue())
        self.assertIn("Visual Studio 2022", output.getvalue())

    def test_failed_compiler_keeps_details_and_update_instructions(self):
        result = subprocess.CompletedProcess([], 1, "authored compiler output\n", "error: authored ranges failure\n")
        output = io.StringIO()
        with mock.patch.object(make_game.subprocess, "run", return_value=result) as compile_run, \
                contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as stopped:
            make_game.check_cpp_library(self.toolchain)
        self.assertEqual(stopped.exception.code, 1)
        compile_run.assert_called_once()
        self.assertIn("authored compiler output", output.getvalue())
        self.assertIn("authored ranges failure", output.getvalue())
        self.assertIn("@@error Your Visual Studio is too old", output.getvalue())
        self.assertIn("Visual Studio 2022", output.getvalue())

    def test_library_failure_stops_check_and_build_before_reading_input(self):
        for check_only in (True, False):
            with self.subTest(check_only=check_only), contextlib.ExitStack() as stack:
                output = io.StringIO()
                # Keep the real SDK/preflight call chain. Only the successful C probe
                # and compiler result are substituted; extraction/lifting cannot run.
                stack.enter_context(mock.patch.dict(sys.modules, {"toolchain": self.toolchain}))
                stack.enter_context(mock.patch.object(sys, "path", list(sys.path)))
                stack.enter_context(mock.patch.dict(os.environ, {"INCLUDE": "authored-ucrt"}))
                stack.enter_context(mock.patch.object(make_game, "compile_test",
                                                     return_value=subprocess.CompletedProcess([], 0, "", "")))
                compiler = stack.enter_context(mock.patch.object(make_game.subprocess, "run",
                    return_value=subprocess.CompletedProcess([], 1, "", "error: authored unsupported ranges\n")))
                launches = [
                    stack.enter_context(mock.patch.object(make_game.subprocess, "Popen",
                        side_effect=AssertionError("Unexpected process launch"))),
                    stack.enter_context(mock.patch.object(os, "system",
                        side_effect=AssertionError("Unexpected shell command"))),
                    stack.enter_context(mock.patch.object(os, "startfile", create=True,
                        side_effect=AssertionError("Unexpected file launch"))),
                ]
                run = stack.enter_context(mock.patch.object(make_game, "run",
                    side_effect=AssertionError("Input reading or translation reached")))
                stack.enter_context(mock.patch.object(make_game, "no_throttle"))
                # (the Visual Studio route on any host: on Linux check_windows_sdk asks for the system's clang, and
                # with llvm-mingw beside the builder it takes that one; this case is about Visual Studio's library)
                stack.enter_context(mock.patch.object(make_game, "LINUX", False))
                stack.enter_context(mock.patch.object(make_game, "bundled_mingw", return_value=""))
                stack.enter_context(mock.patch("ctypes.WinDLL", create=True))
                argv = ["make_game.py", "--nup", str(self.root / "missing-input.nup"),
                        "--out", str(self.root / "output"), "--work", str(self.root / "work")]
                if check_only:
                    argv.append("--check")
                stack.enter_context(mock.patch.object(sys, "argv", argv))
                stack.enter_context(contextlib.redirect_stdout(output))
                with self.assertRaises(SystemExit) as stopped:
                    make_game.main()
                self.assertEqual(stopped.exception.code, 1)
                self.assertIn("Visual Studio 2022", output.getvalue())
                compiler.assert_called_once()
                run.assert_not_called()
                for launch in launches:
                    launch.assert_not_called()
                self.assertFalse((self.root / "missing-input.nup").exists())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", required=True, help="C++ compiler with its normal library/SDK environment")
    parser.add_argument("--cxx-arg", action="append", default=[], help="extra compiler flag (repeatable)")
    args, remaining = parser.parse_known_args()
    # (a full path: the build's compiler check takes what toolchain.find() returns only when it is a file, so a bare
    # "g++" read as no compiler at all)
    COMPILER, COMPILER_FLAGS = shutil.which(args.cxx) or args.cxx, args.cxx_arg
    unittest.main(argv=[sys.argv[0], *remaining])
