/* One window-thread sample, consumed by the renderer without querying the window or SDL.
   The dimensions remain available while inactive/minimized; input is discarded on loss of eligibility. */
#pragma once
#include <windows.h>
#include "../gpu/vk/vk_api.h"

typedef struct HosPointer {
    SRWLOCK lock;
    MkwVkPointer point;
    int active;
    MkwVkPointer press;   /* first pending click, in the geometry of its event */
    int64_t wheel;   /* 1/120 notches; a fractional notch survives a read */
} HosPointer;
#define HOS_POINTER_INIT {SRWLOCK_INIT, {0}, 0, {0}, 0}

static inline void hos_pointer_publish(HosPointer *p, MkwVkPointer sample, int active) {
    AcquireSRWLockExclusive(&p->lock);
    active = active && sample.width > 0 && sample.height > 0;
    const uint32_t pressed = p->point.pressed;
    if (active && sample.pressed && !pressed) p->press = sample;
    p->point = sample;
    p->active = active;
    p->point.pressed = active ? pressed | sample.pressed : 0;
    if (!active) p->point.held = 0;
    p->wheel = active ? p->wheel + sample.wheel : 0;
    ReleaseSRWLockExclusive(&p->lock);
}

static inline int hos_pointer_take(HosPointer *p, MkwVkPointer *out) {
    AcquireSRWLockExclusive(&p->lock);
    *out = p->point;
    const int active = p->active;
    if (active && out->pressed) {
        out->x = p->press.x, out->y = p->press.y;
        out->width = p->press.width, out->height = p->press.height;
    }
    out->wheel = active ? (int32_t)(p->wheel / 120) : 0;
    p->wheel %= 120;
    p->point.pressed = 0;
    ReleaseSRWLockExclusive(&p->lock);
    return active;
}

static inline void hos_pointer_size(HosPointer *p, int *w, int *h) {
    AcquireSRWLockShared(&p->lock);
    *w = p->point.width, *h = p->point.height;
    ReleaseSRWLockShared(&p->lock);
}

static inline void hos_pointer_reset(HosPointer *p) {
    AcquireSRWLockExclusive(&p->lock);
    p->active = 0;
    p->point.held = p->point.pressed = 0;
    p->wheel = 0;
    ReleaseSRWLockExclusive(&p->lock);
}
