/* (hookshot) Native mouse look (the Insert menu's "Mouse camera", off by default; HOS_MOUSE_NATIVE=1 or 0 overrides it):
   the captured mouse turns the player camera's own yaw and pitch, in degrees, with no dead zone, no response curve, no
   smoothing and no top speed, in place of the mouse as the right stick (nn_hid.c's mouse_stick).

   Where the angles are: the player camera's update, f_80644c80 (a virtual method, the camera in x0), calls
   hos_mouse_camera first (nx2/oot_patches.py, patch_mouse_camera), on the game's thread, once a frame while that camera
   runs. The camera holds its pitch limits at +0x178 ({-85, 89} in the field), its pitch at +0x18c and its yaw at +0x1a4.
   The game turns them by the right stick in f_80649c10 (yaw, wrapped at 180) and f_8064b770 (pitch, within the limits),
   which f_80644c80 calls only while the stick is out of its dead zone (found with hardware write watchpoints on the two
   angles in Kokiri Forest). Yaw falls as the view turns right and pitch rises as it tilts down.

   The camera's state at +0x204 is 3 while it follows Link by itself, and then it eases the pitch back to its rest over a
   couple of seconds; the right stick makes it 4 (the player's), where a pitch stays where it was put. The mouse leaves the
   state as it is: written there from here the game puts it back and the angles with it the next frame. So a pitch the
   mouse chose eases back as one the game chose does, while yaw stays.

   The motion is added before the camera reads its input, so the game's own collision, lock-on and scripted cameras still
   follow. While the hook has run in the last 150 ms the mouse's motion is the camera's (hos_mouse_native gives 1: the
   right stick is left alone); otherwise (the pause menu, cutscenes with another camera, a build the patch did not find
   its place in) it is the right stick as before.

   The sensitivity is the mouse's (the menu's Mouse sensitivity, - and =): 0.1 degrees a count at 1. HOS_MOUSE_INVERT_Y=1
   or the menu's Invert mouse vertical flips up and down. */
#include "hos.h"
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

int hos_mouse_take(int32_t *dx, int32_t *dy);                                   /* display.c */
void hos_mouse_give_back(int32_t dx, int32_t dy);                               /* display.c */
int rx_option(int id, int otherwise);
extern double hos_mouse_sens;

enum { LIMITS_AT = 0x178, PITCH_AT = 0x18c, YAW_AT = 0x1a4, STATE_AT = 0x204 };
#define LIVE_NS 150000000LL   /* (the hook ran this recently: the camera takes the mouse) */
#define DEG_PER_COUNT 0.1

static volatile LONG64 last_hook_ns;
static volatile LONG64 last_camera;
static long long applied, cameras_seen;

static float getf(uint64_t a) { float f; memcpy(&f, GP(a), 4); return f; }
static void putf(uint64_t a, float f) { memcpy(GP(a), &f, 4); }

/* the menu's Mouse camera (option 6), or HOS_MOUSE_NATIVE */
static int native_on(void) {
    static const char *env;
    static int looked;
    if (!looked) looked = 1, env = getenv("HOS_MOUSE_NATIVE");
    return env ? atoi(env) != 0 : rx_option(6, 0);
}

static int invert_y(void) {
    static int env = -1;
    if (env < 0) env = getenv("HOS_MOUSE_INVERT_Y") != NULL;
    return env || rx_option(8, 0);   /* (the menu's Invert mouse vertical) */
}

/* a camera's angles as the game keeps them: limits in order within +-90, angles finite */
static int looks_like_camera(uint64_t cam) {
    const float lo = getf(cam + LIMITS_AT), hi = getf(cam + LIMITS_AT + 4), p = getf(cam + PITCH_AT), y = getf(cam + YAW_AT);
    return isfinite(lo) && isfinite(hi) && lo < hi && lo >= -90.0f && hi <= 90.0f && isfinite(p) && isfinite(y) &&
           fabsf(y) <= 360.0f;
}

/* The Controls row "Disable camera centering" (option 45), independent of the mouse mode. The game's state-3 yaw-follow
   branch asks before it runs (nx2/oot_patches.py); 0 keeps the stock behavior, including without a renderer. */
int hos_disable_camera_centering(void) { return rx_option(45, 0); }

/* f_80644c80's first line (nx2/oot_patches.py): cam is the player camera, the game's thread */
void hos_mouse_camera(uint64_t cam) {
    if (!cam || !native_on() || !looks_like_camera(cam)) return;
    /* Only while it is the view: following Link (3) or turned by the player (4). Aiming the slingshot in first person
       leaves this camera updating with its state 0 while another one draws (traced at Hyrule Castle); shops are reported
       the same. In any other state the mouse is the right stick, which those views turn by (the hook counts as not
       run, so hos_mouse_native gives -1) */
    uint32_t state;
    memcpy(&state, GP(cam + STATE_AT), 4);
    if (state != 3 && state != 4) {
        /* (at once: the stick takes the next motion, not one burst once the 150 ms run out) */
        InterlockedExchange64(&last_hook_ns, 0);
        /* (each state seen leaving the mouse to the stick, once: what another view, Z-targeting, climbing or swimming,
           is, to add here if one of them should turn with the mouse) */
        static uint32_t said[8];
        static int nsaid;
        int seen = 0;
        for (int i = 0; i < nsaid; i++) seen |= said[i] == state;
        if (!seen && nsaid < 8) {
            said[nsaid++] = state;
            hos_log("mouse native: camera state %u: the mouse is the right stick", state);
        }
        return;
    }
    InterlockedExchange64(&last_hook_ns, hos_now_ns());
    if (InterlockedExchange64(&last_camera, (LONG64)cam) != (LONG64)cam && cameras_seen++ < 8)
        hos_log("mouse native: the player camera at %#llx turns with the mouse", (unsigned long long)cam);
    int32_t dx, dy;
    if (!hos_mouse_take(&dx, &dy) || (!dx && !dy)) return;
    const double k = DEG_PER_COUNT * hos_mouse_sens;
    float y = getf(cam + YAW_AT) - (float)(dx * k), p = getf(cam + PITCH_AT) + (float)((invert_y() ? -dy : dy) * k);
    const float lo = getf(cam + LIMITS_AT), hi = getf(cam + LIMITS_AT + 4);
    while (y > 180.0f) y -= 360.0f;
    while (y < -180.0f) y += 360.0f;
    if (p < lo) p = lo;
    if (p > hi) p = hi;
    putf(cam + YAW_AT, y), putf(cam + PITCH_AT, p);
    if ((++applied & 4095) == 1)
        hos_log("mouse native: %lld moves applied; pitch %.2f yaw %.2f", applied, p, y);
}

/* With each read of the controller (nn_hid.c, the game's threads): 0 if the mouse is not captured, 1 if the camera takes
   its motion (hos_mouse_camera), -1 if no player camera runs now (the right stick takes it) */
int hos_mouse_native(void) {
    static int said;
    if (!said) said = 1, hos_log("mouse native: on (the menu's Mouse camera, or HOS_MOUSE_NATIVE)");
    if (hos_now_ns() - InterlockedCompareExchange64(&last_hook_ns, 0, 0) >= LIVE_NS) return -1;
    int32_t dx, dy;
    const int captured = hos_mouse_take(&dx, &dy);   /* (only to know the capture: the motion is the camera's) */
    if (dx || dy) hos_mouse_give_back(dx, dy);
    return captured ? 1 : 0;
}
