#!/usr/bin/env python3
"""Builds a native macOS .app bundle for Hookshot on Apple Silicon.

Creates Hookshot.app with:
- High-resolution Retina display support (NSHighResolutionCapable)
- Apple Silicon native arm64 target metadata
- Dark mode Aqua appearance support
- Direct execution of Hookshot with native Metal or MoltenVK backends

Usage:
    python nx2/make_app.py --dir <game_folder> [--out <output_app_path>]
"""
import argparse
import os
import shutil
import stat
import sys

INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>hookshot_launcher</string>
    <key>CFBundleIdentifier</key>
    <string>com.thelazyproject.hookshot</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Hookshot</string>
    <key>CFBundleDisplayName</key>
    <string>Hookshot</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSSupportsAutomaticGraphicsSwitching</key>
    <true/>
    <key>NSRequiresAquaSystemAppearance</key>
    <false/>
</dict>
</plist>
"""

LAUNCHER_SCRIPT = """#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Respect existing RX_BACKEND if set by user, otherwise defaults to vulkan
# To run natively with Apple Metal: RX_BACKEND=metal open Hookshot.app
export RX_BACKEND="${RX_BACKEND:-vulkan}"
exec ./hookshot "$@"
"""


def make_app(game_dir, out_app=None):
    if not out_app:
        out_app = os.path.join(game_dir, "Hookshot.app")

    contents = os.path.join(out_app, "Contents")
    macos_dir = os.path.join(contents, "MacOS")
    resources_dir = os.path.join(contents, "Resources")

    os.makedirs(macos_dir, exist_ok=True)
    os.makedirs(resources_dir, exist_ok=True)

    # Write Info.plist
    plist_path = os.path.join(contents, "Info.plist")
    with open(plist_path, "w", encoding="utf-8") as f:
        f.write(INFO_PLIST)

    # Write PkgInfo
    pkginfo_path = os.path.join(contents, "PkgInfo")
    with open(pkginfo_path, "w", encoding="utf-8") as f:
        f.write("APPL????")

    # Write launcher script
    launcher_path = os.path.join(macos_dir, "hookshot_launcher")
    with open(launcher_path, "w", encoding="utf-8") as f:
        f.write(LAUNCHER_SCRIPT)
    os.chmod(launcher_path, os.stat(launcher_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Symlink game files and binaries into Contents/MacOS so relative paths resolve cleanly
    binaries = ["hookshot", "hookshot_vk.dylib", "hookshot_metal.dylib", "image.bin", "romfs", "user", "language.txt"]
    for b in binaries:
        src = os.path.join(game_dir, b)
        dst = os.path.join(macos_dir, b)
        if os.path.exists(src) and not os.path.exists(dst):
            try:
                os.symlink(os.path.relpath(src, macos_dir), dst)
            except OSError:
                shutil.copy2(src, dst)

    print(f"Created macOS App Bundle: {out_app}")
    return out_app


def main():
    parser = argparse.ArgumentParser(description="Create macOS Hookshot.app bundle")
    parser.add_argument("--dir", required=True, help="Path to built Hookshot game directory")
    parser.add_argument("--out", help="Output path for Hookshot.app (defaults to <dir>/Hookshot.app)")
    args = parser.parse_args()

    make_app(args.dir, args.out)


if __name__ == "__main__":
    main()
