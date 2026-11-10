/* (hookshot) The Insert menu's Text size: the text of dialogue, Navi and signs drawn larger.

   nx2/oot_patches.py calls hos_oot_text_pane from f_80b1e140, the step of a LetterAnimControl (the text panes with
   "LetterAnimOn"), with that control. The control's +0x28 is the game's pane wrapper: its +8 is the Layout2 text box pane,
   and its +0x28 and +0x38 are the diagonal of the text's 2D scale (0.8 each for dialogue). Each of the two keeps the
   game's own value, taken again whenever the game has written it since, and gets that value times the menu's scale. At
   Original a field never scaled is left alone, and one scaled before gets the game's value back.

   HOS_TEXT_SIZE=<0..4> stands over the menu (0 Original, 1 110%, 2 125%, 3 150%, 4 175%), as HOS_TEXT_SPEED does for Text
   speed (host/nn_vi.c). */
#include "hos.h"
#include "../gpu/vk/vk_api.h"
#include <stdlib.h>
#include <string.h>

int rx_option(int id, int otherwise);

enum { TEXT_ANIM_WRAPPER = 0x28, TEXT_WRAPPER_PANE = 0x08, TEXT_WRAPPER_SCALE_X = 0x28, TEXT_WRAPPER_SCALE_Y = 0x38 };

/* A Text size choice's scale: 1 for Original and for anything out of range */
static float text_size_scale(int v) {
    static const float k[] = {1.0f, 1.10f, 1.25f, 1.50f, 1.75f};
    return v > 0 && v < (int)(sizeof k / sizeof k[0]) ? k[v] : 1.0f;
}

/* A scaled field: its guest address, the game's own value, the value written last and when it was last stepped */
typedef struct {
    uint64_t addr;
    uint32_t game, written, seen;
} TextSizeField;

/* The value a field gets: the game's own times s. A field that no longer holds the value written last was written by the
   game since, and that is its new own value */
static uint32_t text_size_value(TextSizeField *f, uint32_t now, float s) {
    if (now != f->written) f->game = now;
    float g, v;
    memcpy(&g, &f->game, 4);
    v = g * s;
    memcpy(&f->written, &v, 4);
    return f->written;
}

void hos_oot_text_pane(Ctx *c, uint64_t anim) {
    static const char *env;
    static int looked;
    if (!looked) looked = 1, env = getenv("HOS_TEXT_SIZE");
    const float s = text_size_scale(env && *env ? atoi(env) : rx_option(HOS_OPT_TEXT_SIZE, 0));
    const uint64_t wrapper = anim ? recomp_load64(c, anim + TEXT_ANIM_WRAPPER) : 0;
    if (!wrapper || !recomp_load64(c, wrapper + TEXT_WRAPPER_PANE)) return;   /* (a pane not set up yet) */

    /* (the fields of the panes seen: a new one takes the place of the one stepped longest ago. Only the text on screen is
       stepped, so that one's text is gone) */
    static TextSizeField kept[64];
    static uint32_t tick;
    static volatile long lock;
    static const unsigned offs[] = {TEXT_WRAPPER_SCALE_X, TEXT_WRAPPER_SCALE_Y};
    while (__sync_lock_test_and_set(&lock, 1)) {}
    tick++;
    for (unsigned i = 0; i < sizeof offs / sizeof offs[0]; i++) {
        const uint64_t a = wrapper + offs[i];
        const uint32_t now = (uint32_t)recomp_load32(c, a);
        TextSizeField *f = NULL, *oldest = &kept[0];
        for (unsigned k = 0; k < sizeof kept / sizeof kept[0] && !f; k++) {
            if (kept[k].addr == a) f = &kept[k];
            else if (kept[k].seen < oldest->seen) oldest = &kept[k];
        }
        if (!f) {
            if (s == 1.0f) continue;   /* (Original: a field never scaled stays the game's) */
            f = oldest, f->addr = a, f->game = f->written = now;
        }
        f->seen = tick;
        const uint32_t v = text_size_value(f, now, s);
        if (v != now) recomp_store32(c, a, v);
    }
    __sync_lock_release(&lock);
}
