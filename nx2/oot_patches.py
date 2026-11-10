"""Changes to the lifted C for Ocarina of Time, applied by lift.py after it writes the code (and by hand: python -I nx2/oot_patches.py).

Each is a runtime switch where it can be, so the game's own path stays reachable.

- Dynamic resolution (Lichii's built-in "Max Resolution" patch, main+0x805BD0): the engine's config flag at +0x94 picks the path that
  follows the GPU-time controller; with hos_fixed_resolution set it takes the other path, the 3D at full scale. The controller made
  a new set of render targets at each size, ~11 images a frame at times, and held the GPU near its budget.
- Text speed (the Insert menu's "Text speed"): f_80b1e140 (main+0xafe140) steps a text pane's letter animation, the
  LetterAnimControl of the panes with "LetterAnimOn" user data (dialogue, Navi, signs). Its time argument (s0) moves the
  letters' clock (+0x60 += rate +0x4c * time, the rate from the message's speed tag) and the pauses' timer (+0x58 -= time);
  hos_text_scale multiplies it, 1.0 as shipped. The auto-advance timer (+0x5c, before) keeps the game's time. A huge
  scale shows a page at once (one frame per pause), as the game's own skip on A (+0x72 = 2, f_80794b00) without its flags.
- The fixed path's scale (hos_fixed_scale_bits: the Insert menu's Resolution) reaching the 3D, in the caller f_831f3200
  (main+0x31d3200). It recomputes the 3D's scale (+0xe5c = scale * +0xe58 / +0xe50) only while +0xe2c bit 3 is set. The dynamic
  path sets it on a level change; the fixed path's flag 1 calls f_831f41d0, whose bit 3 the apply block clears in the same frame,
  before any recompute. So the fixed path kept the dynamic path's last scale (0.75 docked: 1536x864 at every setting). Flag 1 now
  also asks for the recompute, and on the fixed path the flags +0xe20 bits 3/4 (a hardcoded 0.75 / 0.5 in place of the scale)
  are not looked at.
"""
import glob
import os
import sys
import whole_write   # (rewrites written beside and moved over: issue 1197)

DECL = "extern volatile int hos_fixed_resolution;\nextern volatile int hos_dynres_runs;\nextern volatile uint32_t hos_fixed_scale_bits;\n"
OLD = "if (!((c->x[8] >> 0) & 1)) { goto L_8082640c; }"
NEW = "if (hos_fixed_resolution || !((c->x[8] >> 0) & 1)) { goto L_8082640c; }\n    hos_dynres_runs++;"
LABEL = "L_8082640c:;"
SCALE_OLD = "c->x[9] = 0x3f800000ULL;"
SCALE_NEW = "c->x[9] = hos_fixed_scale_bits;"   # (the fixed path's scale, 1.0 as shipped)
DECL2 = "extern volatile int hos_fixed_resolution;\nextern volatile uint64_t hos_res_module;\nextern volatile uint32_t hos_fixed_scale_bits;\n"
APPLY_OLD = "L_831f3efc:;\n    c->x[9]=recomp_load32(c,c->x[20] + 3628);"
APPLY_NEW = "L_831f3efc:;\n    if (hos_fixed_resolution) {   /* (only while +0xe5c is not the chosen scale: a recompute every frame remade the targets) */\n        union { uint32_t u; float f; } now = {(uint32_t)recomp_load32(c,c->x[20] + 3676)}, want = {hos_fixed_scale_bits},\n            e50 = {(uint32_t)recomp_load32(c,c->x[20] + 3664)}, e58 = {(uint32_t)recomp_load32(c,c->x[20] + 3672)};\n        const float d = now.f - (e50.f != 0 ? want.f * e58.f / e50.f : want.f);\n        if (d > 1e-4f || d < -1e-4f) c->x[8] |= 8;\n    }\n    c->x[9]=recomp_load32(c,c->x[20] + 3628);"
FLAGS_OLD = "L_831f3f08:;\n    c->x[8]=recomp_load64(c,c->x[20] + 3616);\n"
FLAGS_NEW = FLAGS_OLD + "    hos_res_module = c->x[20];\n    if (hos_fixed_resolution) c->x[8] &= ~0x18ULL;\n"


def fixed_scale(t):
    """The fixed path's scale reaching the 3D (the Resolution row). (t, 1) when applied here"""
    if APPLY_OLD not in t or FLAGS_OLD not in t:
        return t, 0
    t = t.replace(APPLY_OLD, APPLY_NEW, 1).replace(FLAGS_OLD, FLAGS_NEW, 1)
    return t.replace('#include "a64.h"\n', '#include "a64.h"\n' + DECL2, 1), 1

TEXT_DECL = "extern volatile float hos_text_scale;\nextern void hos_oot_text_pane(Ctx *c, uint64_t anim);\n"
LIFE_BUILD_ID = "e0f3ccfaf50065ae4ea01eb5aeb13b1a45da3348"
LIFE_HEAD = "void f_804bd8c0(Ctx *__restrict A64_NOESC c) {\n"
MOVE_HEAD = "void f_82c415e0(Ctx *__restrict A64_NOESC c) {\n"
MOVE_ANCHOR = ("if (((c->x[8] >> 1) & 1)) { goto L_82c41748; }\n")
MOVE_MATRIX = "L_82c41778:;\n"
WARP_HEAD = "void f_806d2530(Ctx *__restrict A64_NOESC c) {\n"
WARP_ANCHOR = "{ uint64_t _t = c->x[8]; c->x[30] = 0x806d25c8ULL; A64_ICALL(c, _t); }\n"
VIEW_HEAD = "void f_804e48c0(Ctx *__restrict A64_NOESC c) {\n"
# (the head of the view's loop: a bare label, since nx2/poll.py puts the interrupt poll before each backward goto; with the
# poll after the label in C lifted before that)
VIEW_ANCHORS = ("L_804e5068:;\n", "L_804e5068:; A64_POLL(c);\n")
LIFE_CAS = ("{ uint64_t _a = c->x[13]; uint32_t _e = (uint32_t)c->x[11]; "
            "__atomic_compare_exchange_n((uint32_t *)A64_PTR(_a), &_e, (uint32_t)c->x[12], "
            "0, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST); A64_MARK(_a, 4); c->x[11] = (uint64_t)_e; }")


def patch_life(source):
    start = source.find(LIFE_HEAD)
    if start < 0:
        return None
    end = source.find("\n}", start)
    if end < 0 or source[start:end].count(LIFE_CAS) != 2:
        return None
    # x19 is the actor. Confirm its type and life pointer before protecting this write.
    guard = ("    if ((uint32_t)c->x[12] < (uint32_t)c->x[11] && hos_oot_hearts_enabled() &&\n"
             "        hos_oot_is_player(c, c->x[19]) &&\n"
             "        c->x[13] == recomp_load64(c,c->x[19] + 7184) + 8)\n"
             "        c->x[12] = c->x[11];\n")
    body = source[start:end].replace(LIFE_CAS, guard + LIFE_CAS)
    return (source[:start] + body + source[end:]).replace(
        '#include "a64.h"\n', '#include "a64.h"\nextern int hos_oot_hearts_enabled(void);\n'
        'extern int hos_oot_is_player(Ctx *c, uint64_t actor);\n', 1)


def patch_movement(source):
    start = source.find(MOVE_HEAD)
    if start < 0:
        return None
    end = source.find("\n}", start)
    if end < 0 or source[start:end].count(MOVE_ANCHOR) != 1 or source[start:end].count(MOVE_MATRIX) != 1:
        return None
    bypass = ("    hos_oot_lift_player(c, c->x[19]);\n"
              + MOVE_ANCHOR)
    body = source[start:end].replace(MOVE_ANCHOR, bypass, 1).replace(
        MOVE_MATRIX, MOVE_MATRIX + "    hos_oot_flight_pose(c, c->x[19], c->x[25]);\n", 1)
    source = source[:start] + body + source[end:]
    return source.replace('#include "a64.h"\n', '#include "a64.h"\n'
                          'extern void hos_oot_lift_player(Ctx *c, uint64_t actor);\n'
                          'extern void hos_oot_flight_pose(Ctx *c, uint64_t actor, uint64_t matrix);\n', 1)


def patch_flight_rotation(source):
    start = source.find(WARP_HEAD)
    if start < 0:
        return None
    end = source.find("\n}", start)
    body = source[start:end]
    if end < 0 or body.count(WARP_ANCHOR) != 1:
        return None
    body = body.replace(WARP_ANCHOR, "    hos_oot_flight_rotation(c, c->x[0], c->x[1]);\n" + WARP_ANCHOR)
    return (source[:start] + body + source[end:]).replace(
        '#include "a64.h"\n', '#include "a64.h"\n'
        'extern void hos_oot_flight_rotation(Ctx *c, uint64_t controller, uint64_t matrix);\n', 1)


def patch_view(source):
    start = source.find(VIEW_HEAD)
    if start < 0:
        return None
    end = source.find("\n}", start)
    body = source[start:end]
    if end < 0:
        return None
    for anchor in VIEW_ANCHORS:
        if body.count(anchor) == 1:
            break
    else:
        return None
    body = body.replace(anchor, anchor + "    hos_oot_free_view(c, c->x[20]);\n")
    return (source[:start] + body + source[end:]).replace(
        '#include "a64.h"\n', '#include "a64.h"\nextern void hos_oot_free_view(Ctx *c, uint64_t view);\n', 1)

# Native mouse look (host/mouse_native.c): the player camera's update, f_80644c80 (a virtual method, the camera in x0), hands
# its camera to the host before anything else, on the game's thread, once a frame; with the menu's Mouse camera on the mouse's
# motion turns the camera's yaw (+0x1a4) and pitch (+0x18c) there, before the camera reads its input.
CAM_HEAD = "void f_80644c80(Ctx *__restrict A64_NOESC c) {\n"


def patch_mouse_camera(source):
    start = source.find(CAM_HEAD)
    if start < 0:
        return None
    if "hos_mouse_camera(c->x[0]);" in source:   # (made before: a lift patched again)
        return source
    at = start + len(CAM_HEAD)
    source = source[:at] + "    hos_mouse_camera(c->x[0]);   /* (nx2/oot_patches.py: native mouse look) */\n" + source[at:]
    return source.replace('#include "a64.h"\n', '#include "a64.h"\nextern void hos_mouse_camera(uint64_t camera);\n', 1)


# The camera's state-3 yaw follow: after f_80642c80's authored heading override (the branch to 0x806492c4), the block at
# 0x8064720c derives a heading from Link's movement and eases yaw (+0x1a4) through f_80642410 at 0x806475e4. Skip only
# the movement path, restoring x25's parameter base as that path does, and join the other yaw paths at 0x80645ad8.
# State 4's stick, state 2's explicit recenter and authored heading overrides stay intact; pitch and collision follow.
CAM_FOLLOW_ANCHOR = "L_8064720c:;\nif (!c->z) { goto L_806492c4; }\n"
CAM_FOLLOW_JOIN = "L_80645ad8:;"
CAM_FOLLOW_HOOK = ("    if (hos_disable_camera_centering()) { c->x[25] = c->x[26]; goto L_80645ad8; }"
                   "   /* (nx2/oot_patches.py: disable camera centering) */\n")


def patch_camera_centering(source):
    start = source.find(CAM_HEAD)
    if start < 0:
        return None
    end = source.find("\n}", start)
    if end < 0:
        return None
    body = source[start:end]
    if body.count(CAM_FOLLOW_ANCHOR) != 1 or body.count(CAM_FOLLOW_JOIN) != 1:
        return None
    if CAM_FOLLOW_HOOK in body:
        return source
    body = body.replace(CAM_FOLLOW_ANCHOR, CAM_FOLLOW_ANCHOR + CAM_FOLLOW_HOOK, 1)
    return (source[:start] + body + source[end:]).replace(
        '#include "a64.h"\n', '#include "a64.h"\nextern int hos_disable_camera_centering(void);\n', 1)


MENU_FOCUS_HEAD = "void f_802ed660(Ctx *__restrict A64_NOESC c) {\n"


def patch_menu_focus(source):
    """f_802ed660, a menu screen's handler of a pane getting the focus (host/oot_menu.c), calls
    hos_oot_menu_focus first, with the screen, the pane and its caller's return address"""
    start = source.find(MENU_FOCUS_HEAD)
    if start < 0:
        return None
    if "hos_oot_menu_focus(c," in source:   # (made before: a lift patched again)
        return source
    at = start + len(MENU_FOCUS_HEAD)
    hook = "    hos_oot_menu_focus(c, c->x[0], c->x[1], c->x[30]);   /* (nx2/oot_patches.py: the menus' focus) */\n"
    return (source[:at] + hook + source[at:]).replace(
        '#include "a64.h"\n', '#include "a64.h"\nextern void hos_oot_menu_focus(Ctx *c, uint64_t screen, uint64_t pane, uint64_t lr);\n', 1)


MENU_TICK_HEAD = "void f_802f1380(Ctx *__restrict A64_NOESC c) {\n"


def patch_menu_tick(source):
    """f_802f1380, a menu screen's update (each frame, before the screen's UI controller: +56, its vtable's
    +16), calls hos_oot_menu_tick first with the screen: the game's menus' mouse (host/oot_menu.c)"""
    start = source.find(MENU_TICK_HEAD)
    if start < 0:
        return None
    if "hos_oot_menu_tick(c," in source:   # (made before: a lift patched again)
        return source
    at = start + len(MENU_TICK_HEAD)
    hook = "    hos_oot_menu_tick(c, c->x[0]);   /* (nx2/oot_patches.py: the menus' mouse) */\n"
    return (source[:at] + hook + source[at:]).replace(
        '#include "a64.h"\n', '#include "a64.h"\nextern void hos_oot_menu_tick(Ctx *c, uint64_t screen);\n', 1)


TEXT_HEAD = "void f_80b1e140(Ctx *__restrict A64_NOESC c) {"
# (the letters' block: past the early returns, the auto-advance timer and the hidden / no-text checks; reached once a call)
TEXT_OLD = ("L_80b1e1b4:;\n"
            "    c->x[9]=recomp_load16(c,c->x[19] + 110);\n"
            "if ((uint32_t)c->x[9] == 0) { goto L_80b1e18c; }\n")
# (the same block in a build with interrupt polls: nx2/poll.py puts the poll before each backward goto, as a block)
TEXT_OLD_POLLED = TEXT_OLD.replace("{ goto L_80b1e18c; }", "{ { A64_POLL(c); goto L_80b1e18c; } }")
TEXT_ADD = ("    if (hos_text_scale != 1.0f) { float _t; uint32_t _u; memcpy(&_t,c->vreg[0],4); _t *= hos_text_scale; "
            "memcpy(&_u,&_t,4); a64_vset64(c->vreg[0],_u); }   /* (nx2/oot_patches.py: text speed) */\n"
            "    hos_oot_text_pane(c, c->x[19]);   /* (nx2/oot_patches.py: text size; x19 the LetterAnimControl) */\n")
TEXT_NEW = TEXT_OLD + TEXT_ADD


def patch_dynres(s):
    if OLD not in s:
        return None
    s = s.replace(OLD, NEW, 1)
    at = s.index(LABEL)
    scale = s.index(SCALE_OLD, at)
    s = s[:scale] + SCALE_NEW + s[scale + len(SCALE_OLD):]
    return s.replace('#include "a64.h"\n', '#include "a64.h"\n' + DECL, 1)


# The frame's real time in place of the nominal rate, for a Frame rate cap above 60 (host/nn_vi.c hos_frame_seconds_bits; 0, as
# at a cap of 60: the game's own divide, nothing changes). The engine has two places where its integer nominal rate (+0x2c8 of
# the graphics module) becomes a time step, both a float divide "base / nominal":
# - f_80706be0: the frame's step, base 60.0 (30.0 in the half-rate mode), added to the game clock (the double at
#   [x19+0xd58], in 1/60 s) and handed on as the frame's seconds;
# - f_83b6ea90: the global step (60.0 / nominal, a float in .data) the rest of the engine reads.
# The engine's own rate is 60 / <whole display intervals>, never above 60, and its controller puts 60 back over a higher value
# written from outside before either divide runs: above 60 fps every frame still stepped 1/60 s and the game ran fps / 60 times
# too fast. With the host's measured frame time the step is base * seconds, whatever the rate. hos_step_probe: f_80706be0's
# x19, which tells the host the hook is in this build and gives it the game clock for its log (HOS_FPS_LOG=1).
STEP_SITES = (("void f_80706be0(Ctx *__restrict A64_NOESC c) {\n", 8, "\n    hos_step_probe = c->x[19];"),
              ("void f_83b6ea90(Ctx *__restrict A64_NOESC c) {\n", 0, ""))
STEP_OLD = "    _v=a64_fpx_div32_div32(c,_a,_b);\n    a64_vset64(c->vreg[%d],_v);}"
STEP_HOOK = ("    _v=a64_fpx_div32_div32(c,_a,_b);\n"
             "    { const uint32_t _hs = hos_frame_seconds_bits; if (_hs) { float _base, _secs; uint32_t _w; memcpy(&_base,&_a,4); "
             "memcpy(&_secs,&_hs,4); _base *= _secs; memcpy(&_w,&_base,4); _v = _w; } }   /* (base * the frame's seconds: nx2/oot_patches.py) */\n"
             "    a64_vset64(c->vreg[%d],_v);}")
STEP_MARK = "hos_frame_seconds_bits; if (_hs)"   # (once per divide with the hook)
STEP_DECL = "extern volatile uint32_t hos_frame_seconds_bits;\nextern volatile uint64_t hos_step_probe;\n"


def patch_frame_seconds(s):
    """The host's frame time at the step divides of f_80706be0 and f_83b6ea90: (s, the sites patched here). A site whose
    function is not in the file, is patched already, or whose code differs (another game version) is left as it is."""
    done = 0
    for head_text, reg, extra in STEP_SITES:
        head = s.find(head_text)
        if head < 0:
            continue
        end = s.find("\nvoid f_", head + len(head_text))
        body = s[head:end if end >= 0 else len(s)]
        old, new = STEP_OLD % reg, STEP_HOOK % reg + extra
        if new in body or body.count(old) != 1 or body.count("a64_fpx_div32_div32") != 1:
            continue
        at = head + body.index(old)
        s = s[:at] + new + s[at + len(old):]
        done += 1
    if done and STEP_DECL not in s:
        s = s.replace('#include "a64.h"\n', '#include "a64.h"\n' + STEP_DECL, 1)
    return s, done


def unpatch_frame_seconds(s):
    """s without the hook, as the lift wrote it: for a lift where only one of the two divides was found (apply)"""
    for _, reg, extra in STEP_SITES:
        s = s.replace(STEP_HOOK % reg + extra, STEP_OLD % reg)
    return s if STEP_MARK in s else s.replace(STEP_DECL, "", 1)   # (a hook of another shape stays, with its declarations)


# A movie's frame count above a 60 cap. The game's movie player counts its updates while a movie plays (f_83b7c710: one more
# at +760 of the player each frame), and a cutscene that shows a movie takes that count as its timeline's frame (f_83b5ec10,
# f_83b5e9a0): the narration, the rumble and the cutscene's end are placed by it. The movie itself follows the clock, so above
# 60 fps those cues ran ahead of the picture, fps / 60 times too fast (issue 1742). The count now grows by the frames' time, as
# the game's clock does (hos_movie_frames, host/nn_vi.c: 1 as before while the host gives no frame time).
MOVIE_HEAD = "void f_83b7c710(Ctx *__restrict A64_NOESC c) {\n"
# (the load and the add alone: the store after them is rewritten by the page marks' pass, which runs after these edits)
MOVIE_OLD = ("    c->x[8]=recomp_load32(c,c->x[20] + 760);\n"
             "    { uint64_t _a=c->x[8], _b=1ULL; uint64_t _r=_a+_b; _r&=0xFFFFFFFFULL; c->x[8]=_r; }\n")
MOVIE_NEW = MOVIE_OLD.replace("_b=1ULL", "_b=hos_movie_frames(c->x[20])")
MOVIE_DECL = "uint32_t hos_movie_frames(uint64_t player);\n"


def patch_movie_frames(s):
    """The movie player's count by the frames' time; None when the file has no such function, s unchanged when the function is
    there but its code differs (another game version) or has the patch already."""
    head = s.find(MOVIE_HEAD)
    if head < 0:
        return None
    end = s.find("\nvoid f_", head + len(MOVIE_HEAD))
    body = s[head:end if end >= 0 else len(s)]
    if body.count(MOVIE_OLD) != 1:
        return s
    at = head + body.index(MOVIE_OLD)
    s = s[:at] + MOVIE_NEW + s[at + len(MOVIE_OLD):]
    return s if MOVIE_DECL in s else s.replace('#include "a64.h"\n', '#include "a64.h"\n' + MOVIE_DECL, 1)


def patch_text_speed(s):
    """The scale at the head of the letters' block of f_80b1e140 (Text speed), and the call to hos_oot_text_pane after it
    (Text size: host/oot_text_size.c); None when the file has no such function, s unchanged when the
    function is there but its code differs (another game version)."""
    head = s.find(TEXT_HEAD)
    if head < 0:
        return None
    end = s.find("\nvoid f_", head + len(TEXT_HEAD))
    body = s[head:end if end >= 0 else len(s)]
    for old in (TEXT_OLD_POLLED, TEXT_OLD):   # (with the interrupt poll before the block's backward goto, or without: --no-polls)
        if old + TEXT_ADD in body:   # (applied already: a second run)
            return s
        if body.count(old) == 1:
            break
    else:
        return s
    if body.count("goto L_80b1e1b4;") != 1:
        return s
    at = head + body.index(old)
    s = s[:at] + old + TEXT_ADD + s[at + len(old):]
    return s.replace('#include "a64.h"\n', '#include "a64.h"\n' + TEXT_DECL, 1)


def apply(gen, *, protect_hearts=False, required=False):
    """required: the lift of the supported build (LIFE_BUILD_ID), whole: a missing output-size edit stops it (apply_output_size).
    The other patches only warn when their place is not found once."""
    import oot_native_resolution   # (HOS_SCENE_NATIVE=1: the scene's base scale 1.0; off by default since #849's output resolution)
    oot_native_resolution.apply(gen)
    done = {"dynamic resolution branch": 0, "text speed block": 0, "fixed path's scale": 0, "movie's frame count": 0}
    if protect_hearts:   # (the supported build's: these places are its functions)
        done["menu focus hook"] = 0
        done["menu tick hook"] = 0
        done["player heart protection"] = 0
        done["player flight"] = 0
        done["player flight rotation"] = 0
        done["free camera"] = 0
        done["mouse camera"] = 0
        done["disable camera centering"] = 0
    step_sites, step_files = 0, []   # (the divides with the hook, and the files that have it)
    for path in sorted(glob.glob(os.path.join(glob.escape(gen), "code_*.c"))):
        with open(path, encoding="utf-8", newline="") as f:
            s = f.read()
        out = s
        d = patch_dynres(out)
        if d is not None:
            out = d
            done["dynamic resolution branch"] += 1
            print("oot_patches: dynamic resolution switch in", os.path.basename(path))
        t = patch_text_speed(out)
        if t is not None and t != out:
            out = t
            done["text speed block"] += 1
            print("oot_patches: text speed scale and text size in", os.path.basename(path))
        focus = patch_menu_focus(out) if protect_hearts else None
        if focus is not None:
            out = focus
            done["menu focus hook"] += 1
            print("oot_patches: the menus' focus hook in", os.path.basename(path))
        tick = patch_menu_tick(out) if protect_hearts else None
        if tick is not None:
            out = tick
            done["menu tick hook"] += 1
            print("oot_patches: the menus' update hook in", os.path.basename(path))
        movie = patch_movie_frames(out)
        if movie is not None:
            if MOVIE_NEW in movie:   # (made now, or by an earlier run over this file)
                done["movie's frame count"] += 1
            if movie != out:
                print("oot_patches: the movie's frame count by the frames' time in", os.path.basename(path))
            out = movie
        out, n = fixed_scale(out)
        if n:
            done["fixed path's scale"] += 1
            print("oot_patches: the fixed path's scale in", os.path.basename(path))
        life = patch_life(out) if protect_hearts else None
        if life is not None:
            out = life
            done["player heart protection"] += 1
            print("oot_patches: player heart protection in", os.path.basename(path))
        move = patch_movement(out) if protect_hearts else None
        if move is not None:
            out = move
            done["player flight"] += 1
            print("oot_patches: player flight in", os.path.basename(path))
        rotation = patch_flight_rotation(out) if protect_hearts else None
        if rotation is not None:
            out = rotation
            done["player flight rotation"] += 1
            print("oot_patches: player flight rotation in", os.path.basename(path))
        mouse = patch_mouse_camera(out) if protect_hearts else None
        if mouse is not None:
            out = mouse
            done["mouse camera"] += 1
            print("oot_patches: native mouse camera in", os.path.basename(path))
        center = patch_camera_centering(out) if protect_hearts else None
        if center is not None:
            out = center
            done["disable camera centering"] += 1
            print("oot_patches: disable camera centering switch in", os.path.basename(path))
        view = patch_view(out) if protect_hearts else None
        if view is not None:
            out = view
            done["free camera"] += 1
            print("oot_patches: free camera in", os.path.basename(path))
        out, sites = patch_frame_seconds(out)
        if STEP_MARK in out:   # (made now, or by an earlier run over this file)
            step_sites += out.count(STEP_MARK)
            step_files.append(path)
        if sites:
            print("oot_patches: the frame's time at %d step divide(s) in %s" % (sites, os.path.basename(path)))
        if out != s:
            whole_write.write_whole(path, out, newline="")
    for what, n in done.items():
        if n != 1:
            print("oot_patches: WARNING: the %s was found %d times" % (what, n))
    if step_sites != len(STEP_SITES):
        # (both or neither: with one divide timed and the other stepping 1/60 s the two clocks of the game would run apart. Without
        # the hook the host keeps the rate up to the cap, as before: host/nn_vi.c, hos_step_probe)
        for path in step_files:
            with open(path, encoding="utf-8", newline="") as f:
                s = f.read()
            whole_write.write_whole(path, unpatch_frame_seconds(s), newline="")
        print("oot_patches: WARNING: the frame's time was found at %d of %d step divides, none patched (a Frame rate cap above 60 "
              "keeps the game's own step)" % (step_sites, len(STEP_SITES)))
    apply_output_size(gen, required=required)


# Output size (host/nn_applet.c hos_output_size: the Insert menu's Output resolution, 2560 x 1440 as shipped):
# - nnMain (f_81222ce0) puts the display size in the framework's create arg (+20/+24, the framework's +156/+160); the window
#   textures are made at it.
# - f_810a7b70 sets up the display-size object (B = [[0x84ca29c0]+216]) from a config (x1): its docked size list (+8, first
#   2560 x 1440) is the frame's base (B+244; the frame is the base times the graphics scale's factor, f_806702e0, capped by the
#   scale's display class: docked 3840 x 2160 at scale 0). Its first entry asks the host when it differs.
OUT_DECL = "uint32_t hos_output_size(int height);\nuint64_t hos_rt_pool_size(uint64_t game);\n"
OUT_EDITS = [
    # (the picture's 2560 x 1440 at 0x81202ee4, not f_831f3200's copy at +0xb68; nx2/oot_wide.py's widescreen size, after it,
    # stays over it: host/hos_main.c makes that one at this height)
    ("    c->x[8] = 0xa00ULL;\n    c->x[8] = (c->x[8] & ~(0xFFFFULL<<32)) | (0x5a0ULL<<32);\n"
     "{ extern volatile uint64_t hos_wide_out; const uint64_t _s = hos_wide_out; if (_s) c->x[8] = _s; }   /* (nx2/oot_wide.py: hos_wide_out) */\n"
     "    { uint64_t _b=c->x[21]; int64_t _o=20; recomp_store64(c,(_b+_o),c->x[8]); }",
     "    c->x[8] = hos_output_size(0) | ((uint64_t)hos_output_size(1) << 32);\n"
     "{ extern volatile uint64_t hos_wide_out; const uint64_t _s = hos_wide_out; if (_s) c->x[8] = _s; }   /* (nx2/oot_wide.py: hos_wide_out) */\n"
     "    { uint64_t _b=c->x[21]; int64_t _o=20; recomp_store64(c,(_b+_o),c->x[8]); }"),
    ("    { uint64_t _a=c->x[0], _b=724ULL; uint64_t _r=_a+_b; c->x[21]=_r; }\n"
     "    { uint64_t _r = ((uint64_t)0 | ((c->x[1]) << 0)); c->x[20] = _r; }\n",
     "    { uint64_t _a=c->x[0], _b=724ULL; uint64_t _r=_a+_b; c->x[21]=_r; }\n"
     "    { uint64_t _r = ((uint64_t)0 | ((c->x[1]) << 0)); c->x[20] = _r; }\n"
     "    if ((hos_output_size(0) != 2560 || hos_output_size(1) != 1440) && recomp_load32(c, c->x[20] + 8) == 2560) { recomp_store32(c, c->x[20] + 8, hos_output_size(0)); recomp_store32(c, c->x[20] + 12, hos_output_size(1)); }\n"),
    # - f_80ea2f30: the 3D's largest size, ResolutionParam's BaseResolution (or 1920 x 1080 as constants), 3/4 of 2560 x 1440;
    #   above it the game takes a smaller upscale network (1/3: 1280 x 720 at 4K). Scaled with the output.
    ("c->x[30] = 0x80ea2ffcULL; f_831cca50(c);\n"
     "    { uint64_t _b=c->x[0]; int64_t _o=0; { uint64_t _p0,_p1; recomp_ldp32(c,(_b+_o),&_p0,&_p1); c->x[24]=_p0; c->x[25]=_p1; } }\n",
     "c->x[30] = 0x80ea2ffcULL; f_831cca50(c);\n"
     "    { uint64_t _b=c->x[0]; int64_t _o=0; { uint64_t _p0,_p1; recomp_ldp32(c,(_b+_o),&_p0,&_p1); c->x[24]=_p0; c->x[25]=_p1; } }\n"
     "    if (hos_output_size(0) != 2560 || hos_output_size(1) != 1440) { c->x[24] = (uint32_t)c->x[24] * hos_output_size(0) / 2560; c->x[25] = (uint32_t)c->x[25] * hos_output_size(1) / 1440; }\n"),
    ("    c->x[8] = 0x44f00000ULL;\n    c->x[8] &= 0xFFFFFFFFULL;\n    recomp_store32(c,c->x[19] + 3668,c->x[8]);\n"
     "    c->x[8] = 0x44870000ULL;\n    c->x[8] &= 0xFFFFFFFFULL;\n",
     "    c->x[8] = hos_output_size(0) * 3 / 4;\n    { float _f = (float)c->x[8]; uint32_t _u; memcpy(&_u, &_f, 4); c->x[8] = _u; }\n"
     "    recomp_store32(c,c->x[19] + 3668,c->x[8]);\n"
     "    c->x[8] = hos_output_size(1) * 3 / 4;\n    { float _f = (float)c->x[8]; uint32_t _u; memcpy(&_u, &_f, 4); c->x[8] = _u; }\n"),
    # - The render targets' GPU pool: 0x13100000 bytes (the graphics config's +1464, read in f_836ce9d0, which takes its storage from
    #   the "Graphics" heap and makes a physical pool and a virtual one over it: f_80c4a1c0 -> f_80c49070 -> f_80c49380 -> f_811c9ba0).
    #   Sized for 2560 x 1440: a 3840x2160 3D at the 4K output ran out of it and the next target came back null (crash in f_8005ed00,
    #   the pool's allocator, its +0x28 0x13100000). Scaled with the output's pixels (host/nn_applet.c
    #   hos_rt_pool_size: 687 MB at 3840 x 2160), at the config, so the storage and the pool agree.
    ("L_836cea54:;\n",
     "L_836cea54:;\n"
     "    if (recomp_load64(c, c->x[19] + 1464) == 0x13100000ULL) recomp_store64(c, c->x[19] + 1464, hos_rt_pool_size(0x13100000ULL));\n"),
    # - The "Graphics" heap holds it, made by f_83b7b340 with the other module heaps (twice: 0x34900000 bytes in f_83b7a2c0's first
    #   pass, then the heap kept, 0x348ffe20; it had under 16 MB to spare): grown by as much as the pool.
    ("c->x[30] = 0x83b7b440ULL; f_809df710(c);\n",
     "if (c->x[0] == 0x34900000ULL || c->x[0] == 0x348ffe20ULL) c->x[0] += hos_rt_pool_size(0x13100000ULL) - 0x13100000ULL;\n"
     "c->x[30] = 0x83b7b440ULL; f_809df710(c);\n"),
    # - f_83b7b340 then takes each module heap's use (its vtable +120) off the module's budget (the configured size, a table of slots)
    #   and aborts below zero (f_8351c280): the Graphics heap's use counts as the shipped one.
    ("{ uint64_t _t = c->x[8]; c->x[30] = 0x83b7b4e0ULL; A64_ICALL(c, _t); }\n",
     "{ uint64_t _t = c->x[8]; c->x[30] = 0x83b7b4e0ULL; A64_ICALL(c, _t); }\n"
     "{ const uint64_t _b = recomp_load64(c, c->x[21] + (c->x[22] << 3)), _g = hos_rt_pool_size(0x13100000ULL) - 0x13100000ULL; "
     "if ((_b == 0x34900000ULL || _b == 0x348ffe20ULL) && c->x[0] > _g) c->x[0] -= _g; }\n"),
    # - f_80b72340 (from the graphics init f_836cf4b0) makes a heap of what the Graphics heap can still give, which took the growth as
    #   well (0x1b6cb48 bytes as shipped, 0x1996cb48 grown) and left too little for the pool: it keeps its shipped size.
    ("c->x[30] = 0x80b723acULL; f_809df700(c);\n",
     "if (c->x[0] > hos_rt_pool_size(0x13100000ULL) - 0x13100000ULL) c->x[0] -= hos_rt_pool_size(0x13100000ULL) - 0x13100000ULL;\n"
     "c->x[30] = 0x80b723acULL; f_809df700(c);\n"),
]


def apply_output_size(gen, required=False):
    """required (the supported build's whole lift): each edit must be made, or found made, exactly once, else SystemExit: without
    one the Insert menu's Output resolution is ignored, or a 4K output runs out of the render targets' pool. Elsewhere (another
    build, part of a lift, by hand) a warning"""
    found = [0] * len(OUT_EDITS)
    for path in sorted(glob.glob(os.path.join(glob.escape(gen), "code_*.c"))):
        with open(path, encoding="utf-8", newline="") as f:
            s = f.read()
        hit = False
        for i, (old, new) in enumerate(OUT_EDITS):
            # (every place: each made one, and each old text outside a made one; a new text can hold its old one. A file with
            # both is counted for both, and its old ones are left: a second made place or a stray raw one is not once)
            made = s.count(new)
            raw = (s.replace(new, "\0") if made else s).count(old)
            found[i] += made + raw
            if raw and not made:
                s = s.replace(old, new)
                hit = True
        if hit:
            if OUT_DECL not in s:
                s = s.replace('#include "a64.h"\n', '#include "a64.h"\n' + OUT_DECL, 1)
            whole_write.write_whole(path, s, newline="")
            print("oot_patches: output size in", os.path.basename(path))
    if found != [1] * len(OUT_EDITS):
        if required:
            raise SystemExit("oot_patches: the output size places were found %s times, not once each (OUT_EDITS %s): the "
                             "lifted C no longer has the text they match" % (found, [i for i, n in enumerate(found) if n != 1]))
        print("oot_patches: WARNING: the output size places were found %s times" % found)


if __name__ == "__main__":
    apply(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "work", "sa", "gen"))
