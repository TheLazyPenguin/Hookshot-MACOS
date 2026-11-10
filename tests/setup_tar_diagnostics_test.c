/* Authored process/Win32 doubles; no archive, symlink, installer or user data. */
#include <assert.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#ifdef REAL_CHILD
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#define GetLastError mock_GetLastError
#define CloseHandle mock_CloseHandle
#define CreatePipe mock_CreatePipe
#define SetHandleInformation mock_SetHandleInformation
#define CreateFileW mock_CreateFileW
#define CreateProcessW mock_CreateProcessW
#define ReadFile mock_ReadFile
#define WaitForSingleObject mock_WaitForSingleObject
#define GetExitCodeProcess mock_GetExitCodeProcess
#define MultiByteToWideChar mock_MultiByteToWideChar
#define GetSystemDirectoryW mock_GetSystemDirectoryW
typedef unsigned long DWORD;
typedef int BOOL;
typedef void *HANDLE;
#define TRUE 1
#define FALSE 0
#define MAX_PATH 260
#define INVALID_HANDLE_VALUE ((HANDLE)(intptr_t)-1)
#define STARTF_USESHOWWINDOW 1
#define STARTF_USESTDHANDLES 256
#define SW_HIDE 0
#define CREATE_NO_WINDOW 0x08000000
#define HANDLE_FLAG_INHERIT 1
#define GENERIC_READ 0x80000000
#define GENERIC_WRITE 0x40000000
#define FILE_SHARE_READ 1
#define FILE_SHARE_WRITE 2
#define OPEN_EXISTING 3
#define INFINITE 0xffffffff
#define CP_UTF8 65001
#define ERROR_FILE_NOT_FOUND 2
#define ERROR_BROKEN_PIPE 109
#define WAIT_OBJECT_0 0
typedef struct { DWORD nLength; void *lpSecurityDescriptor; BOOL bInheritHandle; } SECURITY_ATTRIBUTES;
typedef struct { DWORD cb, dwFlags; unsigned short wShowWindow; HANDLE hStdInput, hStdOutput, hStdError; } STARTUPINFOW;
typedef struct { HANDLE hProcess, hThread; DWORD dwProcessId, dwThreadId; } PROCESS_INFORMATION;
static struct {
    DWORD code, error, pipe_error, inherit_error, null_error, launch_error, query_error;
    unsigned open, violation;
    int capturing, inherited, launched;
    size_t offset, length, converted_length;
    wchar_t expected_zip[MAX_PATH], expected_destination[MAX_PATH];
    char data[20000];
} state;
#define BAD_IF(c) do { if (c) state.violation++; } while (0)
static HANDLE opened(unsigned bit) { BAD_IF(state.open & bit); state.open |= bit; return (HANDLE)(uintptr_t)bit; }
DWORD GetLastError(void) { return state.error; }
BOOL CloseHandle(HANDLE handle) {
    unsigned bit = (unsigned)(uintptr_t)handle;
    BAD_IF(!(state.open & bit)); state.open &= ~bit; return TRUE;
}
BOOL CreatePipe(HANDLE *rd, HANDLE *wr, SECURITY_ATTRIBUTES *sa, DWORD size) {
    BAD_IF(size || sa->nLength != sizeof *sa || !sa->bInheritHandle || sa->lpSecurityDescriptor);
    if (state.pipe_error) { state.error = state.pipe_error; return FALSE; }
    *rd = opened(1); *wr = opened(2); return TRUE;
}
BOOL SetHandleInformation(HANDLE h, DWORD mask, DWORD flags) {
    BAD_IF(h != (HANDLE)(uintptr_t)1 || mask != HANDLE_FLAG_INHERIT || flags != 0);
    if (state.inherit_error) { state.error = state.inherit_error; return FALSE; }
    state.inherited = 1; return TRUE;
}
HANDLE CreateFileW(const wchar_t *name, DWORD access, DWORD share, SECURITY_ATTRIBUTES *sa, DWORD create, DWORD flags, HANDLE template) {
    BAD_IF(wcscmp(name, L"NUL") || access != (GENERIC_READ | GENERIC_WRITE) || share != (FILE_SHARE_READ | FILE_SHARE_WRITE)
           || !sa->bInheritHandle || create != OPEN_EXISTING || flags || template);
    if (state.null_error) { state.error = state.null_error; return INVALID_HANDLE_VALUE; }
    return opened(16);
}
BOOL CreateProcessW(const wchar_t *app, wchar_t *cmd, void *a, void *b, BOOL inherit, DWORD flags, void *env, const wchar_t *dir,
                    STARTUPINFOW *si, PROCESS_INFORMATION *pi) {
    BAD_IF(app || a || b || env || flags != CREATE_NO_WINDOW || si->cb != sizeof *si || si->wShowWindow != SW_HIDE);
    wchar_t expected[2 * MAX_PATH + 64];
    swprintf(expected, 2 * MAX_PATH + 64, L"\"C:\\Windows\\System32\\tar.exe\" -xf \"%ls\" -C \"%ls\"", state.expected_zip, state.expected_destination);
    BAD_IF(wcscmp(cmd, expected));
    BAD_IF(wcscmp(dir, state.expected_destination));
    state.capturing = !!(si->dwFlags & STARTF_USESTDHANDLES);
    if (state.capturing) {
        BAD_IF(!inherit || !state.inherited || si->hStdInput != (HANDLE)(uintptr_t)16 || si->hStdOutput != si->hStdInput || si->hStdError != (HANDLE)(uintptr_t)2);
    } else BAD_IF(inherit);
    if (state.launch_error) { state.error = state.launch_error; return FALSE; }
    state.launched = 1; pi->hProcess = opened(4); pi->hThread = opened(8); return TRUE;
}
BOOL ReadFile(HANDLE h, void *buf, DWORD cap, DWORD *n, void *overlapped) {
    BAD_IF(h != (HANDLE)(uintptr_t)1 || overlapped || (state.open & 2));
    if (state.offset == state.length) { *n = 0; state.error = ERROR_BROKEN_PIPE; return FALSE; }
    size_t amount = state.length - state.offset;
    if (amount > cap) amount = cap;
    memcpy(buf, state.data + state.offset, amount); state.offset += amount; *n = (DWORD)amount; return TRUE;
}
DWORD WaitForSingleObject(HANDLE h, DWORD timeout) {
    BAD_IF(h != (HANDLE)(uintptr_t)4 || timeout != INFINITE);
    if (state.capturing) BAD_IF(state.offset != state.length || (state.open & (1|2|16)));
    return WAIT_OBJECT_0;
}
BOOL GetExitCodeProcess(HANDLE h, DWORD *code) {
    BAD_IF(h != (HANDLE)(uintptr_t)4);
    if (state.query_error) { state.error = state.query_error; return FALSE; }
    *code = state.code; return TRUE;
}
int MultiByteToWideChar(unsigned cp, DWORD flags, const char *text, int size, wchar_t *out, int cap) {
    BAD_IF(cp != CP_UTF8 || flags || size != -1);
    size_t n = strlen(text); if (n + 1 > (size_t)cap) return 0;
    state.converted_length = n;
    for (size_t i = 0; i <= n; i++) out[i] = (unsigned char)text[i];
    return (int)n + 1;
}
#endif

static jmp_buf failed;
static wchar_t message[1024];
static int failure_seen;
static void fail(const wchar_t *fmt, ...) {
    va_list ap; va_start(ap, fmt);
    int count = vswprintf(message, 1024, fmt, ap);
    va_end(ap);
    assert(count >= 0 && count < 1024);
    failure_seen = 1;
    longjmp(failed, 1);
}

/* ACTUAL_HELPER */

#ifdef REAL_CHILD
static wchar_t fake_system[MAX_PATH];
static DWORD fake_system_directory(wchar_t *out, DWORD n) {
    assert(wcslen(fake_system) < n); wcscpy(out, fake_system); return (DWORD)wcslen(out);
}
#define GetSystemDirectoryW fake_system_directory
#else
DWORD GetSystemDirectoryW(wchar_t *out, DWORD n) {
    assert(n > wcslen(L"C:\\Windows\\System32")); wcscpy(out, L"C:\\Windows\\System32"); return (DWORD)wcslen(out);
}
#endif

static void extract_part(const wchar_t *target, const wchar_t *archive) {
    wchar_t dest[MAX_PATH], zip[MAX_PATH];
    wchar_t sys[MAX_PATH], tarcmd[2 * MAX_PATH + 64];
    int i = 0, nparts = 8;
    wcscpy(dest, target);
    wcscpy(zip, archive);
#ifndef REAL_CHILD
    wcscpy(state.expected_destination, target), wcscpy(state.expected_zip, archive);
#endif
    /* ACTUAL_CALL */
}

#define CHECK(c, why) do { if (!(c)) { fprintf(stderr, "FAIL: %s\n", why); return 1; } } while (0)
static int check_missing_guidance(void) {
    CHECK(wcsstr(message, L"Windows' tar.exe was not found") && wcsstr(message, L"Windows error 2"), "identify the missing Windows extractor");
    const wchar_t *admin = wcsstr(message, L"Command Prompt as administrator");
    const wchar_t *dism = wcsstr(message, L"DISM /Online /Cleanup-Image /RestoreHealth");
    const wchar_t *success = wcsstr(message, L"After DISM succeeds");
    const wchar_t *sfc = wcsstr(message, L"sfc /scannow");
    const wchar_t *restart = wcsstr(message, L"restart Windows");
    const wchar_t *retry = wcsstr(message, L"run setup again");
    CHECK(admin && dism && success && sfc && restart && retry, "complete manual recovery guidance");
    CHECK(admin < dism && dism < success && success < sfc && sfc < restart && restart < retry, "manual repair success/restart/retry order");
    return 0;
}
#ifdef REAL_CHILD
int main(int argc, char **argv) {
    wchar_t self[MAX_PATH]; GetModuleFileNameW(NULL, self, MAX_PATH);
    const wchar_t *name = wcsrchr(self, L'\\'); name = name ? name + 1 : self;
    if (!_wcsicmp(name, L"tar.exe")) {
        DWORD n, flags;
        HANDLE in = GetStdHandle(STD_INPUT_HANDLE), out = GetStdHandle(STD_OUTPUT_HANDLE), err = GetStdHandle(STD_ERROR_HANDLE);
        const char *prefix = GetHandleInformation(in, &flags) && GetHandleInformation(out, &flags)
            ? "valid-standard-handles; authored real tar diagnostic: " : "invalid-standard-handles; authored real tar diagnostic: ";
        WriteFile(err, prefix, (DWORD)strlen(prefix), &n, NULL);
        char bytes[1000]; memset(bytes, 'x', sizeof bytes);
        for (int i = 0; i < 20; i++) WriteFile(err, bytes, sizeof bytes, &n, NULL);
        return 23;
    }
    CHECK(argc == 2 || (argc == 3 && !strcmp(argv[2], "missing")), "temporary folder argument");
    CHECK(MultiByteToWideChar(CP_ACP, 0, argv[1], -1, fake_system, MAX_PATH), "temporary path conversion");
    wchar_t child[MAX_PATH]; swprintf(child, MAX_PATH, L"%ls\\tar.exe", fake_system);
    if (argc == 3) {
        CHECK(GetFileAttributesW(child) == INVALID_FILE_ATTRIBUTES && GetLastError() == ERROR_FILE_NOT_FOUND, "owned temporary extractor does not exist");
        DWORD cold, before, after;
        CHECK(GetProcessHandleCount(GetCurrentProcess(), &cold), "cold native handle count");
        if (!setjmp(failed)) extract_part(fake_system, L"C:\\authored cache\\part.zip");
        CHECK(failure_seen && wcslen(message) < 1024, "bounded native launch failure");
        CHECK(wcsstr(message, fake_system) && wcsstr(message, L"C:\\authored cache\\part.zip"), "native missing failure retains both paths");
        /* The first process/formatting call can initialize persistent runtime handles. Check repeated failures after it. */
        CHECK(GetProcessHandleCount(GetCurrentProcess(), &before), "initial native handle count");
        for (int i = 0; i < 4; i++) {
            failure_seen = 0;
            if (!setjmp(failed)) extract_part(fake_system, L"C:\\authored cache\\part.zip");
            CHECK(failure_seen && wcslen(message) < 1024, "repeated bounded native launch failure");
            CHECK(GetProcessHandleCount(GetCurrentProcess(), &after) && after == before, "each repeated missing native child closes all capture handles");
        }
        CHECK(GetProcessHandleCount(GetCurrentProcess(), &after) && after == before, "repeated missing native children close all capture handles");
        printf("Native handles: cold=%lu warm=%lu after each of four retries=%lu\n", cold, before, after);
        CHECK(!check_missing_guidance(), "native missing recovery guidance");
        CHECK(GetFileAttributesW(child) == INVALID_FILE_ATTRIBUTES, "no extractor or repair command was created");
        printf("PASS real missing executable, recovery guidance, native handles %lu -> %lu across four retries\n", before, after);
        return 0;
    }
    CHECK(CopyFileW(self, child, TRUE), "authored fake tar copy");
    HANDLE saved_in = GetStdHandle(STD_INPUT_HANDLE), saved_out = GetStdHandle(STD_OUTPUT_HANDLE);
    SetStdHandle(STD_INPUT_HANDLE, NULL); SetStdHandle(STD_OUTPUT_HANDLE, NULL);
    if (!setjmp(failed)) extract_part(fake_system, L"C:\\authored cache\\part.zip");
    SetStdHandle(STD_INPUT_HANDLE, saved_in); SetStdHandle(STD_OUTPUT_HANDLE, saved_out);
    CHECK(failure_seen, "real child exit must fail extraction");
    CHECK(wcsstr(message, L"exited with code 23"), "actual real child exit status");
    CHECK(wcsstr(message, fake_system), "actual real destination");
    CHECK(wcsstr(message, L"valid-standard-handles; authored real tar diagnostic:"), "GUI/no-console valid handles and real stderr");
    CHECK(!wcsstr(message, L"invalid-standard-handles"), "reject invalid inherited standard handles");
    CHECK(wcslen(message) < 1024, "bounded real message");
    puts("PASS real child, long stderr, no parent standard handles");
    return 0;
}
#else
int main(int argc, char **argv) {
    CHECK(argc == 2, "case argument");
    const char *test = argv[1];
    wchar_t target[MAX_PATH] = L"Q:\\authored destination\\version.part";
    wchar_t archive[MAX_PATH] = L"C:\\authored cache\\part.zip";
    state.code = 23;
    strcpy(state.data, "authored tar diagnostic"); state.length = strlen(state.data);
    if (!strcmp(test, "launch")) state.launch_error = 5;
    else if (!strcmp(test, "missing")) state.launch_error = ERROR_FILE_NOT_FOUND;
    else if (!strcmp(test, "child_exit_2")) state.code = 2;
    else if (!strcmp(test, "long")) { memset(state.data, 'x', sizeof state.data); memcpy(state.data, "authored tar diagnostic", 23); state.length = sizeof state.data; }
    else if (!strcmp(test, "success")) state.code = 0, state.length = 0;
    else if (!strcmp(test, "warning")) state.code = 0;
    else if (!strcmp(test, "pipe_fallback")) state.code = 0, state.pipe_error = 87;
    else if (!strcmp(test, "inherit_fallback")) state.code = 0, state.inherit_error = 5;
    else if (!strcmp(test, "null_fallback")) state.code = 0, state.null_error = 5;
    else if (!strcmp(test, "empty")) state.length = 0;
    else if (!strcmp(test, "high_exit")) state.code = 0xc0000005UL;
    else if (!strcmp(test, "query")) state.query_error = 6;
    else if (!strcmp(test, "capture_error")) state.pipe_error = 87;
    else if (!strcmp(test, "max_paths") || !strcmp(test, "missing_max_paths")) {
        for (int i = 3; i < MAX_PATH - 1; i++) target[i] = L'd', archive[i] = L'a';
        target[MAX_PATH - 1] = archive[MAX_PATH - 1] = 0;
        memset(state.data, 'x', sizeof state.data); memcpy(state.data, "authored tar diagnostic", 23); state.length = sizeof state.data;
        if (!strcmp(test, "missing_max_paths")) state.launch_error = ERROR_FILE_NOT_FOUND;
    }
    else CHECK(!strcmp(test, "failure"), "known case");
    if (!setjmp(failed)) extract_part(target, archive);
    CHECK(state.violation == 0 && state.open == 0, "command/flags/inheritance/drain order/handle cleanup unchanged");
    CHECK(state.launched == !state.launch_error, "actual child launch");
    if (!strcmp(test, "success") || !strcmp(test, "warning") || strstr(test, "fallback")) {
        CHECK(!failure_seen, "successful extractor stays successful even without capture");
    } else {
        CHECK(failure_seen && wcslen(message) < 1024, "bounded failure message");
        CHECK(wcsstr(message, target), "actual destination retained");
        CHECK(wcsstr(message, archive), "actual archive retained");
        CHECK(!wcsstr(message, L"space on C:"), "do not invent a full C drive");
        if (state.launch_error != ERROR_FILE_NOT_FOUND)
            CHECK(!wcsstr(message, L"tar.exe was not found") && !wcsstr(message, L"DISM") && !wcsstr(message, L"sfc /scannow"), "other failures do not recommend missing-tool repairs");
        if (state.launch_error == ERROR_FILE_NOT_FOUND) CHECK(!check_missing_guidance(), "missing recovery guidance");
        else if (!strcmp(test, "launch")) CHECK(wcsstr(message, L"Could not start") && wcsstr(message, L"Windows error 5"), "launch error is not child exit");
        else if (!strcmp(test, "query")) CHECK(wcsstr(message, L"Could not read") && wcsstr(message, L"Windows error 6"), "unknown exit status is not invented");
        else {
            if (!strcmp(test, "child_exit_2")) CHECK(wcsstr(message, L"exited with code 2"), "child exit 2 is not a missing executable");
            else
            CHECK(wcsstr(message, !strcmp(test, "high_exit") ? L"exited with code 3221225477" : L"exited with code 23"), "actual unsigned child exit status");
            if (!strcmp(test, "capture_error")) {
                CHECK(wcsstr(message, L"Stderr unavailable") && wcsstr(message, L"Windows error 87"), "capture failure label and OS reason");
                CHECK(!wcsstr(message, L"Tar stderr excerpt"), "capture error is not captured child stderr");
            } else if (strcmp(test, "empty")) CHECK(wcsstr(message, L"authored tar diagnostic"), "bounded child stderr retained");
            if (!strcmp(test, "long") || !strcmp(test, "max_paths")) CHECK(state.converted_length == 511, "511-byte capture unchanged");
            if (!strcmp(test, "max_paths")) CHECK(wcsstr(message, L"excerpt") && wcslen(message) == 1023, "full paths with bounded displayed excerpt");
        }
    }
    printf("PASS %s\n", test); return 0;
}
#endif
