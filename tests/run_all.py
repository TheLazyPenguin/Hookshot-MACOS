"""Every game-free check in one run: each tests/test_*.py and nx2/test_*.py in its own process, the C++ unit tests under
gpu/vk/tests and a byte-compile of every tracked Python file. All of them run even when one fails; the failures are
printed whole at the end, with a table of every check (slowest first), also to $GITHUB_STEP_SUMMARY when it is set.
Exits 1 when anything failed.

    python -I -B tests/run_all.py [--jobs N] [--timeout SECONDS] [--strict] [--no-skip] [name ...]

A name picks the checks whose path contains it. --strict: a check that needs a tool this PC lacks (a compiler, the
SPIR-V or Vulkan headers, spirv-val) fails instead of being skipped (CI installs them all). --no-skip runs the checks a
test skips on this OS too. Standard library only: no package is installed for the runner itself.

A test says what it needs in its own file, with up to three top-level assignments of plain literals (after its
docstring and imports). The runner reads them with ast and never imports the test; a test that declares none runs with
no arguments and its own defaults.

    RUN_ALL_ARGS = ["--cxx", "{cxx}", "--headers", "{vulkan_headers}"]   # its command-line arguments
    RUN_ALL_MODULES = ["zstandard"]                                       # Python packages it imports
    RUN_ALL_SKIP = {"windows": "needs spirv-val: checked on Linux"}       # OS ("linux", "windows") -> why it is skipped

{name} in an argument is a tool or folder find_tools looks for (cxx, vulkan_headers, spirv_headers, spirv_val, glslang,
dotnet); a check whose tool, compiler (the word after --cc or --cxx) or module is missing here is skipped, or fails
with --strict. A check skipped on both OSes (a GPU, the game) names both. A declaration that is not a plain literal of
that shape, names an unknown placeholder or OS, or any other RUN_ALL_ name, stops the run with the file and line; so
does one set or changed anywhere but its own top-level line (inside an if or a try, .append(...), +=, a subscript).
Only the tests a run picks (by name) are read: a bad declaration elsewhere does not stop it. A test that does not parse
fails, on every OS, without running.
"""
import argparse
import ast
import concurrent.futures
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOWS = os.name == "nt"
OS = "windows" if WINDOWS else "linux"

# What a check needs is declared in the test file itself, as top-level literals the runner reads with ast (the test is
# never imported): see the docstring above and read_declarations below.
DECLARATIONS = ("RUN_ALL_ARGS", "RUN_ALL_MODULES", "RUN_ALL_SKIP")
# (a list's or a dict's methods that change it in place: a declaration changed that way is not what the runner reads)
MUTATORS = {"append", "extend", "insert", "remove", "pop", "clear", "update", "setdefault", "popitem", "sort",
            "reverse", "__setitem__", "__delitem__", "__iadd__", "__ior__"}
OSES = ("linux", "windows")

# Retired: the central tables these declarations replaced. They stay, empty, so that an entry a branch from before the
# move adds here stops the run and says where it belongs, instead of being dropped without a word. Do not add to them.
ARGS = {}
MODULES = {}
SKIP = {}

def which(*names):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def header_dir(env, cpm_name, probe):
    """A headers folder: the environment variable, else the CPM cache nx2/build.py reads (RX_CPM, build-linux/deps/cpm)"""
    if os.environ.get(env):
        return os.environ[env]
    for cpm in (os.environ.get("RX_CPM"), os.path.join(ROOT, "build-linux", "deps", "cpm")):
        d = os.path.join(cpm or "", cpm_name)
        if cpm and os.path.isdir(d) and os.listdir(d):
            inc = os.path.join(d, sorted(os.listdir(d))[-1], "include")
            if os.path.exists(os.path.join(inc, probe)):
                return inc
    return None


def find_tools():
    return {
        "spirv_headers": header_dir("HOOKSHOT_SPIRV_HEADERS", "spirv-headers", os.path.join("spirv", "unified1", "spirv.h")),
        "vulkan_headers": header_dir("HOOKSHOT_VULKAN_HEADERS", "vulkanheaders", os.path.join("vulkan", "vulkan.h")),
        "spirv_val": which("spirv-val"),
        "glslang": which("glslangValidator", "glslang"),
        "dotnet": which("dotnet"),
        "cxx": which(os.environ.get("CXX", ""), "clang++", "g++", "c++"),
    }


class Check:
    def __init__(self, name, run, why_skip=None):
        self.name, self.run, self.why_skip = name, run, why_skip
        self.status, self.secs, self.output = "skip", 0.0, ""


class DeclarationError(Exception):
    pass


def read_declarations(path, rel, tools):
    """A test's RUN_ALL_ARGS, RUN_ALL_MODULES and RUN_ALL_SKIP (see the docstring), from its top-level assignments,
    checked against the placeholders in tools and the OSes in OSES. {"args": [...], "modules": [...], "skip": {os:
    why}}, empty where the test declares nothing. A file that does not parse declares nothing and says why in
    "unparsed" (its check fails with that, on every OS, without running); a bad declaration raises DeclarationError naming
    the file and line."""
    found = {"args": [], "modules": [], "skip": {}, "unparsed": None}
    with open(path, "rb") as f:
        source = f.read()
    try:
        tree = ast.parse(source, rel)
    except (SyntaxError, ValueError) as e:
        found["unparsed"] = "%s: does not parse (%s), so its RUN_ALL_ declarations cannot be read" % (rel, e)
        return found
    seen = set()

    def bad(node, what):
        return DeclarationError("%s:%d: %s" % (rel, node.lineno, what))

    def declared(node):
        return isinstance(node, ast.Name) and node.id.startswith("RUN_ALL_")
    # (at module level but not a top-level NAME = literal: inside an if or a try, a RUN_ALL_ARGS.append(...), a del. The
    # runner reads only the top level, so these would be ignored without a word. The top level's own forms are checked
    # below; a function's or a class's own names are not declarations and are left alone)
    top_targets = {id(n) for top in tree.body if isinstance(top, (ast.Assign, ast.AnnAssign, ast.AugAssign))
                   for t in (top.targets if isinstance(top, ast.Assign) else [top.target]) for n in ast.walk(t)}

    def module_level(node):
        yield node
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                yield from module_level(child)
    for node in module_level(tree):
        if id(node) in top_targets:
            continue
        if declared(node) and not isinstance(node.ctx, ast.Load):
            raise bad(node, "%s must be assigned at the top level of the file, as NAME = literal" % node.id)
        elif isinstance(node, (ast.Subscript, ast.Attribute)) and declared(node.value) \
                and not isinstance(node.ctx, ast.Load):
            raise bad(node, "%s must be assigned once, alone, as NAME = literal" % node.value.id)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and declared(node.func.value) \
                and node.func.attr in MUTATORS:
            raise bad(node, "%s is changed after it is set (.%s): write the whole literal in one assignment"
                      % (node.func.value.id, node.func.attr))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets, value = [node.target], node.value
        else:
            continue
        names = [n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name) and n.id.startswith("RUN_ALL_")]
        if not names:
            continue
        name = names[0]
        if name not in DECLARATIONS:
            raise bad(node, "%s is not a run_all.py declaration (%s)" % (name, ", ".join(DECLARATIONS)))
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or value is None or len(targets) != 1 \
                or not isinstance(targets[0], ast.Name):
            raise bad(node, "%s must be assigned once, alone, as NAME = literal" % name)
        if name in seen:
            raise bad(node, "%s is assigned twice" % name)
        seen.add(name)
        try:
            v = ast.literal_eval(value)
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
            raise bad(node, "%s must be a plain literal (no names, calls or expressions)" % name) from None
        if name == "RUN_ALL_SKIP":
            if not isinstance(v, dict) or not all(isinstance(k, str) and isinstance(w, str) and w.strip()
                                                  for k, w in v.items()):
                raise bad(node, 'RUN_ALL_SKIP must be a dict of OS -> reason, e.g. {"windows": "why"}')
            unknown = sorted(k for k in v if k not in OSES)
            if unknown:
                raise bad(node, "RUN_ALL_SKIP names an unknown OS %s (known: %s)" % (", ".join(map(repr, unknown)),
                                                                                    ", ".join(OSES)))
            found["skip"] = dict(v)
            continue
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise bad(node, "%s must be a list of strings" % name)
        if name == "RUN_ALL_ARGS":
            unknown = sorted({x.strip("{}") for x in v if x.startswith("{")} - set(tools))
            if unknown:
                raise bad(node, "RUN_ALL_ARGS names an unknown placeholder %s (known: %s)"
                          % (", ".join("{%s}" % u for u in unknown), ", ".join(sorted(tools))))
            found["args"] = list(v)
        else:
            found["modules"] = list(v)
    return found


def stale_tables():
    """Entries a branch from before the move still adds to the retired ARGS, MODULES or SKIP: what to declare instead"""
    out = []
    for table, decl in ((ARGS, "RUN_ALL_ARGS"), (MODULES, "RUN_ALL_MODULES"), (SKIP, "RUN_ALL_SKIP")):
        for rel, v in table.items():
            if decl == "RUN_ALL_SKIP" and isinstance(v, tuple) and len(v) == 2:
                v = {o: v[1] for o in sorted(v[0])}
            out.append("%s: declare it in the test: %s = %r" % (rel, decl, v))
    return out


def python_check(rel, decl, tools, timeout):
    args, missing = [], []
    for a in decl["args"]:
        if a.startswith("{"):
            v = tools.get(a.strip("{}"))
            if not v:
                missing.append(a.strip("{}"))
            args.append(v or "")
        else:
            args.append(a)
    # (a compiler named by the arguments, or the test's own default one, must be on PATH)
    for i, a in enumerate(args[:-1]):
        if a in ("--cc", "--cxx") and not which(args[i + 1]):
            missing.append(args[i + 1])
    missing += [m for m in decl["modules"] if importlib.util.find_spec(m) is None]

    def run():
        return subprocess.run([sys.executable, "-I", "-B", os.path.join(ROOT, rel)] + args, cwd=ROOT, timeout=timeout,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    return run, missing


def cpp_checks(tools, timeout):
    """gpu/vk/tests: the presentation rectangle (all of it), the lowering harness built and run over no programs
    (the programs it reads are dumped from the game, so here it only shows the lowering still compiles), and the
    lowering's register-marker regression"""
    cxx = tools["cxx"]
    out = []

    def build_and_run(src, flags, args):
        def run():
            with tempfile.TemporaryDirectory() as tmp:
                exe = os.path.join(tmp, "t.exe")
                r = subprocess.run([cxx, "-std=c++20", *flags, os.path.join(ROOT, src), "-o", exe], cwd=ROOT,
                                   timeout=timeout, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
                if r.returncode:
                    return r
                return subprocess.run([exe] + [a.replace("{tmp}", tmp) for a in args], cwd=ROOT, timeout=timeout,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        return run
    rect = "gpu/vk/tests/present_rect_test.cpp"
    out.append((rect, build_and_run(rect, ["-Wall", "-Wextra", "-Werror"], [])))
    lower = "gpu/vk/tests/lower_test.cpp"
    eden, compat = os.path.join(ROOT, "gpu", "vk", "eden"), os.path.join(ROOT, "gpu", "vk", "compat")
    out.append((lower, build_and_run(lower, ["-O1", "-Wno-everything", "-I" + eden, "-I" + compat], ["{tmp}"])))
    regmap = "gpu/vk/tests/regmap_marker_test.cpp"   # (the lowering's renamed-register markers: no number mapped twice)
    out.append((regmap, build_and_run(regmap, ["-O1", "-Wno-everything", "-I" + eden, "-I" + compat], [])))
    return out, ([] if cxx else ["a C++ compiler"])


class Result:
    def __init__(self, returncode, stdout):
        self.returncode, self.stdout = returncode, stdout


def compile_all():
    """Every tracked .py file byte-compiled (in memory: nothing written), so a syntax error anywhere fails"""
    r = subprocess.run(["git", "ls-files", "-z", "--", "*.py"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode:
        return Result(r.returncode, r.stdout)
    files = [f for f in r.stdout.decode("utf-8").split("\0") if f]
    bad = []
    for f in files:
        try:
            with open(os.path.join(ROOT, f), "rb") as src:
                compile(src.read(), f, "exec", dont_inherit=True)
        except (SyntaxError, ValueError) as e:
            bad.append("%s: %s" % (f, e))
    text = "%d files byte-compiled\n" % len(files) + "".join(b + "\n" for b in bad)
    return Result(1 if bad else 0, text.encode())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("names", nargs="*")
    p.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    p.add_argument("--timeout", type=int, default=600, help="seconds per check (default 600)")
    p.add_argument("--strict", action="store_true", help="a missing tool fails the check instead of skipping it")
    p.add_argument("--no-skip", action="store_true", help="also run the checks on the skip list")
    a = p.parse_args()
    tools = find_tools()

    checks = []
    tests = sorted(d + "/" + f for d in ("tests", "nx2") for f in os.listdir(os.path.join(ROOT, d))
                   if f.startswith("test_") and f.endswith(".py"))
    stale = stale_tables()
    if stale:
        print("tests/run_all.py: ARGS, MODULES and SKIP are retired: each test declares what it needs in its own file"
              " (see the docstring at the top of tests/run_all.py)", file=sys.stderr)
        for line in stale:
            print("  " + line, file=sys.stderr)
        return 2
    # (only the tests asked for: a bad declaration elsewhere does not stop a run of one named test)
    if a.names:
        tests = [rel for rel in tests if any(n in rel for n in a.names)]
    decls, errors = {}, []
    for rel in tests:
        try:
            decls[rel] = read_declarations(os.path.join(ROOT, rel), rel, tools)
        except DeclarationError as e:
            errors.append(str(e))
    if errors:
        print("tests/run_all.py: bad declarations, nothing run:", file=sys.stderr)
        for e in errors:
            print("  " + e, file=sys.stderr)
        return 2
    for rel in tests:
        reason = decls[rel]["skip"].get(OS)
        run, missing = python_check(rel, decls[rel], tools, a.timeout)
        c = Check(rel, run)
        if decls[rel]["unparsed"]:   # (no skip to read: the same failure on every OS, not run)
            c.run = lambda why=decls[rel]["unparsed"]: Result(1, (why + "\n").encode())
        elif reason and not a.no_skip and not any(n in rel for n in a.names):
            c.why_skip = reason
        elif missing and not a.strict:
            c.why_skip = "not found here: " + ", ".join(missing)
        elif missing:
            c.run = lambda m=missing: Result(1, ("not found: %s (--strict)\n" % ", ".join(m)).encode())
        checks.append(c)
    cpp, missing = cpp_checks(tools, a.timeout)
    for name, run in cpp:
        c = Check(name, run)
        if missing:
            c.why_skip = "not found here: " + ", ".join(missing)
            if a.strict:
                c.why_skip = None
                c.run = lambda m=missing: Result(1, ("not found: %s (--strict)\n" % ", ".join(m)).encode())
        checks.append(c)
    checks.append(Check("(byte-compile every tracked .py)", compile_all))
    if a.names:
        checks = [c for c in checks if any(n in c.name for n in a.names)]

    def one(c):
        t = time.time()
        try:
            r = c.run()
            c.status = "pass" if r.returncode == 0 else "FAIL"
            c.output = r.stdout.decode("utf-8", "replace")
        except subprocess.TimeoutExpired as e:
            c.status = "TIMEOUT"
            c.output = (e.stdout or b"").decode("utf-8", "replace") + "\n(stopped after %d s)\n" % e.timeout
        except Exception as e:   # (a check that could not even start is a failure, not a crash of the runner)
            c.status = "FAIL"
            c.output = "%s: %s\n" % (type(e).__name__, e)
        c.secs = time.time() - t
        return c

    to_run = [c for c in checks if not c.why_skip]
    t0 = time.time()
    print("%d checks, %d skipped, %d at once (%s)" % (len(to_run), len(checks) - len(to_run), a.jobs, OS), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max(1, a.jobs)) as ex:
        for c in concurrent.futures.as_completed([ex.submit(one, c) for c in to_run]):
            c = c.result()
            print("%-7s %6.1fs  %s" % (c.status, c.secs, c.name), flush=True)
    wall = time.time() - t0

    failed = [c for c in to_run if c.status != "pass"]
    gh = os.environ.get("GITHUB_ACTIONS") == "true"
    for c in failed:
        print(("::group::" if gh else "\n==== ") + "%s %s" % (c.status, c.name), flush=True)
        print(c.output.rstrip())
        if gh:
            print("::endgroup::")
            print("::error title=%s %s::see the step's log for its output" % (c.status, c.name))

    order = sorted(to_run, key=lambda c: -c.secs) + sorted((c for c in checks if c.why_skip), key=lambda c: c.name)
    passed = sum(c.status == "pass" for c in to_run)
    head = "%d passed, %d failed, %d skipped in %.0f s (%s, %d at once)" % (passed, len(failed), len(checks) - len(to_run),
                                                                         wall, OS, a.jobs)
    print("\n%-8s %8s  %s" % ("result", "time", "check"))
    for c in order:
        print("%-8s %8s  %s%s" % (c.status, "" if c.why_skip else "%.1fs" % c.secs, c.name,
                                  "  (%s)" % c.why_skip if c.why_skip else ""))
    print(head, flush=True)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        mark = {"pass": "pass", "FAIL": "**FAIL**", "TIMEOUT": "**TIMEOUT**", "skip": "skip"}
        lines = ["### Tests (%s): %s" % (OS, head), "", "| Result | Time | Check | Note |", "|---|---:|---|---|"]
        for c in order:
            note = c.why_skip or ""
            if c.status in ("FAIL", "TIMEOUT"):
                last = [l for l in c.output.strip().splitlines() if l.strip()][-1:] or [""]
                note = "`%s`" % last[0].replace("|", "\\|").replace("`", "'")[:160]
            lines.append("| %s | %s | `%s` | %s |" % (mark[c.status], "" if c.why_skip else "%.1f s" % c.secs, c.name, note))
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
