"""Native nn::fs path/name conversions, without a game or a UTF-8 process manifest.

    python -I -B tests/test_fs_path_utf8.py [--cc <Windows clang>]
"""
import argparse
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cc", "gcc"]
RUN_ALL_SKIP = {"linux": "native Windows filesystem conversion APIs"}

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc")
    parser.add_argument("--source", type=Path, default=ROOT)
    args = parser.parse_args()
    if os.name != "nt":
        print("SKIP: native nn::fs UTF-8 conversion fixture runs on Windows")
        return
    cc = args.cc or shutil.which("clang")
    if not cc:
        raise SystemExit("no Windows C compiler (pass --cc)")
    source = (args.source / "host/nn_fs.c").read_text(encoding="utf-8")
    start = source.index("static const wchar_t *fs_wide(")
    end = source.index("static HANDLE fs_CreateFile(", start)
    actual = source[start:end]
    fixture = r'''
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
#define HOS_FS_PATH 1024
/* ACTUAL_CONVERSIONS */
#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL: %s at line %d\n", #c, __LINE__); return 1; } } while (0)
int main(void) {
    wchar_t wide[HOS_FS_PATH + 8], expected[HOS_FS_PATH + 8];
    const char *leaf = "\xe6\xbc\xa2 \xf0\x9f\x8e\xae \xc3\xa9.bin";
    const wchar_t *wleaf = L"\u6f22 \U0001f3ae \u00e9.bin";
    char path[HOS_FS_PATH];
    CHECK(!wcscmp(fs_wide("C:\\fixture\\ascii.bin", wide, HOS_FS_PATH + 8), L"C:\\fixture\\ascii.bin"));
    snprintf(path, sizeof path, "C:\\fixture\\%s", leaf);
    swprintf(expected, HOS_FS_PATH + 8, L"C:\\fixture\\%ls", wleaf);
    CHECK(!wcscmp(fs_wide(path, wide, HOS_FS_PATH + 8), expected));
    snprintf(path, sizeof path, "C:\\%0240d\\%s", 0, leaf);
    swprintf(expected, HOS_FS_PATH + 8, L"\\\\?\\C:\\%0240d\\%ls", 0, wleaf);
    CHECK(!wcscmp(fs_wide(path, wide, HOS_FS_PATH + 8), expected));
    snprintf(path, sizeof path, "\\\\server\\share\\%0240d\\%s", 0, leaf);
    swprintf(expected, HOS_FS_PATH + 8, L"\\\\?\\UNC\\server\\share\\%0240d\\%ls", 0, wleaf);
    CHECK(!wcscmp(fs_wide(path, wide, HOS_FS_PATH + 8), expected));
    WIN32_FIND_DATAW input = {0};
    WIN32_FIND_DATAA output = {0};
    wcscpy(input.cFileName, wleaf);
    wcscpy(input.cAlternateFileName, L"\u00e9~1.bin");
    input.dwFileAttributes = FILE_ATTRIBUTE_ARCHIVE;
    input.nFileSizeHigh = 1, input.nFileSizeLow = 42;
    fs_find_data(&input, &output);
    CHECK(!strcmp(output.cFileName, leaf));
    CHECK(!strcmp(output.cAlternateFileName, "\xc3\xa9~1.bin"));
    CHECK(output.dwFileAttributes == input.dwFileAttributes);
    CHECK(output.nFileSizeHigh == input.nFileSizeHigh && output.nFileSizeLow == input.nFileSizeLow);
    printf("PASS: actual nn::fs conversions: ASCII, Unicode, long drive/UNC paths, both directory names (ACP %u)\n", GetACP());
    return 0;
}
'''.replace("/* ACTUAL_CONVERSIONS */", actual)
    with tempfile.TemporaryDirectory(prefix="hookshot-fs-utf8-") as temporary:
        path = Path(temporary)
        test, exe = path / "conversions.c", path / "conversions.exe"
        test.write_text(fixture, encoding="utf-8")
        subprocess.run([cc, "-std=c11", "-O0", "-Wall", "-Wextra", "-Werror", str(test), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
