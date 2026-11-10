/* The host's log writer (host/hos_thread.c, the Windows queue, log_main and log_flush) extracted unmodified, with the CRT
   stream calls as spies: what goes out, in how many writes, and when. Real threads, SRW locks and condition variables. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static SRWLOCK spy_lock = SRWLOCK_INIT;
static char out[1 << 20];
static size_t out_len;
static volatile LONG writes;

static void spy_append(const void *p, size_t n) {
    AcquireSRWLockExclusive(&spy_lock);
    if (out_len + n <= sizeof out) memcpy(out + out_len, p, n), out_len += n;
    ReleaseSRWLockExclusive(&spy_lock);
    InterlockedIncrement(&writes);
}
__attribute__((unused)) static int spy_fputs(const char *s, FILE *f) {
    (void)f;
    spy_append(s, strlen(s));
    return 0;
}
__attribute__((unused)) static size_t spy_fwrite(const void *p, size_t size, size_t n, FILE *f) {
    (void)f;
    spy_append(p, size * n);
    return n;
}
__attribute__((unused)) static int spy_fflush(FILE *f) {
    (void)f;
    return 0;
}
static size_t out_size(void) {
    AcquireSRWLockExclusive(&spy_lock);
    const size_t n = out_len;
    ReleaseSRWLockExclusive(&spy_lock);
    return n;
}

#define fputs spy_fputs
#define fwrite spy_fwrite
#define fflush spy_fflush
/* (log_main is a thread that never returns: its for (;;) has no return after it. GCC's C front end warns for a static function
   with no return statement at all, whatever its loop; clang, which builds the game, does not) */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wreturn-type"
/* ACTUAL_LOG */
#pragma GCC diagnostic pop
#undef fflush
#undef fwrite
#undef fputs

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); return 1; } } while (0)

static char expect[1 << 20];
static size_t expect_len;
static int queue(int i) {
    char line[64];
    const int n = snprintf(line, sizeof line, "[hos test] line %d\n", i);
    memcpy(expect + expect_len, line, (size_t)n);
    expect_len += (size_t)n;
    return log_queue(line);
}
static int wait_for(size_t n, DWORD ms) {
    const ULONGLONG end = GetTickCount64() + ms;
    while (out_size() < n && GetTickCount64() < end) Sleep(1);
    return out_size() >= n;
}
static int same(void) {
    return out_size() == expect_len && memcmp(out, expect, expect_len) == 0;
}

static int run(const char *name) {
    if (!strcmp(name, "batch")) {   /* (HOS_LOG_BATCH_MS=1000: the lines of that time in one write) */
        CHECK(queue(0));
        Sleep(20);
        for (int i = 1; i < 50; i++) CHECK(queue(i));
        Sleep(100);
        CHECK(out_size() == 0);   /* (still waiting for more) */
        CHECK(wait_for(expect_len, 4000) && same());
        CHECK(writes == 1);
        Sleep(400);
        CHECK(queue(50));   /* (the next batch: the writer back to waiting for a line) */
        CHECK(wait_for(expect_len, 4000) && same() && writes == 2);
    } else if (!strcmp(name, "default")) {   /* (no setting: a line waits its 250 ms, then goes out) */
        const ULONGLONG t0 = GetTickCount64();
        CHECK(queue(0));
        CHECK(wait_for(expect_len, 3000) && same());
        CHECK(GetTickCount64() - t0 >= 200);   /* (GetTickCount64 steps in 10-16 ms) */
    } else if (!strcmp(name, "off")) {   /* (HOS_LOG_BATCH_MS=0: each wake's lines at once, as before) */
        const ULONGLONG t0 = GetTickCount64();
        CHECK(queue(0));
        CHECK(wait_for(expect_len, 3000) && same());
        CHECK(GetTickCount64() - t0 < 200);
    } else if (!strcmp(name, "burst")) {   /* (HOS_LOG_BATCH_MS=2000: a queue half full goes out without the wait) */
        size_t half = 0;
        for (int i = 0; i < 1500; i++) {
            CHECK(queue(i));   /* (every line queued: none written by this thread) */
            if (i == 1023) half = expect_len;
        }
        CHECK(wait_for(half, 1000));
        CHECK(wait_for(expect_len, 4000) && same());
    } else if (!strcmp(name, "flush")) {   /* (HOS_LOG_BATCH_MS=2000: a way out writes what waits, once) */
        for (int i = 0; i < 10; i++) CHECK(queue(i));
        Sleep(50);
        CHECK(out_size() == 0);
        log_flush();   /* (as atexit, hos_fatal and the window's close do) */
        CHECK(same());
        Sleep(2500);   /* (the writer's wait ends with nothing left to write) */
        CHECK(same());
    } else {
        CHECK(0);
    }
    printf("PASS: %s\n", name);
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    return run(argv[1]);
}
