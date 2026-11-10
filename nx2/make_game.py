"""A game folder from the user's own dump: what the builder app (builder/) runs.

    python -I nx2/make_game.py --nup <file.nup> --out <folder> [--work <folder>] [--jobs <n>]
    python -I nx2/make_game.py --romfs <dir> --exefs <dir> --out <folder> [--work <folder>] [--jobs <n>]
    python -I nx2/make_game.py --check --nup <file.nup>       (or --exefs <dir>: is this the right game and version?)
    python -I nx2/make_game.py --update <folder>             (a folder built before, again with these tools: the game files it keeps)
    python -I nx2/make_game.py --game <.nup or folder> --prepare   (RecompLauncher: --out defaults to ~/Games/Hookshot; no window,
                                                                    "progress <0..1> <text>" lines and an "error <text>" line on stdout,
                                                                    exit 0 when the game is built; with --check, its "check ok|bad" line)

The folder holds the executable and all it needs, started with a double click: nothing goes back into the repository, and no game
data ever comes with the tools. Lines the app reads, each on its own line of stdout:

    @@stage <id> <text>      a step begins
    @@progress <0..1>        how far that step is
    @@plan <changed> <total> how many files the compile rebuilds, of all of them
    @@file <name> <seconds> <new|cached|again>   one module's build
    @@eta <seconds>          the compile's time left, from what the earlier builds measured on this PC
    @@times <total> <compile> <previous|-1>      finished: this build's times beside the last one's
    @@check <ok|bad> <text>  (--check) the answer
    @@done <folder>          finished
    @@error <text>           stopped

and one plain line the builders also read (older ones only show it): "the shaders were not prepared now (<why>): ..." when the
build's last step, the shaders' preparation, was skipped or failed and is left to the game's first start (NOT_PREPARED)
"""
import argparse
import contextlib
import filecmp
import hashlib
import importlib.util
import json
import os
import queue
import re
import shutil
import stat
import subprocess
import threading
import time
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = [sys.executable, "-I", "-u", "-X", "utf8"]   # (utf8: every step's output in UTF-8 whatever the console's code page: lift.py crashed on a letter, #180)   # (-u: the steps' output as it comes, not in 8 KB blocks minutes apart)
BUILD_ID = "e0f3ccfa"   # (the version the patches, the hot list and the profile were made from)
STARTED = time.time()   # (the build's total time, kept in build_times.json and said as @@times)
sys.path[:0] = [HERE, os.path.join(ROOT, "third_party", "a64-kit", "tools")]   # (python -I leaves the script folder off)
import disk as _disk
import toolchain as _toolchain
DARWIN = getattr(_toolchain, "darwin", lambda: sys.platform == "darwin")()
WINDOWS = _toolchain.windows()
LINUX = not WINDOWS and not DARWIN
CROSS = WINDOWS and os.name != "nt"
# (SDL2.dll is sdl2-compat: it loads SDL3.dll from beside the exe. Left out of bin\ since v2.0.0, it said "Failed loading SDL3
# library" three times and no controller worked: Discord #bug-reporting, 11-08)
if DARWIN:
    BESIDE = ["hookshot", "hookshot_vk.dylib", "hookshot_metal.dylib"]
elif LINUX:
    BESIDE = ["hookshot", "hookshot_vk.so", "libSDL2-2.0.so.0"]
else:
    BESIDE = ["hookshot.exe", "hookshot_vk.dll", "SDL2.dll", "SDL3.dll", "wgpu_native.dll"]
LANGUAGES = [("en-US", "English (US)"), ("en-GB", "English (UK)"), ("fr", "French (France)"), ("fr-CA", "French (Canada)"), ("de", "German"),
             ("it", "Italian"), ("es", "Spanish (Spain)"), ("es-419", "Spanish (Latin America)"), ("pt-BR", "Portuguese (Brazil)"), ("nl", "Dutch"),
             ("pl", "Polish"), ("ru", "Russian"), ("ja", "Japanese"), ("ko", "Korean"), ("zh-Hans", "Chinese (Simplified)"),
             ("zh-Hant", "Chinese (Traditional)")]


def no_throttle(handle=None):
    """(issue 87) Windows' power throttling (EcoQoS) slows a background window's processes to almost nothing on some machines: the
    build sat at 0% CPU. Turned off for this process, or the one whose handle this is"""
    if os.name != "nt":
        return
    import ctypes
    class State(ctypes.Structure):
        _fields_ = [("Version", ctypes.c_ulong), ("ControlMask", ctypes.c_ulong), ("StateMask", ctypes.c_ulong)]
    k = ctypes.WinDLL("kernel32")
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.SetProcessInformation.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong]
    s = State(1, 1, 0)   # (PROCESS_POWER_THROTTLING_EXECUTION_SPEED in the mask, off in the state)
    try:
        k.SetProcessInformation(ctypes.c_void_p(int(handle)) if handle else k.GetCurrentProcess(), 4, ctypes.byref(s), ctypes.sizeof(s))
    except (OSError, ValueError, TypeError):
        pass


PREPARE = False   # (--prepare) say() prints RecompLauncher's "progress <0..1> <text>" lines instead of the builder app's @@ lines
STAGE_SPAN = {"read": (0.0, 0.05), "lift": (0.05, 0.25), "compile": (0.25, 0.95), "finish": (0.95, 1.0)}   # (a share of the whole each stage takes)
_stage = {"span": (0.0, 1.0), "text": ""}


def say_prepare(words):
    if words[0] == "stage" and len(words) > 2:
        _stage["span"], _stage["text"] = STAGE_SPAN.get(words[1], _stage["span"]), " ".join(words[2:])
        print("progress %.3f %s" % (_stage["span"][0], _stage["text"]), flush=True)
    elif words[0] == "progress" and len(words) > 1:
        lo, hi = _stage["span"]
        print("progress %.3f %s" % (lo + (hi - lo) * float(words[1]), _stage["text"]), flush=True)
    elif words[0] in ("error", "check"):   # (on stdout, the only stream a launcher reads; HookshotBuilder --cli also takes its "error" line)
        print(" ".join(words), flush=True)
    elif words[0] == "done":
        print("progress 1.000 Done", flush=True)


def say(*words):
    if PREPARE:
        return say_prepare([str(w) for w in words])
    print("@@" + " ".join(str(w) for w in words), flush=True)


def check_writable(out):
    """The game folder must take new files before anything is read into it. A folder under Program Files (or another protected
    place) only takes them with administrator rights, and the build used to stop minutes later inside nup.py with a bare
    "PermissionError: [WinError 5]" on its .game folder"""
    probe = os.path.join(out, ".hookshot_write_check")
    try:
        os.makedirs(out, exist_ok=True)
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
    except PermissionError as e:
        protected = [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "SystemRoot")]
        inside = any(d and os.path.normcase(os.path.abspath(out)).startswith(os.path.normcase(os.path.abspath(d)) + os.sep)
                     for d in protected)
        where = (" Windows protects folders under Program Files and Windows, and only lets administrators write there."
                 if inside else "")
        example = "~/Games/Hookshot" if LINUX else r"C:\Games\Hookshot"
        fail("The game folder %s can't be written to (%s).%s In Hookshot Builder, choose a game folder of your own, for example "
             "%s, and build again." % (out, e.strerror or e, where, example))


def fail(text):
    say("error", text)
    sys.exit(1)


def failure_reason(lines):
    """The line a stopped step is named with. Only the last 12 lines used to be kept, so a compiler's "error:" hundreds
    of lines earlier was replaced by "compiled in 790s, 1 failed"."""
    tail, seen = [], None
    for line in lines:
        tail = (tail + [line])[-12:]
        if "error:" in line.lower() and "CalledProcessError" not in line:
            seen = line
    if seen is not None:
        return seen
    return tail[-1] if tail else "no output"


def killed_reason():
    """(issues 478, 768, 807) A step stopped by SIGKILL or SIGTERM from outside the build: the builder's own Cancel stops make_game
    with it, so this is the system's, the kernel's or a desktop's low-memory killer most likely. Its last lines then said nothing
    of that (the lift's emit processes failing on their result pipe, BrokenPipeError, or the lift's last progress line)"""
    total = None
    try:
        with open("/proc/meminfo") as f:
            total = next((round(int(l.split()[1]) / (1 << 20)) for l in f if l.startswith("MemTotal:")), None)   # (kB, to the nearest GB)
    except (OSError, ValueError, IndexError):
        pass
    return ("the system stopped it, most likely because the PC ran out of memory%s. Close other programs and build again"
            % (" (%d GB here)" % total if total else ""))


def reported(line):
    """The sentence a builder shows. @@check is '@@check <ok|bad> <text>'; @@error is '@@error <text>'. None otherwise."""
    if line.startswith("@@error "):
        return line[len("@@error "):]
    if line.startswith("@@check "):
        parts = line.split(" ", 2)
        return parts[2] if len(parts) == 3 else ""
    return None


class LogStream:
    """Keep console output live while also saving it to the build log."""
    def __init__(self, console, log):
        self.console, self.log = console, log

    def write(self, text):
        result = self.console.write(text)
        self.log.write(text)
        self.flush()
        return result

    def flush(self):
        self.console.flush()
        self.log.flush()

    def __getattr__(self, name):
        return getattr(self.console, name)


@contextlib.contextmanager
def build_log(path):
    if path is None:
        yield
        return
    try:
        log = open(path, "w", encoding="utf-8", newline="\n")
    except OSError as e:
        fail("Could not open build log %s: %s" % (path, e))
    with log:
        with contextlib.redirect_stdout(LogStream(sys.stdout, log)), contextlib.redirect_stderr(LogStream(sys.stderr, log)):
            yield


TIMES_FORMAT = 1
KEEP_BUILDS = 20


def times_path(work):
    """Where the builds' times are kept: beside the object cache, in the builder's own folder (LOCALAPPDATA\\HookshotBuilder
    on Windows, ~/.cache/hookshot-builder on Linux). A builder update keeps it, so the next build still knows what this PC
    took, and the one after that can compare."""
    return os.path.join(work, "build_times.json")


def load_times(work):
    """The seconds each module took on this PC, and the last builds' totals; a fresh record when there is none to trust
    (missing, half written, or written by another version of the tools)."""
    data = {"format": TIMES_FORMAT, "builds": [], "seconds": {}}
    try:
        with open(times_path(work), encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        return data
    if not isinstance(old, dict) or old.get("format") != TIMES_FORMAT:
        return data
    builds = old.get("builds")
    if isinstance(builds, list):
        data["builds"] = [b for b in builds
                          if isinstance(b, dict) and isinstance(b.get("total_seconds"), (int, float))][-KEEP_BUILDS:]
    seconds = old.get("seconds")
    if isinstance(seconds, dict):
        data["seconds"] = {str(k): float(v) for k, v in seconds.items()
                           if isinstance(v, (int, float)) and not isinstance(v, bool)}
    return data


def save_times(work, data):
    """The whole file at once: a build stopped while writing it leaves the last record in place."""
    path = times_path(work)
    try:
        os.makedirs(work, exist_ok=True)
        with open(path + ".new", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True)
            f.write("\n")
        os.replace(path + ".new", path)
    except OSError as e:
        print("the build times were not saved (%s)" % e, flush=True)


def record_times(work, files, compile_seconds, total_seconds, modules=0, kind="build"):
    """This build in the record: what each module it compiled took (a module a cache already held keeps the time it took
    before), the compile's and the whole build's seconds. Returns the last build's total, to show beside this one."""
    data = load_times(work)
    previous = data["builds"][-1]["total_seconds"] if data["builds"] else None
    data["seconds"].update({str(k): round(float(v), 1) for k, v in files.items() if v > 0})
    data["builds"].append({"when": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, "modules": int(modules),
                           "compiled": len(files), "compile_seconds": round(compile_seconds, 1),
                           "total_seconds": round(total_seconds, 1)})
    data["builds"] = data["builds"][-KEEP_BUILDS:]
    save_times(work, data)
    return previous


def clock(seconds):
    """A length of time the way the build's lines say it: '1:02:03'"""
    s = int(round(seconds))
    return "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60)


class Silent(Exception):
    """a step printed nothing for longer than run()'s silence"""


def output_lines(p, silence):
    """A step's lines as they come; with silence (seconds), read on a thread so that a step which goes quiet that long (a hung
    driver, a crash dialog left open) raises Silent instead of waiting for ever"""
    if silence is None:
        yield from p.stdout
        return
    lines = queue.Queue()

    def read():
        try:
            for line in p.stdout:
                lines.put(line)
        except (OSError, ValueError):
            pass
        finally:
            with contextlib.suppress(OSError, ValueError):
                p.stdout.close()   # (here, not by run(): a stopped step's pipe may still be read by this thread)
            lines.put(None)

    threading.Thread(target=read, daemon=True).start()
    while True:
        try:
            line = lines.get(timeout=silence)
        except queue.Empty:
            raise Silent() from None
        if line is None:
            return
        yield line


def run(cmd, env=None, on_line=None, check=True, output=None, show=None, cwd=ROOT, base=None, silence=None):
    """A step, its output printed as it comes. show: what of each line is printed (its None: nothing; on_line and a failure's
    reason still get the line itself). base: the environment it starts from (os.environ). silence: seconds without a line after
    which the step is stopped; it returns None then (with check, the build fails)"""
    e = dict(os.environ if base is None else base, PYTHONIOENCODING="utf-8")
    e.update(env or {})
    p = subprocess.Popen(cmd, cwd=cwd, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                         errors="replace", bufsize=1)
    no_throttle(getattr(p, "_handle", None))
    lines = []
    try:
        for line in output_lines(p, silence):
            line = line.rstrip()
            shown = show(line) if show else line
            if shown is not None:
                print(shown, file=output, flush=True)
            lines.append(line)
            if on_line:
                on_line(line)
    except Silent:
        p.kill()
        p.wait()
        if check:
            fail("%s printed nothing for %s and was stopped" % (os.path.basename(cmd[0]), span(silence)))
        return None
    p.stdout.close()
    code = p.wait()
    if code and check:
        step = next((os.path.basename(c) for c in cmd[1:] if c.endswith(".py")), os.path.basename(cmd[-1]))   # (issue 154: not "-u")
        status = "signal %d" % -code if os.name == "posix" and code < 0 else "exit status %d" % code
        fail("%s stopped (%s): %s" % (step, status, killed_reason() if os.name == "posix" and -code in (9, 15) else failure_reason(lines)))
    return code


def build_id(main):
    """the module id of an NSO, plain or compressed: the header is the same"""
    with open(main, "rb") as f:
        head = f.read(0x60)
    if head[:4] != b"NSO0":
        fail("%s is not a game executable" % main)
    return head[0x40:0x60].hex()


def check_modules(exefs):
    """Every module of the exefs is one the tools can read: said here, not as a Python error from the translator"""
    for name in os.listdir(exefs):
        if name != "main.npdm" and not name.endswith(".part"):
            with open(os.path.join(exefs, name), "rb") as f:
                head = f.read(16)
            if head[:4] != b"NSO0":
                fail("The file %s in this dump is not a game module (it starts %s). Try another dump of the game, or send this message to the "
                     "Hookshot developers." % (name, head.hex()))


def check_supported_build(exefs):
    bid = build_id(os.path.join(exefs, "main"))
    if not bid.startswith(BUILD_ID):
        fail("This is build %s. Hookshot supports build %s." % (bid[:8], BUILD_ID))


def file_progress(verb, clock=time.monotonic):
    """A progress(done, total) for a long pass over many files: "@@progress" for the builder's bar of the step it is in, at most
    4 times a second and at the end, and a plain line at each tenth ("checked 40,000 of 102,185 files (40%, 51 s)"), so a log or a
    terminal shows it moving too"""
    start = clock()
    last = [None, 0]   # (when the last @@progress went out; the last tenth said)
    def progress(done, total):
        now = clock()
        if last[0] is None or now - last[0] >= 0.25 or done >= total:
            last[0] = now
            print("@@progress %.3f" % (done / total if total else 1.0), flush=True)
        tenth = done * 10 // total if total else 10
        if tenth > last[1]:
            last[1] = tenth
            print("%s %s of %s files (%d%%, %d s)" % (verb, format(done, ","), format(total, ","), tenth * 10, now - start),
                  flush=True)
    return progress


HEADS = ".hookshot_romfs_heads"   # (the extraction's damaged .zs list, under the stamp of the unpack that made it)


def keep_heads(out, game, stamp):
    """nup.py's list of the romfs .zs files that do not start as zstd (its HEADS_NAME, beside the extracted romfs), kept in the
    game folder under this unpack's stamp for stand_in_damaged_files: the ~100,000 files are then not opened again"""
    import nup
    made = os.path.join(game, nup.HEADS_NAME)
    with contextlib.suppress(FileNotFoundError):
        os.remove(os.path.join(out, HEADS))
    if nup.read_heads(made) is None:
        return
    with open(made, encoding="utf-8") as f:
        listed = f.read().partition("\n")[2]
    with open(os.path.join(out, HEADS), "w", encoding="utf-8", newline="\n") as f:
        f.write(stamp.strip() + "\n" + listed)


def stand_in_damaged_files(out, romfs):
    """An incomplete dump's damaged textures replaced by whole ones of the same kind, and said: without them the game
    leaves out the walls and floors that use them (the Water Temple, #1002). Only in a romfs this builder unpacked (its
    .hookshot_romfs stamp), and once per unpack: .hookshot_romfs_checked holds the stamp it was checked under"""
    good = os.path.join(out, ".hookshot_romfs")
    checked = os.path.join(out, ".hookshot_romfs_checked")
    if not os.path.isfile(good) or not os.path.isdir(romfs):
        return
    check_cache_paths(out, (good, checked, romfs))
    with open(good) as f:
        stamp = f.read()
    if os.path.isfile(checked):
        with open(checked) as f:
            if f.read() == stamp:
                return
    import nup
    heads = os.path.join(out, HEADS)
    known = None
    try:
        with open(heads, encoding="utf-8") as f:
            first, _, rest = f.read().partition("\n")
        if first == stamp.strip():   # (made by this unpack's extraction: nup.py HEADS_NAME)
            known = nup.read_heads_text(rest)
    except OSError:
        pass
    if known is None:
        print("checking your game files for damaged textures (once after an unpack): every .zs file is opened, which can take "
              "minutes", flush=True)
        done = nup.stand_in_damaged(romfs, file_progress("checked"))
    else:   # (found while the .nup was extracted: no file opened again)
        done = nup.stand_in_damaged(romfs, damaged=[os.path.normpath(os.path.join(romfs, rel)) for rel in known])
    with open(checked, "w") as f:
        f.write(stamp)
    with contextlib.suppress(FileNotFoundError):
        os.remove(heads)
    if not done:
        return
    print("Your game dump is incomplete: %d game file%s in it %s damaged (a complete dump is about 23.8 GB, an incomplete "
          "one 23.3 GB). Each is replaced by a similar file so that the places using it are still drawn, with a different "
          "texture there. Dump the game again for the original look:" % (len(done), "" if len(done) == 1 else "s",
                                                                          "is" if len(done) == 1 else "are"), flush=True)
    for path, other in done:
        print("  %s: %s" % (os.path.relpath(path, romfs),
                            "in its place " + os.path.basename(other) if other else "nothing similar found, left as it is"),
              flush=True)


def check_cache_paths(out, paths):
    """Resolve generated paths and reject symbolic links/reparse points before replacement."""
    root = os.path.realpath(out)
    for path in paths:
        try:
            inside = os.path.commonpath((root, os.path.realpath(path))) == root
        except ValueError:
            inside = False
        attrs = os.lstat(path) if os.path.lexists(path) else None
        linked = os.path.islink(path) or bool(
            getattr(attrs, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
        if not inside or linked:
            fail("The generated cache path %s is not a normal path inside the build folder (symbolic links and reparse points are not supported). "
                 "Choose a different output folder." % path)


def check_cpu():
    """(linux) The AppImage's Vulkan back end (HOOKSHOT_VK_PREBUILT) is built for x86-64-v3 elsewhere
    (scripts/linux/appimage.sh), while the game follows this PC (nx2/host_cpu.py): on a CPU without AVX2 it would stop at
    its start. Said now, before the game is read, not 40 minutes in (issue 363)"""
    if not os.environ.get("HOOKSHOT_VK_PREBUILT") or os.environ.get("RX_MARCH"):
        return
    sys.path.insert(0, HERE)
    from host_cpu import host_march
    m = host_march()
    if m != "x86-64-v3":
        fail("Your processor has no AVX2 (it runs %s), and the AppImage's renderer needs it. Build Hookshot from source "
             "instead (see the readme): a source build follows your processor." % m)


def check(a, work):
    check_windows_sdk()   # (first: said in plain words when the game is chosen, not after it has been read)
    check_cpu()
    if a.nup:
        probe = os.path.join(work, "probe")
        shutil.rmtree(probe, ignore_errors=True)
        run(PY + ["nx2/nup.py", a.nup, "--extract", probe, "--only", "exefs"])
        check_modules(os.path.join(probe, "exefs"))
        bid = build_id(os.path.join(probe, "exefs", "main"))
        shutil.rmtree(probe, ignore_errors=True)
    else:
        bid = build_id(os.path.join(a.exefs, "main"))
    if bid.startswith(BUILD_ID):
        say("check", "ok", "This is the version Hookshot supports (build %s)." % bid[:8])
    else:
        say("check", "bad", "This is build %s. Hookshot supports build %s." % (bid[:8], BUILD_ID))


def visual_studio_environment():
    """What Visual Studio's own vcvars64.bat sets, for a compiler that does not find it by itself; None without one"""
    vswhere = os.path.join(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"), "Microsoft Visual Studio", "Installer", "vswhere.exe")
    if not os.path.exists(vswhere):
        return None
    r = subprocess.run([vswhere, "-latest", "-prerelease", "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                        "-property", "installationPath"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    lines = r.stdout.strip().splitlines()
    if not lines:
        return None
    bat = os.path.join(lines[-1], "VC", "Auxiliary", "Build", "vcvars64.bat")
    if not os.path.exists(bat):
        return None
    r = subprocess.run('"%s" >nul && set' % bat, shell=True, capture_output=True, text=True, encoding="mbcs", errors="replace")
    keep = ("INCLUDE", "LIB", "LIBPATH", "PATH", "VCINSTALLDIR", "VCTOOLSINSTALLDIR", "VCTOOLSVERSION", "WINDOWSSDKDIR", "WINDOWSSDKVERSION",
            "UCRTVERSION", "UNIVERSALCRTSDKDIR")
    found = {}
    for line in r.stdout.splitlines():
        name, eq, value = line.partition("=")
        if eq and name.upper() in keep:
            found[name] = value
    return found if any(k.upper() == "INCLUDE" for k in found) else None


def windows_kits_environment(base):
    """INCLUDE and LIB with the Windows SDK's C library (ucrt) and headers added from where its installer puts them: Visual Studio's
    vcvars leaves them out when the SDK came apart from it (issue 89: 'stdio.h' file not found with MSVC installed). None without one"""
    kits = os.path.join(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"), "Windows Kits", "10")
    inc = os.path.join(kits, "Include")
    try:
        versions = sorted((v for v in os.listdir(inc) if os.path.exists(os.path.join(inc, v, "ucrt", "stdio.h"))),
                          key=lambda v: [int(x) if x.isdigit() else 0 for x in v.split(".")])
    except OSError:
        return None
    if not versions:
        return None
    v = versions[-1]
    env = dict(base or {})
    get = lambda k: next((env[n] for n in env if n.upper() == k), os.environ.get(k, ""))
    env["INCLUDE"] = ";".join(x for x in [get("INCLUDE")] + [os.path.join(inc, v, d) for d in ("ucrt", "um", "shared", "winrt")] if x)
    env["LIB"] = ";".join(x for x in [get("LIB")] + [os.path.join(kits, "Lib", v, d, "x64") for d in ("ucrt", "um")] if x)
    print("the Windows SDK %s from %s" % (v, kits), flush=True)
    return env


def compile_test(toolchain):
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "t.c")
        with open(src, "w") as f:
            # (_UCRT: the C library of Visual Studio 2015 and later. An older one's stdio.h compiled, and the link failed 40 minutes later
            # on __iob_func: issue 80)
            f.write(chr(10).join(("#include <stdio.h>", "#ifndef _UCRT", "#error \"stdio.h is from an old C library (before Visual Studio 2015)\"",
                                  "#endif", "#include <windows.h>", "int main(void) { return 0; }", "")))
        return subprocess.run([toolchain.need(toolchain.find("clang"))] + toolchain.native_target() + ["-c", src, "-o", os.path.join(d, "t.o")],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")


def link_test(toolchain):
    """A program links, not only compiles (issue 439: a default library a recent Windows SDK no longer ships stopped the
    build at 99%, after the game had been read and translated)"""
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "t.c")
        with open(src, "w") as f:
            f.write(chr(10).join(("#include <stdio.h>", "int main(void) { return 0; }", "")))
        return subprocess.run([toolchain.need(toolchain.find("clang"))] + toolchain.native_target() + toolchain.native_link() +
                              [src, "-o", os.path.join(d, "t.exe")], capture_output=True, text=True, encoding="utf-8", errors="replace")


def check_cpp_library(toolchain):
    """Check the renderer's C++20 library features before the long build (issues 39 and 100)."""
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "t.cpp")
        with open(src, "w") as f:
            # Projected find: frontend/maxwell/structured_control_flow.cpp; predicate find and
            # comparator sort: ir_opt/texture_pass.cpp (under gpu/vk/eden/shader_recompiler).
            f.write(chr(10).join(("#include <algorithm>", "#include <format>", "#include <string>", "#include <vector>",
                                  "std::string t(int v) { return std::vformat(\"{}\", std::make_format_args(v)); }",
                                  "namespace { struct Entry { int value; }; }",
                                  "bool ranges_test() {",
                                  "    std::vector<Entry> entries{{2}, {1}};",
                                  "    const auto found = std::ranges::find(entries, 1, &Entry::value);",
                                  "    const auto matching = std::ranges::find_if(entries, [](const Entry& e) { return e.value == 2; });",
                                  "    std::ranges::sort(entries, [](const Entry& a, const Entry& b) { return a.value < b.value; });",
                                  "    return found != entries.end() && matching != entries.end();",
                                  "}", "")))
        r = subprocess.run([toolchain.need(toolchain.find("clang++"))] + toolchain.native_target() + ["-std=c++20", "-c", src, "-o", os.path.join(d, "t.o")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        print(r.stdout + r.stderr, flush=True)
        fail("Your Visual Studio is too old for this game's renderer. Open the Visual Studio Installer, press Update on "
             "Visual Studio 2022 (or install it), then build again.")


def check_linux_compiler():
    """(linux/darwin) A C compiler that builds and links a program here: found now, not 40 minutes in"""
    sys.path.insert(0, os.path.join(ROOT, "third_party", "a64-kit", "tools"))
    import toolchain
    cc = toolchain.find("clang")
    if not os.path.isfile(cc):
        fail("No C compiler was found. Install clang (and lld on Linux, or Xcode Command Line Tools on macOS).")
    sysroot = os.environ.get("HOOKSHOT_SYSROOT")
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "t.c")
        with open(src, "w") as f:
            f.write(chr(10).join(("#include <stdio.h>", "#include <pthread.h>", "int main(void) { return 0; }", "")))
        cmd = [cc] + toolchain.native_target() + (["--sysroot=" + sysroot] if sysroot else []) + \
              (["-fuse-ld=lld"] if not toolchain.darwin() else []) + [src, "-o", os.path.join(d, "t")]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        print(r.stdout + r.stderr, flush=True)
        errors = [l for l in r.stderr.splitlines() if "error" in l]
        fail("The compiler could not build a test program: %s" % (errors[0] if errors else "no message"))


def requested_jobs(value):
    """The builder's explicit worker override, or None to keep its automatic selection."""
    if value is None or value == "":
        return None
    error = "HOOKSHOT_JOBS must be a whole number: use 1 or more, or 0 for automatic."
    try:
        jobs = int(value)
    except ValueError:
        raise ValueError(error) from None
    if jobs < 0:
        raise ValueError(error)
    return jobs or None


def default_jobs():
    """(issue 418) One compiler per CPU thread: nx2/build.py starts each one only when the memory free holds it (MemoryGate), so the
    count no longer has to fit the biggest files in the memory free at the start. HOOKSHOT_JOBS or --jobs choose"""
    cpus = os.cpu_count() or 2
    print("build: up to %d compilers at once (one per CPU thread), as the memory allows; HOOKSHOT_JOBS=<n> to change" % cpus, flush=True)
    return cpus


def chosen_jobs(given):
    """--jobs when it is given (1 or more), else HOOKSHOT_JOBS, else what default_jobs chooses: worked out only when it is
    needed, so the "compilers at once" line is the number the build uses"""
    if given:
        return given
    try:
        return requested_jobs(os.environ.get("HOOKSHOT_JOBS")) or default_jobs()
    except ValueError as e:
        fail(str(e))


def bundled_mingw():
    """(as TotK Recomp's installer) llvm-mingw in the tools folder: its clang, headers and libraries build the game, and nothing of
    Visual Studio or the Windows SDK is needed. HOOKSHOT_MINGW set already wins; HOOKSHOT_MSVC=1: the Visual Studio route"""
    if LINUX or DARWIN or os.environ.get("HOOKSHOT_MSVC") == "1":
        return os.environ.get("HOOKSHOT_MINGW", "")
    if not os.environ.get("HOOKSHOT_MINGW"):
        here = os.path.join(ROOT, "llvm-mingw")
        if os.path.isfile(os.path.join(here, "bin", "clang" + (".exe" if os.name == "nt" else ""))):
            os.environ["HOOKSHOT_MINGW"] = here
        elif os.path.isdir(here):
            # (the folder is there and its compiler is not: an antivirus took it (false positives on unsigned tools), or the
            # zip was not unpacked whole. It went on to the Visual Studio route and said "The Windows SDK was not found")
            missing = [n for n in ("clang.exe", "clang++.exe", "ld.lld.exe")
                       if not os.path.isfile(os.path.join(here, "bin", n))]
            fail("Files of the builder's own compiler are missing (%s in %s). Your antivirus most likely removed them "
                 "(a false alarm on unsigned programs): restore them from its quarantine or allow the Hookshot Builder folder, "
                 "then unzip HookshotBuilder.zip again and build. Visual Studio is not needed."
                 % (", ".join(missing) or "bin", os.path.join(here, "bin")))
    return os.environ.get("HOOKSHOT_MINGW", "")


def check_mingw():
    """The bundled compiler builds and links a Windows program: found now, not 40 minutes in"""
    sys.path.insert(0, os.path.join(ROOT, "third_party", "a64-kit", "tools"))
    import toolchain
    cc = toolchain.find("clang")   # (HOOKSHOT_MINGW's, else the one toolchain.py finds: the same as the build uses)
    if not os.path.isfile(cc):   # (HOOKSHOT_MINGW set to a folder without the compiler: said here, not as a silent SystemExit)
        fail("The builder's own compiler was not found at %s. Set HOOKSHOT_MINGW to an llvm-mingw folder, or unpack the "
             "Hookshot Builder zip again into a folder your antivirus allows." % cc)
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "t.c")
        with open(src, "w") as f:
            f.write(chr(10).join(("#include <stdio.h>", "#include <windows.h>", "int main(void) { return 0; }", "")))
        r = subprocess.run([cc] + toolchain.native_target() + toolchain.native_link() +
                           [src, "-o", os.path.join(d, "t.exe")], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        print(r.stdout + r.stderr, flush=True)
        errors = [l for l in r.stderr.splitlines() if "error" in l]
        fail("The builder's own compiler (tools/llvm-mingw) could not build a test program: %s. Unpack the zip again into a folder "
             "your antivirus allows." % (errors[0] if errors else "no message"))
    print("the compiler: %s (no Visual Studio needed)" % os.environ["HOOKSHOT_MINGW"], flush=True)


def check_windows_sdk():
    """The compiler is bundled; Microsoft's C library and Windows SDK may not be, by their licences. Found now, not 40 minutes in."""
    if LINUX or DARWIN:
        return check_linux_compiler()
    if bundled_mingw():
        return check_mingw()
    if CROSS:
        fail("Building for Windows on Linux needs llvm-mingw: unpack its Linux release (github.com/mstorsjo/llvm-mingw) and set "
             "HOOKSHOT_MINGW to its folder.")
    sys.path.insert(0, os.path.join(ROOT, "third_party", "a64-kit", "tools"))
    import toolchain
    cc = toolchain.find("clang")
    if not os.path.isfile(cc):   # (toolchain.need() would raise SystemExit, which the builder cannot show: said in its protocol)
        fail("No C compiler was found. Install clang (and lld) and put it on PATH, set EMSDK to an emsdk checkout, or set "
             "HOOKSHOT_MINGW to an llvm-mingw folder. (%s)" % cc)
    # (an INCLUDE set for the whole machine, by an old Visual Studio or another tool, is all clang reads: without the Windows SDK's C
    # library in it, it is dropped and the compiler looks for Visual Studio itself. Issues 80 and 89)
    for k in [n for n in os.environ if n.upper() == "INCLUDE"]:
        if "ucrt" not in os.environ[k].lower():
            print("INCLUDE is set on this PC without the Windows SDK's C library: not used (%s)" % os.environ[k][:200], flush=True)
            for n in [n for n in os.environ if n.upper() in ("INCLUDE", "LIB", "LIBPATH")]:
                del os.environ[n]
            break
    r = compile_test(toolchain)
    found = None
    if r.returncode:   # (clang looks for Visual Studio its own way, and does not always find it: then ask Visual Studio)
        found = visual_studio_environment()
        if found:
            print("the compiler did not find Visual Studio by itself: using vcvars64", flush=True)
            os.environ.update(found)
            r = compile_test(toolchain)
    if r.returncode and found and ("stdio.h" in r.stderr or "windows.h" in r.stderr.lower()):
        # (only on top of vcvars' INCLUDE: clang takes INCLUDE as all of its system headers once it is set)
        kits = windows_kits_environment(found)
        if kits:
            for k in [n for n in os.environ if n.upper() in ("INCLUDE", "LIB")]:
                del os.environ[k]
            os.environ.update(kits)
            r = compile_test(toolchain)
    if not r.returncode:
        check_cpp_library(toolchain)
        link = link_test(toolchain)
        if not link.returncode:
            return
        print(link.stdout + link.stderr, flush=True)
        errors = [l for l in link.stderr.splitlines() if "error" in l]
        why = errors[0].split("error:", 1)[-1].strip() if errors else (link.stderr.strip().splitlines() or ["no message"])[-1]
        fail("The compiler could not link a test program: %s. In the Visual Studio Installer choose Modify on Visual Studio 2022, "
             "tick \"Desktop development with C++\" with a Windows 11 SDK, then build again." % why)
    print(r.stdout + r.stderr, flush=True)   # (all of it, for Show details)
    errors = [l for l in r.stderr.splitlines() if "error:" in l]
    why = errors[0].split("error:", 1)[1].strip() if errors else (r.stderr.strip().splitlines() or ["no message"])[-1]
    if "old c library" in why.lower():
        fail("The compiler found an old Visual Studio's C library (from before 2015) instead of the Windows SDK's. In the Visual Studio "
             "Installer choose Modify on Visual Studio 2022, tick \"Desktop development with C++\" with a Windows 11 SDK, then build again. (%s)" % why)
    if "windows.h" in why.lower() or "stdio.h" in why.lower():
        fail("The Windows SDK was not found. In the Visual Studio Installer choose Modify, and under \"Desktop development with C++\" tick a "
             "Windows 11 SDK, then build again. (%s)" % why)
    if "file not found" in why:
        fail("Visual Studio's C++ tools were not found. In the Visual Studio Installer choose Modify, tick \"Desktop development with C++\" "
             "and its MSVC x64/x86 build tools, then build again. (%s)" % why)
    fail("The compiler could not run a test build: %s" % why)


def stop_stray_compilers(work, default_work):
    """(issues 501, 530) A build left running by an earlier one on this work folder (the builder closed, crashed, or replaced by an
    update mid-build) keeps its files open: the next build stopped at once with 'OSError: [Errno 22]' writing sa/gen/a64_fpx.h, or
    WinError 1224 on the play profile. Only that build goes: an earlier make_game on this work folder, the build and lift steps
    whose make_game is gone, and compilers whose command line names this work folder. Never this build or what started it."""
    if LINUX or DARWIN:
        return
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'clang*' -or $_.Name -like 'ld.lld*' -or $_.Name -like 'python*' } "
          "| Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress")
    try:
        import json
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, text=True, timeout=90)
        procs = json.loads(r.stdout or "[]")
        if isinstance(procs, dict):
            procs = [procs]
        alive = {q["ProcessId"]: q for q in procs}
        mine, pid = set(), os.getpid()        # (this process and the chain that started it)
        while pid in alive and pid not in mine:
            mine.add(pid)
            pid = alive[pid]["ParentProcessId"]
        mine.add(pid)
        w = os.path.normcase(os.path.abspath(work))
        names = lambda c: os.path.normcase((c or "").replace("/", "\\"))
        doomed = {}
        for q in procs:
            c, n = names(q.get("CommandLine")), q["Name"].lower()
            if q["ProcessId"] in mine:
                continue
            if "make_game.py" in c and (w in c or ("--work" not in c and w == os.path.normcase(default_work))):
                doomed[q["ProcessId"]] = n
            elif ("build.py" in c or "lift.py" in c) and "--standalone" in c and q["ParentProcessId"] not in alive:
                doomed[q["ProcessId"]] = n           # (its make_game is gone)
            elif not n.startswith("python") and w in c:
                doomed[q["ProcessId"]] = n
        for k in doomed:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(k)], capture_output=True, timeout=60)
        if doomed:
            print("stopped %d process(es) an earlier build left running on this work folder: %s"
                  % (len(doomed), " ".join(sorted(set(doomed.values())))), flush=True)
            time.sleep(2)
    except Exception as e:   # (not finding them is no reason to stop)
        print("could not look for an earlier build's processes: %s" % e, flush=True)


def makefile_words(text):
    """Decode clang -M words, preserving ordinary Windows backslashes."""
    text = re.sub(r"\\\r?\n", " ", text)
    words = re.findall(r"(?:\\[ \t]|\S)+", text)
    # clang doubles backslashes before an escaped space, but adds only one before #.
    def unescape(m):
        slashes, char = m.groups()
        return "\\" * ((len(slashes) - 1) // 2 if char != "#" else len(slashes) - 1) + char
    return [re.sub(r"(\\+)([ \t#])", unescape, word).replace("$$", "$") for word in words]


def _drop_stale_linux(work):
    """The AppImage's sysroot is a new /tmp/.mount_... path every start. The stamp is the compiler's version and stdio.h's
    bytes, not that path, so an update reuses the compiled game when the headers did not change (the Windows stamp leaves
    the builder's install folder out for the same reason, issue 565)."""
    import hashlib
    sysroot = os.environ.get("HOOKSHOT_SYSROOT", "")
    stdio = os.path.join(sysroot, "usr", "include", "stdio.h") if sysroot else "/usr/include/stdio.h"
    try:
        body = open(stdio, "rb").read()
    except OSError:
        return
    sys.path.insert(0, os.path.join(ROOT, "third_party", "a64-kit", "tools"))
    import toolchain
    try:
        cc = toolchain.need(toolchain.find("clang"))
        ver = subprocess.run([cc, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except Exception:
        return
    first = ver.stdout.splitlines()[:1]
    if ver.returncode or not first:
        return
    stamp = hashlib.sha1(body + first[0].encode(), usedforsecurity=False).hexdigest()
    note = os.path.join(work, "system_headers.txt")
    try:
        with open(note) as f:
            if f.read().strip() == stamp:
                return
    except OSError:
        pass
    for sub in (os.path.join(work, "objcache"), os.path.join(work, "sa", "build", "obj")):
        if os.path.isdir(sub):
            print("the system headers changed since the last build: its compiled objects are not reused (%s)" % sub, flush=True)
            shutil.rmtree(sub, ignore_errors=True)
    with open(note, "w") as f:
        f.write(stamp + chr(10))


def prune_object_cache(work):
    """(issue 1287) The object cache down to the objects this build used: each object in sa/build/obj names its key in <obj>.sha1
    (nx2/build.py compile_one); cached objects no stamp names (earlier releases', other settings') go. Returns the bytes kept.
    Nothing is pruned when no stamp is found (a build that did not reach the compile keeps the cache as it was)"""
    cache, obj_dir = os.path.join(work, "objcache"), os.path.join(work, "sa", "build", "obj")
    used = set()
    if os.path.isdir(obj_dir):
        for f in os.listdir(obj_dir):
            if f.endswith(".sha1"):
                try:
                    with open(os.path.join(obj_dir, f)) as h:
                        used.add(h.read().strip())
                except OSError:
                    pass
    kept = 0
    if not os.path.isdir(cache):
        return kept
    for f in os.listdir(cache):
        p = os.path.join(cache, f)
        if used and f.endswith(".o") and f[:-2] not in used:
            try:
                os.remove(p)
            except OSError:
                pass
            continue
        try:
            kept += os.path.getsize(p)
        except OSError:
            pass
    return kept


def clear_folder(path):
    """(issue 1354) A folder this build makes again from nothing (the game's code, exefs): gone before it is made. rmtree with
    ignore_errors left it behind whenever a file in it was held (an antivirus scan, an explorer window, a game still closing), and the
    copy into it stopped with FileExistsError at every update. Tried a few times, then moved aside (deleted at the next build), and
    only then a clear stop"""
    for attempt in range(5):
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            return
        time.sleep(1)
    parent, name = os.path.split(path.rstrip("\\/"))
    for stale in os.listdir(parent or "."):   # (what an earlier build moved aside: gone now, if it can be)
        if stale.startswith(name + ".old-"):
            shutil.rmtree(os.path.join(parent, stale), ignore_errors=True)
    aside = "%s.old-%d" % (path.rstrip("\\/"), os.getpid())
    try:
        os.rename(path, aside)
        print("could not delete %s (a file in it is in use): moved aside to %s" % (path, aside), flush=True)
        return
    except OSError as e:
        fail("Could not clear %s (%s). A file in it is in use: close any window showing that folder, wait for your antivirus "
             "to finish, then try again." % (path, e))


def drop_stale_objects(work):
    """(issue 231) Objects compiled against other system headers are not reused. A first build that compiled with an old Visual Studio's
    stdio.h (before 2015) left its objects in the cache; once the PC was fixed every later build reused them and the link failed on
    __iob_func. The headers the compiler finds are noted, and when they change the compiled objects go"""
    if LINUX or DARWIN:
        _drop_stale_linux(work)
        return
    sys.path.insert(0, os.path.join(ROOT, "third_party", "a64-kit", "tools"))
    import hashlib
    import toolchain
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "t.c")
        with open(src, "w") as f:
            f.write(chr(10).join(("#include <stdio.h>", "#include <stdlib.h>", "#include <windows.h>", "")))
        r = subprocess.run([toolchain.need(toolchain.find("clang"))] + toolchain.native_target() + ["-M", src], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    if r.returncode:
        return
    found = sorted({h.lower() for h in makefile_words(r.stdout) if h.endswith(".h")})

    # (issue 565) The paths are taken relative to the builder's own folder, with the compiler's version: under
    # versions\<tag>\ every release looked like new headers, and an update compiled everything again (2+ hours). clang
    # writes them with / where the folder has \: compared with / on both sides, each path's own spelling kept for the old stamp
    mine = os.path.normcase(os.path.abspath(ROOT)).lower().replace(os.sep, "/")
    ours = lambda h: h.replace(os.sep, "/").startswith(mine + "/")

    def stamp_for(root):   # (the old stamp: the headers' full paths, with the builder's own folder as it was in that version)
        root = root.replace(os.sep, "/")
        moved = [((root if "/" in h[:len(mine)] else root.replace("/", os.sep)) + h[len(mine):]) if ours(h) else h for h in found]
        return hashlib.sha1(chr(10).join(sorted(moved)).encode(), usedforsecurity=False).hexdigest()

    rel = sorted(("<tools>" + h[len(mine):].replace(os.sep, "/")) if ours(h) else h for h in found)
    ver = subprocess.run([toolchain.need(toolchain.find("clang")), "--version"], capture_output=True, text=True, encoding="utf-8",
                         errors="replace").stdout.splitlines()[:1]
    stamp = hashlib.sha1(chr(10).join(ver + rel).encode(), usedforsecurity=False).hexdigest()
    note = os.path.join(work, "system_headers.txt")
    try:
        with open(note) as f:
            had = f.read().strip()
    except OSError:
        had = ""
    if had == stamp:
        return
    # (a stamp an installed version of the builder wrote the old way: the same headers, in its own folder; kept, and written anew)
    versions = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(ROOT))))
    olds = {stamp_for(mine)}
    if os.path.basename(versions).lower() == "versions" and os.path.isdir(versions):
        for v in os.listdir(versions):
            olds.add(stamp_for(os.path.normcase(os.path.join(versions, v, "HookshotBuilder", "tools")).lower()))
    if had and had in olds:
        print("the system headers are the same as the last build's (an earlier version of the builder): its objects are reused", flush=True)
        with open(note, "w") as f:
            f.write(stamp + chr(10))
        return
    for sub in (os.path.join(work, "objcache"), os.path.join(work, "sa", "build", "obj")):
        if os.path.isdir(sub):
            print("the system headers changed since the last build: its compiled objects are not reused (%s)" % sub, flush=True)
            shutil.rmtree(sub, ignore_errors=True)
    with open(note, "w") as f:
        f.write(stamp + chr(10))


def seed_pipelines(out):
    """The pipelines recorded on the development PC (hookshot_pipelines_seed.bin in the tools: program keys and draw states, no game
    code), as the game folder's list, so its first start builds them before the title, as TotK Recomp's shipped shader list does,
    instead of compiling each when it is first drawn (the stutter of a first visit). Each release ships the list its own build
    made: the file's first 8 bytes are that build's stamp, and a list the folder has from the same build is kept (it grows as
    the player plays)"""
    seed = os.path.join(ROOT, "hookshot_pipelines_seed.bin")
    dst = os.path.join(out, "hookshot_pipelines.bin")
    if not os.path.isfile(seed):
        return
    with open(seed, "rb") as f:
        stamp = f.read(8)
    try:
        with open(dst, "rb") as f:
            if f.read(8) == stamp:
                return
    except OSError:
        pass
    shutil.copyfile(seed, dst)
    print("the shipped pipeline list: %d KB, built before the first title" % (os.path.getsize(seed) >> 10), flush=True)


def ship_state_list(out):
    """The pipeline state list made from play of the game on the development PC (assets/pipeline_states.bin.xz: each
    pipeline's stage code keys, vertex and target formats and draw state; hashes and state only, no game code), unpacked as the
    folder's hookshot_pipeline_states_shipped.bin: the first start's shader preparation builds those pipelines before the
    title, from the player's own shaders (hookshot_shaders.bin), instead of compiling each when it is first drawn. Good for
    any build, and optional: a list that is missing or does not read is left out with a line saying so (the release checks
    stop on it: nx2/pipeline_states.py --check)"""
    import pipeline_states
    src = os.path.join(ROOT, *pipeline_states.SHIPPED)
    dst = os.path.join(out, "hookshot_pipeline_states_shipped.bin")
    if not os.path.isfile(src):
        return
    try:
        data = pipeline_states.load(src)
        n = len(pipeline_states.parse(data, src, strict=True))
    except (OSError, SystemExit) as e:
        print("the shipped pipeline state list was left out: %s" % e, flush=True)
        return
    try:
        with open(dst, "rb") as f:
            same = f.read() == data
    except OSError:
        same = False
    if not same:
        with open(dst + ".new", "wb") as f:
            f.write(data)
        os.replace(dst + ".new", dst)
    print("the shipped pipeline state list: %d pipelines" % n, flush=True)


# (the builders read this line's start: the step was skipped or failed, and the shaders' row says so instead of a check mark)
NOT_PREPARED = "the shaders were not prepared now"
# (a run that prints nothing this long is stopped. Not its whole length: that is 25 minutes on some AMD GPUs, and the driver's own
# step near the end can sit at 99% for minutes)
PREPARE_SILENCE = 15 * 60
GAME_ENV_DROP = ("HOOKSHOT_", "PYTHON", "APPDIR", "APPIMAGE", "ARGV0", "OWD")


def span(seconds):
    return "%d minutes" % (seconds // 60) if seconds >= 120 else "%g seconds" % seconds


def game_env(environ=None):
    """The environment the game runs in when the tools start it: without what the AppImage runtime and the tools put there (their
    libraries first on the search path, Python's settings, the HOOKSHOT_ build switches), so it loads its own SDL and the system's
    Vulkan, as when the player starts it. The Linux builder's Play button uses it too; builder/linux/hookshot-launch drops the same"""
    env = {k: v for k, v in (os.environ if environ is None else environ).items() if not k.startswith(GAME_ENV_DROP)}
    env.pop("LD_LIBRARY_PATH", None)
    return env


def not_prepared(why):
    print("%s (%s): the game prepares them at its first start" % (NOT_PREPARED, why), flush=True)


def prepare_skipped(a, environ=None):
    """Why the build leaves the shaders to the first start, or None: it prepares them"""
    environ = os.environ if environ is None else environ
    if a.no_prepare_shaders:
        return '"Prepare shaders now" is unticked'
    if environ.get("HOOKSHOT_NO_PREPARE", "0") != "0":   # (set and not 0, as the game reads HOOKSHOT_NO_UPDATE_CHECK)
        return "HOOKSHOT_NO_PREPARE is set"
    if CROSS:   # (hookshot.exe can't run here, and under Wine it would prepare for this PC's GPU, not the one that plays it)
        return "a Windows game built on Linux prepares them on the PC it runs on"
    return None


def show_prepared(line):
    """The game's @@stage and @@progress lines go on to the builder; its own @@done and @@error would end or fail the build there,
    so they go on as plain text"""
    return line if line.startswith(("@@stage ", "@@progress ")) or not line.startswith("@@") else line[2:]


def prepare_shaders(cmd, folder=None, silence=PREPARE_SILENCE):
    """The shaders prepared now, under the builder's progress bar, not at the game's first start behind a black window (minutes on
    some GPUs, issue 711): hookshot --prepare-shaders (host/hos_main.c, gpu/vk/vk_main.cpp), the same work as that first start, in
    the game's folder and environment, as the builders' Play starts it. A PC whose Vulkan can't (exit 3), a run silent for `silence` seconds (then stopped), or
    any other failure leaves the work to the first start, as before: never a failed build. Returns its exit code (None: stopped)"""
    try:
        code = run(cmd, check=False, show=show_prepared, cwd=folder or os.path.dirname(cmd[0]) or None,
                   base=game_env(), silence=silence)
    except OSError as e:
        not_prepared(str(e))
        return 1
    if code is None:
        not_prepared("the game printed nothing for %s and was stopped" % span(silence))
    elif code == 3:
        not_prepared("no usable Vulkan here")
    elif code:
        not_prepared("the game stopped with exit status %d" % code)
    return code


def folder_language(out):
    """the language a game folder was built in: the code line of its language.txt"""
    try:
        with open(os.path.join(out, "language.txt"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and any(line == code for code, _ in LANGUAGES):
                    return line
    except OSError:
        pass
    return None


def profile_readable(prof):
    """(linux/darwin) the profile is made by a recent clang (the Windows tools'): an older one, the system's, cannot read it and stops the
    build. Then the game is built without it (a little slower in play), not at all"""
    if not (LINUX or DARWIN):
        return True
    sys.path.insert(0, os.path.join(ROOT, "third_party", "a64-kit", "tools"))
    import toolchain
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "t.c")
        with open(src, "w") as f:
            f.write("int f(int x) { return x + 1; }" + chr(10))
        r = subprocess.run([toolchain.find("clang")] + toolchain.native_target() +
                           ["-O2", "-Wno-everything", "-fprofile-instr-use=" + prof, "-c", src, "-o",
                            os.path.join(d, "t.o")], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        print("this compiler cannot read the play profile (%s): building without it" % (r.stderr.strip().splitlines() or ["?"])[-1],
              flush=True)
    return r.returncode == 0


def copy_writable(src, dst):
    """src's bytes at dst, writable whatever src's mode: copy2 took the mode along, and from a read-only install (a Nix
    store, a packaged tools folder) the copies in the work folder were read-only, so lift.py could not write chunks.txt
    again (PermissionError) and every later build failed on the same file"""
    if os.path.exists(dst):
        os.chmod(dst, stat.S_IREAD | stat.S_IWRITE)
    shutil.copyfile(src, dst)


def refuse_dump_links(folder):
    """An extracted dump holds only files and folders: a link in it was followed, and hard-linked or copied the file it
    names (anywhere on this PC) into the game folder. The folder itself may be one. (Walked as a long path: #1468)"""
    for d, dirs, files in os.walk(long_path(folder)):
        for name in dirs + files:
            path = os.path.join(d, name)
            attrs = os.lstat(path)
            if stat.S_ISLNK(attrs.st_mode) or getattr(attrs, "st_file_attributes", 0) & getattr(
                    stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                fail("The game files at %s contain a link (%s): copy them without links and choose that folder."
                     % (folder, path))


def long_path(p):
    """(Windows) p as an extended-length path (\\\\?\\...): a game folder whose deepest file passes 260 characters still links
    and is read (#1468); Python takes these without Windows' long-paths setting. Elsewhere, or one already: as is (nup.py's)"""
    if os.name != "nt" or not p:
        return p
    p = os.path.abspath(p)
    if p.startswith("\\\\?\\"):
        return p
    return "\\\\?\\UNC\\" + p[2:] if p.startswith("\\\\") else "\\\\?\\" + p


def link_or_copy(src, dst):
    """the romfs by hard links where the disk allows: 26 GB not written twice"""
    src, dst = long_path(src), long_path(dst)
    files = [os.path.join(d, f) for d, _, fs in os.walk(src) for f in fs]
    for i, s in enumerate(files):
        t = os.path.join(dst, os.path.relpath(s, src))
        os.makedirs(os.path.dirname(t), exist_ok=True)
        if not os.path.exists(t):
            try:
                os.link(s, t)
            except OSError:
                # A retry skips existing targets, so publish the copy only after it is complete.
                fd, staged = tempfile.mkstemp(prefix=".romfs-", dir=os.path.dirname(t))
                try:
                    os.close(fd)
                    shutil.copy2(s, staged)
                    os.replace(staged, t)
                except BaseException:
                    with contextlib.suppress(FileNotFoundError):
                        if os.name == "nt":
                            # copy2 can carry the source's read-only attribute over.
                            os.chmod(staged, stat.S_IWRITE)
                        os.unlink(staged)
                    raise
        if i % 500 == 0:
            say("progress", "%.3f" % (i / max(1, len(files))))


def shader_census_cmd(romfs, out):
    """The shader list, under the same UTF-8 mode as the other steps. -I alone follows the console's code page, and an
    archive name that page cannot print stopped this step: the game then compiled its shaders as it played."""
    return PY + [os.path.join(HERE, "shader_census.py"), long_path(romfs), "--out", out]


LIFT_KEY = ".lift_key"   # (in <work>/sa/gen: what the lifted C there was made from)


def lift_key(exefs, work, env):
    """What the lift's output depends on: the game's code, the translator (nx2/, the vendored a64-kit), the HLE functions host/ defines
    (hooked in the lift; the rest of host/ is compiled after it, so a change there alone does not lift again), the hot list and chunk
    boundaries, the lift's environment and the Python running it. A file the lift never reads may be in it (a new build then lifts
    again); one it reads must be"""
    import kit  # noqa: F401  (a64-kit on the path, for standalone)
    import standalone
    h = hashlib.sha1(sys.version.encode(), usedforsecurity=False)
    h.update(" ".join(sorted(standalone.implemented())).encode())
    # (each file named from its own base: the exefs and the work folder may be on another drive than the source, which relpath refuses)
    files = [(exefs, os.path.join(exefs, f)) for f in sorted(os.listdir(exefs))]
    for top in (HERE, os.path.join(ROOT, "third_party", "a64-kit")):
        for d, dirs, fs in os.walk(top):
            dirs[:] = sorted(x for x in dirs if x != "__pycache__")
            files += [(ROOT, os.path.join(d, f)) for f in sorted(fs) if f.endswith((".py", ".c", ".h", ".cpp", ".hpp", ".txt", ".json"))]
    files += [(work, os.path.join(work, "hot_funcs.txt")), (work, os.path.join(work, "image", "chunks.txt"))]
    for base, f in files:
        if os.path.isfile(f):
            h.update(os.path.relpath(f, base).replace(os.sep, "/").encode() + bytes(1))
            with open(f, "rb") as src:
                h.update(hashlib.sha1(src.read(), usedforsecurity=False).digest())
    lift_env = dict(env, **{k: v for k, v in os.environ.items() if k.startswith(("A64_", "OOT_", "RX_"))})
    h.update(repr(sorted(lift_env.items())).encode())
    return h.hexdigest()


def gen_print(gen):
    """The lifted C's files as the lift left them (names, sizes, times): another builder's lift into the same work folder
    (an older one, or another branch's, which knows nothing of the key) changes it, and the key no longer vouches for it"""
    h = hashlib.sha1(usedforsecurity=False)
    for name in sorted(os.listdir(gen)):
        p = os.path.join(gen, name)
        if name != LIFT_KEY and os.path.isfile(p):
            st = os.stat(p)
            h.update(("%s %d %d\n" % (name, st.st_size, st.st_mtime_ns)).encode())
    return h.hexdigest()


def write_lift_key(work, key):
    gen = os.path.join(work, "sa", "gen")
    with open(os.path.join(gen, LIFT_KEY), "w") as f:
        f.write(key + "\n" + gen_print(gen) + "\n")


def lifted_cut_short(gen):
    """The lifted C files (code_*.c) that do not end as every lifted file does, a function's closing brace and a newline: cut short
    (a run stopped while writing one, a full disk, a second build in the same folder: issue 1197)"""
    bad = []
    if not os.path.isdir(gen):
        return bad
    for f in sorted(os.listdir(gen)):
        if not (f.startswith("code_") and f.endswith(".c")):
            continue
        try:
            with open(os.path.join(gen, f), "rb") as h:
                h.seek(0, 2)
                n = h.tell()
                h.seek(max(0, n - 2))
                end = h.read()
        except OSError:
            end = b""
        if end != b"}\n":
            bad.append(f)
    return bad


def lifted_before(work, key):
    """The lift (and split_hot) in <work>/sa finished before with this key, its C is as that lift left it, and what the later
    steps read of it is there"""
    gen, image = os.path.join(work, "sa", "gen"), os.path.join(work, "sa", "image")
    try:
        with open(os.path.join(gen, LIFT_KEY)) as f:
            lines = f.read().split()
    except OSError:
        return False
    if len(lines) != 2 or lines[0] != key or lines[1] != gen_print(gen):
        return False
    return os.path.isfile(os.path.join(image, "image.bin")) and os.path.isfile(os.path.join(gen, "a64_table.c"))


def ngx_script():
    """scripts/ngx_sdk.py: NVIDIA's DLSS SDK, its file table and where each file goes"""
    import importlib.util
    path = os.path.join(ROOT, "scripts", "ngx_sdk.py")
    if not os.path.isfile(path):   # (the AppImage carries no scripts/: its Vulkan back end comes built, without DLSS)
        fail("NVIDIA DLSS (HOOKSHOT_NGX_SDK) needs %s, which this builder does not carry: its renderer is built without DLSS. "
             "Unset HOOKSHOT_NGX_SDK, or build Hookshot from source for DLSS." % path)
    spec = importlib.util.spec_from_file_location("ngx_sdk", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ngx_platform():
    return "linux" if LINUX else "windows"


def fetch_ngx_sdk(a):
    """--fetch-ngx-sdk (the Hookshot Builder's NVIDIA DLSS tick): NVIDIA's DLSS SDK into HOOKSHOT_NGX_SDK before the build, once
    NVIDIA's license was accepted (--accept-nvidia-license: the builder asked first). Only what is missing or not the file
    expected is downloaded"""
    sdk = os.environ.get("HOOKSHOT_NGX_SDK", "")
    if not sdk:
        fail("--fetch-ngx-sdk needs HOOKSHOT_NGX_SDK, the folder NVIDIA's DLSS SDK goes into.")
    if not a.accept_nvidia_license:
        fail("NVIDIA DLSS needs NVIDIA's license accepted first (--accept-nvidia-license).")
    ngx = ngx_script()
    print(ngx.NOTICE, flush=True)
    print("NVIDIA's license accepted: getting NVIDIA's DLSS SDK into %s" % sdk, flush=True)
    try:
        ngx.fetch(sdk, ngx_platform(), say=lambda line: print(line, flush=True))
    except (OSError, ValueError) as e:
        fail("NVIDIA's DLSS SDK could not be downloaded (%s). Check the connection and build again, or untick NVIDIA DLSS." % e)


def ngx_built():
    """This build has NVIDIA DLSS: HOOKSHOT_NGX_SDK holds this platform's library (what nx2/build.py takes)"""
    sdk = os.environ.get("HOOKSHOT_NGX_SDK", "")
    return bool(sdk) and os.path.isfile(ngx_script().library(sdk, ngx_platform()))


FSR_MARK = ".hookshot_fsr"   # (in a game folder built with AMD FSR 4: --update builds it with FSR again)


def fsr_wanted(a, out):
    """AMD FSR 4 in this build (--fsr; or --update of a folder built with it, unless --no-fsr): nothing to download, AMD's
    MIT headers are in third_party/fidelityfx and its DLLs are the player's (the readme)"""
    if getattr(a, "no_fsr", False):
        return False
    return bool(getattr(a, "fsr", False)) or bool(a.update and os.path.isfile(os.path.join(out, FSR_MARK)))


def place_ngx_runtime(out):
    """(NVIDIA DLSS) a game built with NVIDIA's SDK (HOOKSHOT_NGX_SDK, as nx2/build.py takes it) gets DLSS's runtime in its ngx
    folder, where gpu/vk/vk_dlss.cpp looks first: nvngx_dlss.dll on Windows, libnvidia-ngx-dlss.so.<version> on Linux. Never
    NGX's core (_nvngx.dll is the driver's) and nothing beside the exe. Returns the file placed, or None"""
    ngx = ngx_script()
    platform = ngx_platform()
    sdk = os.environ.get("HOOKSHOT_NGX_SDK", "")
    if not sdk or not (os.path.isfile(ngx.library(sdk, platform)) and os.path.isfile(ngx.runtime(sdk, platform))):
        # (a folder built with DLSS before and rebuilt without it loses NVIDIA's runtime too)
        stale = os.path.join(out, "ngx", ngx.runtime_name(platform))
        if os.path.isfile(stale):
            with contextlib.suppress(OSError):
                os.remove(stale)
                os.rmdir(os.path.dirname(stale))
        return None
    dst = ngx.install_runtime(sdk, platform, os.path.join(out, "ngx"))
    print("NVIDIA DLSS: %s (NVIDIA's, under NVIDIA's license: never share this game folder)" % dst, flush=True)
    return dst


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--nup")
    p.add_argument("--romfs")
    p.add_argument("--exefs")
    p.add_argument("--out")
    p.add_argument("--work", default=os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
                                                  "hookshot-builder-windows" if CROSS else "hookshot-builder")   # (the objects apart)
                   if os.name != "nt" else os.path.join(os.environ.get("LOCALAPPDATA", ROOT), "HookshotBuilder"))
    # (HOOKSHOT_JOBS: fewer compilers on a PC short of memory; the AppImage's builds pass no --jobs)
    p.add_argument("--jobs", type=int)
    p.add_argument("--language", default="en-US", help="the game's language: a code from LANGUAGES, written to language.txt")
    p.add_argument("--check", action="store_true")
    p.add_argument("--game", help="your copy: a .nup file, or a folder with romfs and exefs in it (the same as --nup, or --romfs and --exefs)")
    p.add_argument("--prepare", action="store_true", help="for RecompLauncher: no window, progress lines, --out ~/Games/Hookshot unless given")
    p.add_argument("--update", help="a game folder built before: built again from the game files it keeps (the game's update offer)")
    p.add_argument("--no-prepare-shaders", action="store_true",
                   help="leave the shaders' preparation to the game's first start (the builder's \"Prepare shaders now\" unticked)")
    p.add_argument("--log", metavar="FILE", help="also save build output to a UTF-8 file (replaces the file if it exists)")
    # (NVIDIA DLSS, off unless asked: NVIDIA's SDK into HOOKSHOT_NGX_SDK first, under NVIDIA's license. scripts/ngx_sdk.py)
    p.add_argument("--fetch-ngx-sdk", action="store_true", help="download NVIDIA's DLSS SDK into HOOKSHOT_NGX_SDK before the build")
    p.add_argument("--accept-nvidia-license", action="store_true", help="NVIDIA's DLSS SDK license, accepted (with --fetch-ngx-sdk)")
    # (AMD FSR 4, off unless asked: nothing is downloaded. gpu/vk/vk_fsr4.cpp)
    p.add_argument("--fsr", action="store_true", help="build with AMD FSR 4 (AMD's DLLs are not included: see the readme)")
    p.add_argument("--no-fsr", action="store_true", help="with --update: build without AMD FSR 4 even if the folder had it")
    a = p.parse_args()
    if a.prepare:   # (first: a bad --game below is said as RecompLauncher's "error" line)
        global PREPARE
        PREPARE = True
        a.out = a.out or os.path.join(os.path.expanduser("~"), "Games", "Hookshot")
    if a.game:   # (a path from a launcher: said plainly before any folder is made, not as a traceback halfway in)
        if os.path.isdir(a.game):
            a.romfs, a.exefs = os.path.join(a.game, "romfs"), os.path.join(a.game, "exefs")
            if not (os.path.isdir(a.romfs) and os.path.isdir(a.exefs)):
                fail("The folder %s needs both a romfs and an exefs folder in it." % a.game)
        elif os.path.isfile(a.game):
            a.nup = a.game
        else:
            fail("Your copy of the game was not found: %s" % a.game)
    a.default_work = p.get_default("work")   # (main: the builder's own work folder, stop_stray_compilers)
    return a


def spinning_disk(folder):
    """True on a hard drive, False on an SSD, None when the drive cannot be told (nx2/disk.py)"""
    return _disk.spinning(folder)


def warn_slow_disk(*folders):
    """A build reads and writes tens of gigabytes, and on a hard drive it takes much longer than on an SSD. Say so, and build
    anyway: the player may have no other folder with the room. Said once, for the first folder on a hard drive."""
    for folder in folders:
        if spinning_disk(folder) is True:
            # (on stderr under --prepare: RecompLauncher reads stdout's progress lines only)
            print("Warning: %s is on a hard drive. An SSD builds the game much faster: build there if you can. "
                  "The build goes ahead on this drive." % folder, file=sys.stderr if PREPARE else sys.stdout, flush=True)
            return


def main(a=None):
    if a is None:
        a = parse_args()
    if a.jobs is not None and a.jobs < 0:
        fail("--jobs must be 1 or more, or 0 for automatic.")
    a.jobs = chosen_jobs(a.jobs)
    os.makedirs(a.work, exist_ok=True)
    no_throttle()
    if os.name == "nt":   # (the PC kept awake while this runs: a build is 45 minutes, and sleep stopped it)
        import ctypes
        ctypes.WinDLL("kernel32").SetThreadExecutionState(0x80000000 | 0x00000001)
    if a.check:
        return check(a, a.work)
    if a.update:
        a.out = a.update
        a.language = folder_language(a.update) or a.language
    if not a.out or not (a.update or a.nup or (a.romfs and a.exefs)):
        fail("needs --out, and --nup or --romfs with --exefs")
    out = os.path.abspath(a.out)
    work = os.path.abspath(a.work)
    warn_slow_disk(out, work)   # (a warning, not a stop: a hard drive still builds, only much slower)
    check_writable(out)
    # (linux) the compiler probe waits until the compile. The game-free cache test stops at the lift, and a missing
    # compiler is still said before the long compile, not after the package has been read
    check_cpu()   # (no game read yet: the AppImage on a CPU without AVX2 stops here)
    if not (LINUX or DARWIN):
        check_windows_sdk()
    stop_stray_compilers(work, a.default_work)
    drop_stale_objects(work)
    if getattr(a, "fetch_ngx_sdk", False):
        fetch_ngx_sdk(a)
    # (AMD FSR 4: the build's switch for nx2/build.py, and the folder's mark for the next --update)
    if fsr_wanted(a, out):
        os.environ["HOOKSHOT_FSR"] = "1"
        open(os.path.join(out, FSR_MARK), "w").close()
        if os.environ.get("HOOKSHOT_VK_PREBUILT"):   # (the AppImage's back end, built without FSR 4)
            print("--fsr: this build uses the prebuilt Vulkan back end (HOOKSHOT_VK_PREBUILT), which has no AMD FSR 4: the "
                  "Upscaler row will not offer it", flush=True)
    else:
        os.environ.pop("HOOKSHOT_FSR", None)
        if os.path.isfile(os.path.join(out, FSR_MARK)):
            os.remove(os.path.join(out, FSR_MARK))
    exefs = os.path.join(work, "exefs")
    romfs = os.path.join(out, "romfs")

    say("stage", "read", "Reading your game files")
    clear_folder(exefs)
    kept = os.path.join(out, ".hookshot_exefs")   # (the game's code as read, kept in the folder: what an update builds from again)
    if a.update:
        if not os.path.isdir(kept) or not os.path.isdir(romfs):
            fail("This game folder has no copy of the game files to update from: it was built before updates came in. Choose your game files "
                 "in Hookshot Builder and build into the same folder once; updates after that work by themselves.")
        check_cache_paths(out, (kept, romfs))
        shutil.copytree(kept, exefs)
        check_modules(exefs)
        stand_in_damaged_files(out, romfs)   # (a folder unpacked by an earlier builder from a 23.3 GB dump)
    elif a.nup:
        # (what an earlier build left is not kept without a reason to trust it: builders before the compressed .nup fix wrote those files as
        # they lay, so a folder they left held broken game data, and the game crashed at start over its empty dictionaries)
        game = os.path.join(out, ".game")
        good = os.path.join(out, ".hookshot_romfs")
        check_cache_paths(out, (game, good, kept, romfs))
        # (an update of the builder over the same .nup: nothing to read again, only what the build needs. Issues 21 and 28)
        try:
            st = os.stat(a.nup)
        except OSError as e:
            fail("Could not access your .nup file %s: %s. Check that the file is still there, reconnect its drive if needed, "
                 "or choose the file again in Hookshot Builder." % (a.nup, e))
        stamp = "unpacked by this builder: %s %d" % (os.path.basename(a.nup), st.st_size)
        same = False
        if os.path.exists(good) and os.path.isdir(romfs) and os.path.isdir(kept):
            with open(good) as f:
                same = f.read().strip() == stamp
        if same:
            print("the game was read from this .nup before: reading it again is skipped", flush=True)
            shutil.copytree(kept, exefs)
        else:
            shutil.rmtree(game, ignore_errors=True)
            with contextlib.suppress(FileNotFoundError):   # (a new unpack is checked again)
                os.remove(os.path.join(out, ".hookshot_romfs_checked"))
            # Keep the last usable cache until the new package has been read and validated.
            staged_exefs = os.path.join(game, "exefs")
            try:
                run(PY + ["nx2/nup.py", a.nup, "--extract", game])
                check_modules(staged_exefs)
                check_supported_build(staged_exefs)
                if not os.path.isdir(os.path.join(game, "romfs")):
                    fail("The package did not contain a romfs folder.")
            except (OSError, SystemExit):
                try:
                    shutil.rmtree(game)
                except FileNotFoundError:
                    pass
                except OSError as e:
                    print("Could not remove the incomplete extraction at %s (%s)." % (game, e), flush=True)
                raise
            if os.path.exists(romfs):
                shutil.rmtree(romfs)
            shutil.move(os.path.join(game, "romfs"), romfs)
            keep_heads(out, game, stamp)
            shutil.move(staged_exefs, exefs)
            shutil.rmtree(game, ignore_errors=True)
            shutil.rmtree(kept, ignore_errors=True)
            shutil.copytree(exefs, kept)
            with open(good, "w") as f:
                f.write(stamp + chr(10))
        check_modules(exefs)
        # (also when the .nup was read before: a folder built from a 23.3 GB dump by an earlier builder gets them too)
        stand_in_damaged_files(out, romfs)
    else:
        check_cache_paths(out, (kept, romfs))
        refuse_dump_links(a.exefs)
        refuse_dump_links(a.romfs)
        shutil.copytree(a.exefs, exefs)   # (unpacked in place: the user's copy stays as it is)
        run(PY + ["nx2/unpack.py", exefs])
        link_or_copy(a.romfs, romfs)
        shutil.rmtree(kept, ignore_errors=True)
        shutil.copytree(exefs, kept)
    check_supported_build(exefs)

    # (made once on the development PC: lists of addresses and counts, no game code)
    for name in ("hot_funcs.txt", "hot_order.txt", "hookshot_pieces.prof", "hookshot.res"):
        src = os.path.join(ROOT, "work", name)
        dst = os.path.join(work, name)
        # (copied only when it differs: a compiler still ending from a cancelled build keeps the profile mapped, WinError 1224)
        if os.path.exists(src) and not (os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False)):
            copy_writable(src, dst)
    os.makedirs(os.path.join(work, "image"), exist_ok=True)
    src = os.path.join(ROOT, "work", "image", "chunks.txt")   # (where the lifted code's files begin: addresses)
    if os.path.exists(src):
        copy_writable(src, os.path.join(work, "image", "chunks.txt"))
    env = {"OOT_WORK": work, "OOT_EXEFS": exefs, "OOT_ROMFS": romfs, "OOT_DUMP": out, "RX_RELEASE": "1", "A64_HOT_CHUNK": "1"}
    if os.path.exists(os.path.join(work, "hot_funcs.txt")):
        env["A64_HOT_FUNCS"] = os.path.join(work, "hot_funcs.txt")
    if os.path.exists(os.path.join(work, "hookshot_pieces.prof")) and profile_readable(os.path.join(work, "hookshot_pieces.prof")):
        env["RX_PGO"] = os.path.join(work, "hookshot_pieces.prof")

    say("stage", "lift", "Translating the game to PC code")
    # (the same game, tools and settings as the lift before: its C is what this lift would write, and nothing recompiles from it. A
    # rebuild after a change to host/ alone skips the minutes of the lift)
    key = lift_key(exefs, work, env)
    gen_dir = os.path.join(work, "sa", "gen")
    # (issue 1197: a lifted file cut short, "g_module_b" where g_module_base was, stopped the compile at every try. Before the compile
    # every one must end as a function does: one that does not is translated again, once; a second time says what to check)
    for _ in range(2):
        if lifted_before(work, key):   # (never on the second pass: its key was taken away below)
            print("the game was translated with these tools before: translating it again is skipped", flush=True)
        else:
            key_file = os.path.join(work, "sa", "gen", LIFT_KEY)
            if os.path.exists(key_file):
                os.remove(key_file)   # (a lift stopped halfway leaves no key behind)
            # (hookshot) the lifted C of an earlier lift goes first: a file that lift made and this one does not (another builder's naming,
            # a chunk cut short) was compiled with the new ones, undefined or doubly defined game functions at the link (issue 1176).
            # The objects stay cached by their contents, so a file this lift writes the same is not compiled again
            gen_dir = os.path.join(work, "sa", "gen")
            if os.path.isdir(gen_dir):
                for f in os.listdir(gen_dir):
                    if f.startswith("code_") and (f.endswith(".c") or f.endswith(".c.whole") or f.endswith(".part")):
                        try:
                            os.remove(os.path.join(gen_dir, f))
                        except FileNotFoundError:
                            pass   # (already gone: another cleanup removed it)
                        except OSError as e:
                            fail("Could not remove earlier translated file %s: %s. The new translation has not started." %
                                 (os.path.join(gen_dir, f), e))
            run(PY + ["nx2/lift.py", "--standalone", "--write", "--exefs", exefs, "--work", work], env)
            if os.path.isfile(os.path.join(work, "sa", "gen", "code_hot.c")):
                run(PY + ["nx2/split_hot.py", os.path.join(work, "sa", "gen")], env)   # (eight files side by side: ~6 minutes, not 79)
            write_lift_key(work, key)
        cut = lifted_cut_short(gen_dir)
        if not cut:
            break
        key_file = os.path.join(gen_dir, LIFT_KEY)
        if os.path.exists(key_file):
            os.remove(key_file)
        print("translated files cut short (%s): the game is translated again" % ", ".join(cut[:6]), flush=True)
    else:
        fail("The translated game came out cut short twice (%s). Check that the drive with %s has free space, and that no antivirus "
             "and no second Hookshot Builder is working in that folder, then update again." % (", ".join(cut[:6]), work))

    if LINUX or DARWIN:
        check_linux_compiler()
    # (the compile's timer: build.py reads the record of the earlier builds on this PC, says which files this run really
    # rebuilds and how long the rest will take, and reports each module's seconds; they go into the record below)
    env["HOOKSHOT_TIMES"] = times_path(work)
    run_files, plan = {}, [0, 0]
    say("stage", "compile", "Compiling")
    compile_started = time.time()
    done = {"n": 0.0, "of": 1.0}
    # (the progress by each file's share of the compile time, not by the count of files: the build takes the biggest first, and
    # the 515 small files were 89% of the count and 10% of the time, so 45 of 579 files read as 8% when it was ~45%, and the
    # builder said "452 minutes left" an hour from the end. Seconds per MB measured on a full build: the eight hot files (-O2,
    # the play profile) 23.5, the other game files 3.4, the rest ~1.3 s each)
    gen = os.path.join(work, "sa", "gen")

    def cost(name, mb=None):
        if mb is None:
            try:
                mb = os.path.getsize(os.path.join(gen, name)) / (1 << 20)
            except OSError:
                mb = 0
        return 23.5 * mb if name.startswith("code_hot") else 3.4 * mb + 1 if name.startswith("code_") else 1.3

    def compiled(line):
        m = re.match(r"(\d+) files, ", line)
        if m:
            try:
                ours = [f for f in os.listdir(gen) if f.startswith("code_") and f.endswith(".c")]
            except OSError:
                ours = []
            done["of"] = sum(cost(f) for f in ours) + max(0, int(m.group(1)) - len(ours)) * 1.3
        else:
            m = re.match(r"\s+(\S+)\s+(\d+) MB\s+\d+s", line)
            if m:
                done["n"] += cost(m.group(1))
                say("progress", "%.3f" % min(1.0, done["n"] / max(1.0, done["of"])))
        if line.startswith("@@file "):
            parts = line.split(" ")
            if len(parts) == 4 and parts[3] in ("new", "again"):
                try:
                    seconds = float(parts[2])
                except ValueError:
                    return
                if seconds > 0:   # (a module a cache held is not a measurement of this PC)
                    run_files[parts[1]] = seconds
        elif line.startswith("@@plan "):
            parts = line.split(" ")
            if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                plan[:] = [int(parts[1]), int(parts[2])]
    try:
        run(PY + ["nx2/build.py", "--standalone", "--jobs", str(a.jobs)], env, compiled)
    except SystemExit:
        # (hookshot) a compile or link that failed forgets the lift: the next build translates the game again. A lifted file cut short
        # (an antivirus, a full disk, a stopped run: "g_module_b" for g_module_base, issue 1197) or lifted C another builder left (20
        # undefined game functions at the link, issue 1176) otherwise failed the same way at every try, the key still matching
        key_file = os.path.join(work, "sa", "gen", LIFT_KEY)
        if os.path.exists(key_file):
            os.remove(key_file)
        # (and its compiled objects go too: a cached runtime object from another version linked with every object "compiled in 0s"
        # and a64_dirty, a64_icall, a64_lookup, recomp_cntpct undefined, at every try (issue 1197, Linux, v2.0.10))
        for sub in (os.path.join(work, "objcache"), os.path.join(work, "sa", "build", "obj")):
            shutil.rmtree(sub, ignore_errors=True)
        print("the build failed: the next one translates and compiles the game again (nothing of this one is reused)", flush=True)
        raise
    compile_seconds = time.time() - compile_started

    say("stage", "finish", "Putting the game folder together")
    built = os.path.join(work, "sa", "build")
    # (the new files are copied in beside the old ones as <name>.new and swapped in only once all are complete: a build stopped while
    # copying, or a full disk, left a half-written 460 MB hookshot.exe and no game to play. The old game stays playable until the swap)
    # (Windows) hookshot.exe in the folder is the game's launcher: the builder's small setup, which opens the installed builder as a
    # launcher for this folder (Play, and Update left of it when a newer release is out: builder/setup/setup.c launch mode), or starts
    # the game when no builder is installed. The game and its DLLs are in bin\; its files (image.bin, romfs, saves, settings, caches)
    # stay in the folder (host/hos_paths.h). Without the setup (a development build) the game stays hookshot.exe in the folder
    staged = []
    # (Linux) the same launcher, as a script, when this is a packaged builder (the AppImage sets HOOKSHOT_TOOLS). A source
    # checkout leaves hookshot in the folder, as a development build on Windows does when the setup exe is not beside it
    launcher = os.path.join(os.path.dirname(os.path.abspath(ROOT)), "HookshotBuilder-Setup.exe")
    if LINUX:
        script = os.path.join(ROOT, "builder", "linux", "hookshot-folder")
        launcher = script if os.environ.get("HOOKSHOT_TOOLS") and os.path.isfile(script) else None
    else:
        launcher = launcher if os.path.isfile(launcher) else None
    game_dir = os.path.join(out, "bin") if launcher else out
    os.makedirs(game_dir, exist_ok=True)
    ffmpeg_dlls = [] if (LINUX or DARWIN) else sorted(f for f in os.listdir(built) if f.endswith(".dll") and f.startswith(("av", "sw")))
    for n in BESIDE + ffmpeg_dlls:
        src = os.path.join(built, n)
        if os.path.exists(src):
            staged.append((src, os.path.join(game_dir, n)))
    staged.append((os.path.join(work, "sa", "image", "image.bin"), os.path.join(out, "image.bin")))
    if launcher:
        staged.append((launcher, os.path.join(out, BESIDE[0])))
    for src, dst in staged:
        try:
            if os.path.exists(dst + ".new"):
                os.remove(dst + ".new")
            shutil.copy2(src, dst + ".new")
        except PermissionError:
            fail("Could not stage the new build at %s. Check that %s is readable and the staged file and output folder are writable, "
                 "close any program using that file, then retry. No installed files were replaced; the compiled source is still available."
                 % (dst + ".new", src))
    for src, dst in staged:
        try:
            os.replace(dst + ".new", dst)   # (linux: a running copy keeps its own file; windows: a running exe cannot be replaced)
        except PermissionError:
            fail("Could not replace %s. Close any running copy of Hookshot and check that the file and folder are writable, then retry. "
                 "Staged replacements remain beside the installed files; the compiled source remains at %s." % (dst, src))
    if launcher:   # (a folder built before the launcher: its libraries left the folder for bin\; hookshot is the launcher now)
        stale = [] if (LINUX or DARWIN) else sorted(f for f in os.listdir(out) if f.endswith(".dll") and f.startswith(("av", "sw")))
        for n in BESIDE[1:] + stale + ["hookshot.map", "hookshot-game.exe"]:
            try:
                if os.path.isfile(os.path.join(out, n)):
                    os.remove(os.path.join(out, n))
            except OSError:
                pass
    place_ngx_runtime(out)
    # every shader of the game, for its first start to translate (gpu/vk/vk_shader.cpp seed_open). Without it the game still runs, compiling them
    # as it meets them: not worth stopping a finished build for
    if run(shader_census_cmd(romfs, os.path.join(out, "hookshot_shaders.bin")), check=False, output=sys.stderr):
        print("the shader list was not made: the game will compile its shaders as it plays", flush=True)
    # (hookshot) the button prompts of other controllers (host/prompts.c): the game's icon font redrawn per controller, with fontTools.
    # Without it the game shows its own icons
    prompts = os.path.join(out, "prompts")
    shutil.rmtree(prompts, ignore_errors=True)
    if importlib.util.find_spec("fontTools") is None:
        print("the button prompts of other controllers were not made (no fontTools): the game shows its own", flush=True)
    elif run(PY + [os.path.join(HERE, "prompt_assets.py"), "--romfs", romfs, "--out", prompts], check=False, output=sys.stderr):
        print("the button prompts of other controllers were not made: the game shows its own", flush=True)
        shutil.rmtree(prompts, ignore_errors=True)
    icon = os.path.join(ROOT, "assets", "hookshot.png")
    if (LINUX or DARWIN) and os.path.exists(icon):   # (the window's icon: host/posix/display_sdl.c)
        copy_writable(icon, os.path.join(out, "hookshot.png"))   # (a second build overwrites the first's)
    seed_pipelines(out)
    ship_state_list(out)
    language = os.path.join(out, "language.txt")   # (the same text as host/nn_applet.c writes)
    with open(language, "w", encoding="utf-8", newline="\n") as f:
        f.write("# The game's language. Change the line below to one of the codes listed here, save, and start the game again.\n\n%s\n\n" % a.language)
        f.writelines("# %-8s %s\n" % l for l in LANGUAGES)
    # (what the game's update offer reads, host/hos_update.c: which release these tools are, and where the builder that made the folder is)
    tag = ""
    for version_name in ("version.txt", "VERSION"):   # (VERSION: the AppImage, which has no version.txt)
        version = os.path.join(ROOT, version_name)
        if os.path.isfile(version):
            with open(version, encoding="utf-8") as f:
                tag = f.readline().strip()
            if tag:
                break
    if tag:
        with open(os.path.join(out, "hookshot_version.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("version=%s\n" % tag)
            if os.environ.get("HOOKSHOT_BUILDER_EXE"):
                f.write("builder=%s\n" % os.environ["HOOKSHOT_BUILDER_EXE"])
                # (the Python builder: builder is its pythonw.exe, and these the arguments before --update, host/hos_update.c)
                if os.environ.get("HOOKSHOT_BUILDER_ARGS"):
                    f.write("builder_args=%s\n" % os.environ["HOOKSHOT_BUILDER_ARGS"])
    # (the game's code as read: written again by every build, so not left behind in the work folder. The translated code (sa\gen)
    # and the compiled objects stay: the next build skips the lift when nothing it reads changed (#428) and compiles only what
    # changed; the builder says how much stays and lets it go. Kept in a development checkout)
    if os.path.normcase(work) != os.path.normcase(os.path.abspath(os.path.join(ROOT, "work"))):
        shutil.rmtree(exefs, ignore_errors=True)
        # (players asked for the space back: the translated code (1.5 GB) goes once the game is ready, on Windows and Linux alike. The
        # compiled objects of this build stay (~1 GB; those of earlier builds go): without them every update compiled all ~600 files
        # again, an hour and more on many PCs (issue 1287, "updates rebuild everything"), where the update changes a few. The next
        # update translates again (minutes) and compiles only what changed. The builder's Free up space lets them go too.
        # HOOKSHOT_KEEP_BUILD_FILES=1 keeps everything, as before)
        if os.environ.get("HOOKSHOT_KEEP_BUILD_FILES", "0") in ("", "0"):
            kept = prune_object_cache(work)
            for sub in ("sa", "probe"):
                shutil.rmtree(os.path.join(work, sub), ignore_errors=True)
            print("the build files in %s were deleted but this build's compiled objects (%d MB), so that an update compiles only what "
                  "changed (HOOKSHOT_KEEP_BUILD_FILES=1 keeps all)" % (work, kept >> 20), flush=True)
    total_seconds = time.time() - STARTED
    previous = record_times(work, run_files, compile_seconds, total_seconds, modules=plan[1],
                            kind="update" if a.update else "build")
    print("the build took %s, compiled in %s%s" % (clock(total_seconds), clock(compile_seconds),
                                                    "" if previous is None else " (the last one %s)" % clock(previous)), flush=True)
    say("times", "%.0f" % total_seconds, "%.0f" % compile_seconds, "-1" if previous is None else "%.0f" % previous)
    # (after the times: they stay comparable from build to build, without a GPU's minutes that can be switched off)
    skipped = prepare_skipped(a)
    if skipped:
        not_prepared(skipped)
    else:
        prepare_shaders([os.path.join(game_dir, BESIDE[0]), "--prepare-shaders"], out)
    if DARWIN:
        try:
            import make_app
            make_app.make_app(out)
        except Exception as e:
            print("note: could not create Hookshot.app bundle: %s" % e, flush=True)
    say("done", out)


def cli():
    # (an error nobody foresaw is said in the window, not as "The game files could not be read" or "something went wrong" with the reason
    # only in a console nobody sees: the traceback's last lines go to Show details, its last line to the message)
    with contextlib.ExitStack() as stack:
        try:
            for stream in (sys.stdout, sys.stderr):
                try:
                    stream.reconfigure(encoding="utf-8", errors="replace")   # (-I ignores PYTHONIOENCODING: a path's letters crashed a print)
                except (AttributeError, ValueError):
                    pass
            a = parse_args()
            stack.enter_context(build_log(a.log))
            main(a)
        except SystemExit as e:
            # (fail() exits with a number: it already said @@error. A library's SystemExit (toolchain.need) carries its message as
            # text, which would reach only stderr; the builder app does not show that, and said "The game files could not be read")
            if isinstance(e.code, str):
                say("error", e.code)
                sys.exit(1)
            raise
        except BaseException as e:
            import traceback
            print(traceback.format_exc(), flush=True)
            say("error", "The builder stopped on an error it did not expect: %s: %s. Please send the text under Show details to the "
                "Hookshot issues page." % (type(e).__name__, str(e)[:300]))
            sys.exit(1)


if __name__ == "__main__":
    cli()
