"""Native scene resolution for Ocarina of Time 1.1.1 (v131072): Resolution 100% renders the 3D at the picture's size.

From oscarrc91's PR #578 (native scene base scale) and i900gaming's PR #329 (stale fixed-resolution scale); both switches are
host globals (host/nn_vi.c, hos_main.c) instead of environment reads in the game's code.

- The graphics configuration has a scale table apart from the GPU-time controller: (1.0, 0.8, 2/3) for each axis, in two
  profiles. The game runs in mode 1, so even the fixed path's 100% sized the scene at 0.8 of the picture (2048x1152 in
  2560x1440). f_806702e0 picks the mode and tells the resources about a change: with hos_native_scene set it changes mode 1's
  0.8 to 1.0 (after checking the whole stock table) and makes the mode compare unequal once, so the game's own notification
  runs and the targets are made again at the new size.
- f_831f3200, the scene's update: the fixed path can ask for a resource refresh without marking the scene's cached scale
  dirty, so the last dynamic scale stayed (0.75: 1536x864). With hos_fix_res set, a cached scale that differs from the one
  asked for sets the scale-dirty bit (8) and the game's own code recomputes it.
Another game version leaves the functions out (and says so).
"""
import glob
import os
import whole_write   # (rewrites written beside and moved over: issue 1197)

CONFIG_HEAD = "void f_806702e0(Ctx *__restrict A64_NOESC c) {"
CONFIG_ANCHOR = "    c->x[14]=recomp_load8(c,c->x[0] + 1354);\n"
CONFIG_DECL = "extern volatile int hos_native_scene;\nextern void hos_log(const char *, ...);\n"
CONFIG_PATCH = """    /* (nx2/oot_native_resolution.py: mode 1's base scale 0.8 -> 1.0, PR #578) */
    if (hos_native_scene) {
        for (unsigned _profile = 0; _profile < 2; ++_profile) {
            const uint64_t _table = c->x[0] + 724 + _profile * 520;
            if (recomp_load64(c, _table) == 0x3f8000003f800000ULL &&
                recomp_load64(c, _table + 8) == 0x3f4ccccd3f4ccccdULL &&
                recomp_load64(c, _table + 16) == 0x3f2aaaab3f2aaaabULL) {
                recomp_store64(c, _table + 8, 0x3f8000003f800000ULL);
                c->x[14] = 0xff;   /* (the old mode compares unequal once: the game's own refresh runs) */
                hos_log("native-scene: profile %u mode 1 base scale 0.8 -> 1.0", _profile);
            }
        }
    }
"""

SCENE_HEAD = "void f_831f3200(Ctx *__restrict A64_NOESC c) {"
SCENE_DECL = "extern volatile int hos_fixed_resolution;\nextern volatile int hos_fix_res;\nextern volatile uint32_t hos_fixed_scale_bits;\n"
SCENE_PATCH = """
    /* (nx2/oot_native_resolution.py: the fixed scale marked dirty when the cached one differs, PR #329) */
    if (hos_fixed_resolution && hos_fix_res) {
        float _req, _base, _ref, _prev; uint32_t _u = hos_fixed_scale_bits; memcpy(&_req, &_u, 4);
        _u = recomp_load32(c, c->x[0] + 3664); memcpy(&_base, &_u, 4);
        _u = recomp_load32(c, c->x[0] + 3672); memcpy(&_ref, &_u, 4);
        _u = recomp_load32(c, c->x[0] + 3676); memcpy(&_prev, &_u, 4);
        if (_base > 0.0f && _ref > 0.0f && _req > 0.0f && _req <= 2.0f && _prev != _req * _ref / _base)
            recomp_store32(c, c->x[0] + 3628, recomp_load32(c, c->x[0] + 3628) | 8u);
    }
"""
HEADER = '#include "a64.h"\n'


def _body(s, head):
    start = s.index(head)
    end = s.find("\nvoid f_", start + len(head))
    return start, s[start:end if end >= 0 else len(s)]


def patch_config(s):
    """None when the file has no such function; s unchanged when its code differs"""
    if CONFIG_HEAD not in s:
        return None
    start, body = _body(s, CONFIG_HEAD)
    if CONFIG_PATCH in body or body.count(CONFIG_ANCHOR) != 1 or "goto L_80670648;" not in body or s.count(HEADER) != 1:
        return s
    at = start + body.index(CONFIG_ANCHOR) + len(CONFIG_ANCHOR)
    s = s[:at] + CONFIG_PATCH + s[at:]
    return s.replace(HEADER, HEADER + CONFIG_DECL, 1)


def patch_scene(s):
    if SCENE_HEAD not in s:
        return None
    if SCENE_PATCH in s or s.count(SCENE_HEAD) != 1 or s.count(HEADER) != 1:
        return s
    s = s.replace(SCENE_HEAD, SCENE_HEAD + SCENE_PATCH, 1)
    return s.replace(HEADER, HEADER + SCENE_DECL, 1)


def apply(gen):
    done = {"scene base scale (f_806702e0)": 0, "scene scale check (f_831f3200)": 0}
    for path in sorted(glob.glob(os.path.join(glob.escape(gen), "code_*.c"))):
        with open(path, encoding="utf-8", newline="") as f:
            s = f.read()
        out = s
        for what, fn in (("scene base scale (f_806702e0)", patch_config), ("scene scale check (f_831f3200)", patch_scene)):
            r = fn(out)
            if r is not None and r != out:
                out = r
                done[what] += 1
                print("oot_native_resolution: %s in %s" % (what, os.path.basename(path)))
        if out != s:
            whole_write.write_whole(path, out, newline="")
    for what, n in done.items():
        if n != 1:
            print("oot_native_resolution: WARNING: the %s was found %d times" % (what, n))
