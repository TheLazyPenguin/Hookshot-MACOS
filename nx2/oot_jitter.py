"""The temporal upscalers' camera jitter for Ocarina of Time 1.1.1: C added after a few instructions of the game (a64_lift.py
Lifter.after). One jitter for all of them: NVIDIA DLSS and AMD FSR 4 (gpu/vk/vk_temporal.cpp, the frame chain they share) and
AMD FSR 3.1 (gpu/vk/vk_fsr3_inputs.cpp).

A temporal upscaler resolves detail finer than a pixel from frames whose camera moved by a different fraction of a
pixel each time. The game's cameras do not move so: these sites give the scene's projection a sub-pixel offset each frame,
in the GPU's copy only. The game fills each view's uniform buffers in one function (main+0x6bc520): for each view it loads
the view's projection matrix (the view at x28, its projection's rows at +0x1a8) and writes it, the view-projection made from
it and more into the buffers the draws read. The sites are those loads: the jitter goes on the third column of the first two
rows (P[0][2], P[1][2]), in the registers, so the buffers get the jittered matrix and everything made from it, while the
game's own cameras and views keep the projection as it is.

The jitter used to go into sead's perspective projection itself (its frustum offset, +0xb4 and +0xb8), where the game's
CPU work saw it too: the shadow cascades are fitted to the view's frustum, so with the camera still the shadow map's origin
moved by a sixth of a shadow texel each frame (up to a third; 0.003 without the jitter), and with it the shadows' edges
(#841: a tester saw shadows flicker at DLAA). Here the cascades (and culling, and anything else on the CPU) see the view as
the game set it.

host/rx_backend.c hos_dlss_jitter_clip picks the jitter and checks the projection is one of the picture's: perspective, of
16:9 or the window's ratio (nx2/oot_wide.py). It is none (the game as shipped) unless DLSS or an FSR runs (the renderer's
rx_option HOS_OPT_DLSS_JITTER_W and _H are 0 otherwise), and the renderer reads the offset back from the camera's uniform
buffer. Which view is the scene's, the renderer learns from its draws, too late for
this: the other views of the picture's ratio (a reflection, a portrait) are drawn without DLSS and move by under a pixel
of the scene's size, too little to see.

Installed in every standalone lift (nx2/lift.py): FSR 3.1 needs no SDK, so a build without NVIDIA's has the jitter too.
"""

import oot_wide

# (main offset, the original instruction word there, and the registers whose third lane gets the jitter's x and y: None
# for one not loaded there). The view is x28 at all three; its projection's rows are at +0x1a8, 16 bytes apart.
SITES = (
    # the view-projection block: ldp q19, q20, [x8] (rows 0 and 1), then this ldp q21, q22, [x8, #0x20] (rows 2 and 3)
    (0x6bc708, 0xad415915, 19, 20),
    # the second block: ldr q26, [x9] (row 0), ldr q6, [x9] (row 1)
    (0x6bcf8c, 0x3dc0013a, 26, None),
    (0x6bcf9c, 0x3dc00126, None, 6),
)
VIEW, PROJECTION = 28, 0x1a8


def _text(xreg, yreg):
    add = "".join("{ float _o; memcpy(&_o, (uint8_t *)c->vreg[%d] + 8, 4); _o += _j[%d]; memcpy((uint8_t *)c->vreg[%d] + 8, &_o, 4); } "
                  % (r, axis, r) for axis, r in ((0, xreg), (1, yreg)) if r is not None)
    return ("{ extern int hos_dlss_jitter_clip(uint64_t projection, float out[2]); float _j[2]; "
            "if (hos_dlss_jitter_clip(c->x[%d] + %#x, _j)) { %s} }   /* (nx2/oot_jitter.py: the upscalers' camera jitter) */"
            % (VIEW, PROJECTION, add))


def install(lifter, img):
    """The sites into lifter.after, after what is there; a site whose word differs (another game version) is left out"""
    n = 0
    for off, word, xreg, yreg in SITES:
        pc = oot_wide.MAIN + off
        try:
            have = img.word(pc)
        except Exception:
            have = None
        if have != word:
            print("dlss jitter: main+%#x holds %s, not %08x: left out" % (off, "?" if have is None else "%08x" % have, word))
            continue
        lifter.after[pc] = (lifter.after[pc] + "\n" if pc in lifter.after else "") + _text(xreg, yreg)
        n += 1
    print("dlss jitter: %d of %d sites" % (n, len(SITES)))
    return n
