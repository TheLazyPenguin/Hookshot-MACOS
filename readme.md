<h1 align="center">
  <br>
  <a>
  <img src="assets/hookshot.png" alt="Hookshot" width="200">
</a>

  <br>
  <b>Hookshot</b>
  <br>
</h1>

<h4 align="center">The Legend of Zelda: Ocarina of Time (Nintendo Switch 2) running natively on Windows & Linux, with no emulator.
</h4>


<p align="center">
  <a href="#project-status">Status</a> |
  <a href="#install-and-play">Install and play</a> |
  <a href="#in-game-menu">In-game menu</a> |
  <a href="#if-something-goes-wrong">Problems</a> |
  <a href="#build-from-source">Build from source</a> |
  <a href="#how-it-works">How it works</a> |
  <a href="#want-to-help">Want to help?</a> |
  <a href="#credits">Credits</a> |
  <a href="#license">License</a>
</p>

Hookshot is a static recompilation. The game's code is translated to C and compiled into a Windows or Linux program,
the console's system software is reimplemented, and the Switch 2 graphics are rebuilt on Vulkan. All of this happens
**on your PC, from your own copy of the game**.
<br>

> [!WARNING]
> Some users report the file in releases to be a Trojan - it is not. Feel free to run it through any antivirus software


Discord: https://discord.gg/DVQQJphbBf
<br>

> [!IMPORTANT]
> This repository **does not contain the game, keys or an executable**, and it does not explain how to get them. You
> need your own copy. Everything the build creates (`hookshot.exe`, the generated code, the shader caches and your
> saves) comes from your game and stays on your PC. Never share those files.

## Project status

Experimental. Most testing so far has been around the start of the game. Players have reported on many PCs since:
the table says what works and what does not yet.

| What | Status |
|---|---|
| Kokiri Forest: reaching gameplay and walking around | ✅ Works |
| Sound, controller, keyboard and saves | ✅ Works |
| In-game menu, frame generation and upscaling | ✅ Works |
| Flicker (the picture flashing too bright while moving) | ✅ Fixed in v2.0.2 ([#645](https://github.com/NotRexed/Hookshot/pull/645)) |
| Ground fog vanishing when looking down | ✅ Fixed in v2.0.2 ([#638](https://github.com/NotRexed/Hookshot/pull/638)) |
| Models with missing pieces (doors, fences, parts of trees) | ✅ Fixed where tested, more play needed |
| Stutter when entering new areas | ⚠️ Still happens the first time you visit a place. The next visits are smooth |
| Performance | ⚠️ Depends on the PC: some reach a steady 60 fps, others stay below it, more so in Hyrule Field |
| Hyrule Field, Castle Town, Kakariko and the dungeons | ⚠️ Players got there, with open bugs: striped shadows in Hyrule Field ([#468](https://github.com/NotRexed/Hookshot/issues/468)), some crashes ([#317](https://github.com/NotRexed/Hookshot/issues/317), [#648](https://github.com/NotRexed/Hookshot/issues/648)) |
| Ultrawide and 4:3 | ⚠️ The 3D keeps its shape, but the HUD is stretched and the picture is softer |
| NVIDIA cards | ✅ Works. The most tested |
| AMD cards | ⚠️ Some tested: reports from the RX 6600, RX 7800 XT and RX 7900 XTX. Known issue: the game loses the GPU in the Deku Tree on the RX 6600 ([#708](https://github.com/NotRexed/Hookshot/issues/708), [#614](https://github.com/NotRexed/Hookshot/issues/614)) |
| Intel cards | ❓ Few reports, many of them black screens or crashes ([#17](https://github.com/NotRexed/Hookshot/issues/17)) |
| Cards without mesh shaders (such as AMD RX 5000 and older) | ❌ Not supported: parts of the picture are missing. Since v2.0.6 a fallback runs the mesh programs as compute shaders on cards with buffer device addresses ([#640](https://github.com/NotRexed/Hookshot/issues/640)); it leaves out the mesh draws that take their count from a buffer |
| Linux | ✅ Works with the AppImage. Tested on several distributions (CachyOS, Fedora, Bazzite, SteamOS) and cards, with open problems on some AMD cards ([#604](https://github.com/NotRexed/Hookshot/issues/604), [#528](https://github.com/NotRexed/Hookshot/issues/528)) |

## Install and play

The game does not come ready-made: Hookshot Builder builds it on your PC from your copy. You do this once. After that
you start the game from its launcher, which also updates it.

### What you need

- **Your copy of the game at the supported version:** program `0400486024DEC000`, update v131072, build `e0f3ccfa`.
  Other versions do not work. A `.nup` file, or the `romfs` and `exefs` folders.
- 64-bit Windows 10 or 11, or 64-bit Linux with glibc 2.35 or newer (Ubuntu 22.04, Debian 12, Fedora, Arch,
  SteamOS ...) and a CPU with AVX2. The Linux AppImage needs AVX2; on Windows, and in a build from source, a CPU
  without it gets a game built for what it has, a little slower.
- A graphics card with Vulkan 1.3 and mesh shaders, with an up-to-date driver: NVIDIA GeForce RTX 20 series or newer,
  AMD Radeon RX 6000 series or newer, or Intel Arc. On Linux, Mesa or NVIDIA's driver. Cards without mesh shaders are
  not supported.
- 8 GB of video memory (VRAM) or more is recommended. Cards with less can use the in-game menu's lower Quality presets.
- 16 GB of RAM or more. A run uses about 10 GB.
- About 60 GB free while building, on an SSD if you can: a hard drive makes the build much slower. You can build on one
  anyway; the builder says so first.
- An internet connection for the download. Nothing else to install: the builder brings its own compiler and tools.

### On Windows

1. Open the [latest release](https://github.com/NotRexed/Hookshot/releases/latest) and download `HookshotBuilder.exe`.
2. Run it. It downloads the rest of Hookshot Builder (about 500 MB), checks it, and opens it.
3. Pick your game. The builder looks for `.nup` files in your Downloads, Desktop and Documents folders and lists them
   under **Found on this PC**. Not listed? Press **Browse…**, drop the file on the window, or choose
   **romfs and exefs folders**. The builder checks that it is the right version.
4. Under **Install the game to**, keep the folder (`Games\Hookshot` in your user folder) or press **Change**. Choose
   the **Game language**.
5. Press **Build the game**. It takes about 10 to 45 minutes, depending on your CPU and memory. You can use your PC in
   the meantime.
6. When it says **Your game is ready**, press **Play**. The **Desktop shortcut** and **Start menu entry** boxes are
   ticked: untick them if you don't want them.

Next time, start the game from the Hookshot shortcut, or `hookshot.exe` in the game folder. That is the launcher: it
has **Play**, and **Update** when a newer release is out.

The first start prepares the game's shaders, which takes a while. Later starts are faster.

### On Linux

1. Open the [latest release](https://github.com/NotRexed/Hookshot/releases/latest) and download
   `Hookshot-<version>-x86_64.AppImage`. It is Hookshot Builder with everything it needs inside.
2. Allow it to run as a program. In most file managers: right-click it, open **Properties**, and turn on
   "Allow executing file as program" (the words differ between desktops). Or in a terminal:
   `chmod +x Hookshot-*-x86_64.AppImage`.
3. Double-click it. The Hookshot Builder window opens.
4. Under **Game files**, choose **.nup file** or **romfs and exefs**, then press **Browse** to pick them. The builder
   checks the version.
5. Under **Save the game to**, keep `~/Games/Hookshot` or choose another folder. Choose a **Language**.
6. Press **Build**. It takes about 10 to 45 minutes, depending on your CPU and memory.
7. When it says "Your game is ready", press **Play**.

The game is also added to your applications menu as "Hookshot". That entry, and `hookshot` in the game folder, open the
launcher: **Play**, and **Update** when a newer release is out. Keep the AppImage where it is: the launcher uses it to
update.

The same AppImage also builds and starts the game without opening the window, for a machine you reach over SSH or for a
script: see [Linux, the AppImage from the command line](#build-from-source).

### Updating

When a new release is out, the launcher says "Update available". Press **Update**: in `hookshot.exe` on Windows, or in
`hookshot` (or the AppImage) on Linux. It downloads only the parts that changed and builds the game again in the same
folder. The build files of the last build are gone by then (see [Where the files go](#where-the-files-go)), so an
update takes about as long as the first build. Your saves and settings are kept. What changed is on the
[Releases page](https://github.com/NotRexed/Hookshot/releases).

<details>
<summary>What an update keeps and replaces, and updating from the command line</summary>

To be safe, copy your saves somewhere first: the `user` folder in the game folder on Windows, or
`~/.local/share/hookshot` on Linux.

| Kept | Replaced |
|---|---|
| Your saves (`user`, or `~/.local/share/hookshot` on Linux) | The game in `bin` and its files |
| `hookshot_options.ini`, the in-game menu's choices and your controls | `image.bin` and the shader list |
| `hookshot_env.txt` | `language.txt`, written again with the game's language |
| `mods` | |

The game files the first build read are kept in the game folder, so an update does not need your `.nup` again.

From a clone: `git pull`, then `python -I nx2/make_game.py --update <game folder>`. The Linux AppImage does the same
with `--update <game folder>`.

</details>

### Where the files go

- The build reads your game and never changes it. It writes to the folder you choose and to the builder's own folder:
  `%LOCALAPPDATA%\HookshotBuilder` on Windows, `~/.cache/hookshot-builder` on Linux.
- The romfs is hard-linked instead of copied where the disk allows it.
- The build files (about 4 GB: the translated code and the compiled objects) are deleted once the game is ready. None
  of them are needed to play. To keep them, so that an update compiles only what changed, set the environment variable
  `HOOKSHOT_KEEP_BUILD_FILES=1` for the builder; on Windows, **Free up space** on the "Your game is ready" page then
  deletes them when you want. The build files folder can be moved before a build (**Change**, **Default**).
- Saves: the `user` folder in the game folder on Windows, `~/.local/share/hookshot` on Linux (a `user` folder from an
  earlier Linux build is moved there once). `--user <folder>` puts them somewhere else ([command line
  arguments](#running-the-game-from-the-command-line)).
  To carry on with a save from an emulator (Lichii, Eglantine, Orchid, ...) or NX2navi, or to take yours there, see
  [using a save from an emulator](docs/saves.md).
- To uninstall, delete the game folder, the builder's folder and the shortcuts.

### If something goes wrong

| Problem | What to do |
|---|---|
| Where is the log? | `hookshot_log.txt` in the game folder holds the last run. The four runs before are `hookshot_log.1.txt` (the last) to `.4.txt`. Started from a terminal, the game prints there instead. Every 600 frames it has a `vk: status:` line: the video memory in use of what the driver allows, and DLSS's details while it draws; `vk: over the driver's video-memory allowance` says when the game passed it |
| "Hookshot supports build e0f3ccfa" or "This version isn't supported" | Check that you chose the right game with its update installed |
| The game opens and closes, or the log says "device lost" | Update your graphics driver. On AMD cards there are known crashes ([#708](https://github.com/NotRexed/Hookshot/issues/708), [#614](https://github.com/NotRexed/Hookshot/issues/614)) |
| Parts of the picture are missing, or a message says your card has no mesh shader support | The card or its driver has no mesh shaders. Update the driver; older cards are not supported ([#640](https://github.com/NotRexed/Hookshot/issues/640)) |
| AMD: blocky textures, solid rectangles in the sky or unusually dark courtyard surfaces | Try the [RGBA8 texture workaround](#amd-texture-workaround). It uses more graphics memory |
| Linux: the game does not start or the picture is broken | The game needs a Vulkan 1.3 driver with mesh shaders. Check with `vulkaninfo \| grep mesh`: it should list `VK_EXT_mesh_shader`. Update Mesa or the NVIDIA driver |
| Steam Deck: the game freezes and closes in Kokiri Forest or the Great Deku Tree (`gfx_0.0.0 timeout` in `journalctl -k`) | `RX_VK_MESH_NOCULL=2c56dc1006942f74` in `hookshot_env.txt` gets past it with every model drawn (the culling pass that runs for seconds is turned off). `RX_VK_SKIP_CODE=2c56dc1006942f74` also gets past it, but the models those draws make go missing (see the [development guide](docs/development.md#switches-for-testing-and-debugging), [#817](https://github.com/NotRexed/Hookshot/issues/817)) |
| "Your antivirus removed part of the build tools" | A false alarm on unsigned programs. Restore the files from Windows Security's Protection history, or add `%LOCALAPPDATA%\HookshotBuilder` to its exclusions, then press **Repair** |
| Stutter the first time you see something | Normal for now: shaders are being prepared. It gets better when you pass through the same place again |
| The game is in the wrong language | Change the code in `language.txt` in the game folder. The file lists them all |

If the problem continues, [report it](https://github.com/NotRexed/Hookshot/issues/new/choose) with the version, where
you were in the game, your graphics card, `hookshot_log.txt` and a screenshot or video. Never send game files.

#### Low FPS or stutter

Walk through the same spot twice after shader preparation finishes. Note whether the slowdown clears on the
second pass or lasts until you restart the game. For a slowdown after an update, compare the same spot and
settings on both versions if you still have the earlier build. Turn off **Frame generation** for both runs so the
FPS reflects game frames, and keep the resolution, upscaler and frame rate cap the same.

Attach the log from the slow run and, if available, the one from the earlier build. Say where the FPS dropped and
keep the lines around the drop that show `presents`, `GPU time`, `waits for shaders or pipelines`, `VRAM:` and
`memory heaps`. Compare total and per-heap memory use with the driver's allowances. The texture cache has a
separate budget on the `VRAM:` line.

If the GPU time stays high, a separate run with `RX_VK_PASS_TIMING=1` in `hookshot_env.txt` reports which GPU
passes take the time every 600 presents. Keep the unprofiled log for the FPS comparison since the timing itself
adds work. Remove the switch after collecting the log. The [development guide](docs/development.md#time-and-profiles)
has more switches.

#### AMD texture workaround

For these AMD texture artifacts, try keeping decoded ASTC textures as RGBA8 instead of re-encoding them to BC3
([#57](https://github.com/NotRexed/Hookshot/issues/57), [#1006](https://github.com/NotRexed/Hookshot/issues/1006)).
Close the game, then create or edit `hookshot_env.txt` in the built game folder, beside `image.bin`, and add:

```ini
RX_VK_ASTC_RGBA8=1
```

Restart the game. The same setting applies when Steam or RecompLauncher starts that game folder.

This is a workaround for some artifacts, not a general lighting fix. It can substantially increase graphics-memory
use and cause stalls when the card runs out of headroom. To undo it, remove that line and restart the game.

## In-game menu

By default, press <kbd>Insert</kbd> or <kbd>F1</kbd> in game. On a controller, press Home or Select and Start together; on
a DualShock 4 or DualSense, clicking the touchpad does the same as <kbd>F1</kbd>.
The same keys close it, and so does <kbd>Esc</kbd>. <kbd>F1</kbd> always works; **Controls → Menu shortcut** can leave
<kbd>Insert</kbd> free for another overlay. The menu has four tabs, Graphics, Gameplay, Controls and Debug:
<kbd>Q</kbd> and <kbd>E</kbd> (or <kbd>Tab</kbd> and <kbd>Shift</kbd>+<kbd>Tab</kbd>) switch between them, LB and RB on
a controller (or the triggers). <kbd>Up</kbd> and <kbd>Down</kbd> choose a row, <kbd>Left</kbd> and <kbd>Right</kbd>
change it (<kbd>Enter</kbd> changes it too); beside the rows, the help says what the row is and, on a line of its own,
what the value chosen does. On a controller the D-pad chooses and changes, A changes too and opens a page (Motion,
Controls, the Teleport list, the inventory), and B goes back or closes the menu: A and B are the buttons your layout puts the Switch's A and B
on (with the Nintendo layout, A is the right face button). The mouse is free while the menu is open: click a tab, click a row's name to choose it (its
value stays), click the left or right half of a value to lower or raise it, drag a slider, turn the wheel to scroll the rows (it never changes a value), and right-click to go back. The
button prompts at the bottom show the keys or the controller's buttons, whichever you used last. Your choices are saved
in `hookshot_options.ini` in the game folder.

The menu, the FPS counter and the start-up screen are drawn in the style of the game's own menus. They use the game's
own menu font, read into memory from your game files (the romfs folder the game runs from) the first time one of them is
drawn. It is never copied anywhere, and Hookshot does not include it. Without it, or if it has no Latin letters, they use
Libertinus, which Hookshot includes.

The rows marked "after a restart" below are read when the game starts. While one is changed, it is tagged "After
restart" and the help on the Graphics tab lists it; closing the menu then asks whether to restart now. **Later** keeps
the change for the next start (and is not asked again until you change one of those rows); **Restart now** saves your
choices and starts the game again, so progress since your last save is lost.

A row for something this PC cannot use is not shown: NVIDIA Reflex and AMD Anti-Lag 2 without a GPU and driver that
have them, the Upscaler where nothing but the game's own runs, the DLSS model where DLSS does not run. HDR paper white and
HDR peak brightness show only while HDR is on.

| Tab | Option | Choices | Default |
|---|---|---|---|
| Graphics | Quality preset | Custom, Minimum (4GB), Low (6GB), Balanced (8GB), High (12GB), Ultra (16GB+) | Custom |
| | Fullscreen | Off, On (the same as <kbd>F11</kbd>) | Off |
| | GPU device | Auto, or each graphics card by name (after a restart) | Auto |
| | Frame generation | Off, Auto, 2x to 8x | Off |
| | Frame pacing | Off, On | Off |
| | HDR | Off, Expanded, Native (the game's) | Off |
| | HDR paper white | 80 to 400 nits (while HDR is on) | 200 nits |
| | HDR peak brightness | 400 to 4000 nits (while HDR is on) | 1000 nits |
| | Game frame rate cap | 60, 90, 120, 144, 165, 240 FPS (after a restart) | 60 FPS |
| | NVIDIA Reflex | Off, On, On + Boost (shown only on NVIDIA GPUs with `VK_NV_low_latency2`) | Off |
| | AMD Anti-Lag 2 | Off, On (shown only on AMD GPUs with `VK_AMD_anti_lag`) | Off |
| | Output resolution | 1920x1080, 2048x1152, 2560x1440, 3840x2160, 5120x1440, 5120x2880 (after a restart) | 2048x1152 |
| | Upscaler | Game's own, NVIDIA DLSS, NVIDIA DLAA (only in builds with NVIDIA's DLSS SDK, below; DLSS and DLAA on RTX GPUs), AMD FSR 3.1 (every build, on GPUs it runs on, below), AMD FSR 4, AMD FSR 4 Native AA (only in builds with FSR 4, below) | Game's own |
| | DLSS model | Transformer (K), Transformer 2 (M), Transformer 2 (L), NVIDIA default (shown where DLSS runs; used by DLSS and DLAA) | Transformer (K) |
| | Render resolution | Auto (the game's own dynamic resolution), 100%, 75%, 67%, 50% (each with its size). With DLSS, FSR 3.1 or FSR 4: Auto, Quality (67%), Balanced (58%), Performance (50%), Ultra Performance (33%). With DLAA or FSR 4 Native AA: Native | Auto |
| | Window scaling filter | Off, Catmull-Rom, Lanczos | Off |
| | Sharpness | 0 to 100%, in steps of 10 | 0% |
| | Anisotropic filtering | Game's, 2x, 4x, 8x, 16x | 16x |
| | Profile | Docked, Handheld (after a restart) | Docked |
| | Ultrawide | 16:9, Monitor's shape: wider than 16:9, or narrower down to 5:4 (after a restart) | 16:9 |
| | Robust buffers | Auto, Off, On (after a restart) | Auto |
| Audio | Volume | 0 to 100%, in steps of 5 | 100% |
| | Mute in background | Off, On | Off |
| | Audio output | Auto, Stereo, 5.1 (after a restart) | Auto |
| Gameplay | FPS counter | Off, On | Off |
| | Menu size | Auto, Small, Medium, Large | Auto |
| | Game speed | Per frame, Real time | Real time |
| | Text speed | Normal, 2x, 4x, Instant | Normal |
| | Text size | Original, 110%, 125%, 150%, 175% (dialogue, Navi and signs) | Original |
| | Microphone | Off, Default, or each microphone by name | Default |
| Controls | Controller in background | Off, On | Off |
| | Mouse camera | As the stick, Native | As the stick |
| | Disable camera centering | Off, On | Off |
| | Mouse sensitivity | 0.10 to 5.00 | 1.00 |
| | Invert mouse vertical | Off, On | Off |
| | Invert camera X | Off, On | Off |
| | Invert camera Y | Off, On | Off |
| | Stick dead zone | Default (24%), 5%, 10%, 15%, 20%, 30% | Default (24%) |
| | Rumble strength | Off, 25% to 150%, in steps of 25 | 100% |
| | Layout preset | Nintendo (Def), Xbox / PC, Swap Face, Custom | Nintendo (Def) |
| | Motion | Opens the Motion page: Motion controls (Off, On; On), Motion sensitivity X (10% to 600%) and Y (10% to 300%; 100%), Invert motion X and Y (Off, On; Off), Motion deadzone (Low, Standard, High; Standard) | |
| | Controls | Opens the Controls page | |
| | Menu shortcut | Insert or F1, F1 only | Insert or F1 |

- **Quality preset** sets Render resolution, Window scaling filter, Sharpness, Frame pacing, Game speed, Profile
  and the video memory limits for a card with that much memory. It leaves the Upscaler and Frame generation as
  you chose them: with DLSS, FSR 3.1 or FSR 4, the preset's resolution becomes their nearest mode. Changing most other
  rows yourself sets it back to Custom.
- **Menu size** is how large the menu, the FPS counter and the start-up screen are drawn. Auto is Large in fullscreen on a
  screen of 1080 lines or more while you use a controller (a TV across the room), else Medium.
- **GPU device** matters on a PC with more than one graphics card (a laptop's integrated and dedicated GPUs, or a
  second card for Lossless Scaling). Auto prefers a dedicated one, and only cards with Vulkan 1.3 are listed.
  `hookshot_log.txt` lists every card as `vk: device <n>`; `RX_VK_DEVICE=<n>` chooses one for a single run and wins
  over the menu.
- **Frame generation** makes extra frames between the game's own. It adds a little input delay, and fast motion can
  show artifacts. The renderer's own interpolation makes the frames; at 2x, AMD FSR 3.1's frame interpolation can make
  it instead with `RX_VK_FSR_FG=1` (below: it moves the HUD with the scene, so it is not the default). **Frame pacing** shows frames at an even interval: less stutter, up to one frame of delay. It paces
  the frames that frame generation shows, so it has no effect while Frame generation is Off.
- **Game frame rate cap** limits the frames the game renders. With a cap of 60 and Frame generation at 2x, the output
  can reach 120 FPS. Choose **Auto** in Frame generation to target the display's refresh rate instead of a fixed multiplier.
  A cap **past 60 is experimental**: the game keeps real time, but some cutscenes and bosses still count frames and can
  misbehave (Gohma running into the wall, the intro's narration running ahead: #1742). 60 is the safe choice.
- **The scaling rows**, in the picture's order: **Output resolution** is the size of the game's whole frame, HUD
  included. The **Upscaler** fills it from the 3D: the game's own network, NVIDIA DLSS or DLAA (the 3D at full size,
  edges smoothed), AMD FSR 3.1, or AMD FSR 4 or its Native AA (below). DLSS and DLAA look softer than the game's own: set
  **Sharpness** to around 80% with them. **DLSS model**
  chooses their network (below). **Render
  resolution** is the 3D's share of the output. The **Window scaling filter** then scales the frame to your window,
  and **Sharpness** sharpens it, by the picture's pixels: when the window is much larger than the picture (the Handheld
  Profile's 1536x864 on a 4K screen), a Sharpness kept from an older version is stronger than it was, so a lower one may
  suit.
- **Output resolution:** its rows below show the sizes for the output you chose. Docked only. On a 1920x1080 display,
  the 1920x1080 option keeps HUD and text sharp when the game fills the screen by mapping them pixel for pixel. At
  3840x2160 the game's render targets get a bigger GPU pool, so a full-size 3D fits. On a 5120x1440 (32:9) ultrawide
  monitor, 5120x1440 gives a native frame with a sharp HUD. Set **Ultrawide** to Monitor's shape with it: it widens the
  cameras to the frame's shape and keeps the HUD and movies in the middle 16:9; without it, the game's 16:9 picture is
  stretched across the 32:9 output, sharp but wide. For a size the menu does not offer (3440x1440, 2560x1080, ...), set
  `output_res=<width>x<height>` in `hookshot_options.ini`: each side a multiple of 8, at least 640x360, at most 5120x2880's
  pixels, and between 5:4 and 32:9 in shape; anything else uses the game's 2048x1152. The menu then offers it as its own
  choice. With **Ultrawide** on, a picture wider than 16:9 is kept to 3840x2160's pixels, so above that a wide size is not a
  native frame. For one run, set `HOS_OUTPUT_RES` to a size, such as `HOS_OUTPUT_RES=3840x2160`.
- **Window scaling filter** matters only when your window's size differs from the Output resolution: for the sharpest
  picture, set the Output resolution to your screen's, and the row shows "Not needed (window = output)". It and
  **Sharpness** also work when Frame generation is Off.
- **Anisotropic filtering** keeps textures sharp on surfaces seen at a slant: the paths and floors ahead of Link. The game
  asks for 1x or 2x, which at a PC's resolutions smears the ground a few metres off; 16x costs little on most cards, and
  Game's is the console's own. `RX_VK_ANISO=<n>` sets it for one run (0: the game's).
- **Texture detail with DLSS, FSR 3.1 or FSR 4:** below 75% Render resolution, the world's textures are sampled one finer
  mip step for each halving of the 3D (the game already does so for its own 75%), so the upscaled picture keeps their
  detail. `RX_VK_UPSCALE_LOD_BIAS=0` turns it off.
- **NVIDIA Reflex** Off is the game as without it. `RX_VK_REFLEX_LOG=1` logs the driver's latency timings every 300
  frames while it is on.
- **AMD Anti-Lag 2** Off is the game as without it. Like Reflex, it is not used while Frame generation is on.
- **Profile** runs the game as the console docked (at the Output resolution) or Handheld (1536x864): lighter on the GPU.
- **Robust buffers:** a read past a buffer's end is dropped instead of stopping the GPU. Auto is on, on every card; Off
  can be faster on some NVIDIA cards.
- **Game speed:** with Per frame, the game runs slower whenever it is below 60 fps. Real time keeps it at normal speed
  down to 15 fps.
- **FPS counter** shows in the top right corner. With frame generation on, it also shows the game's own rate.
- **Volume** scales the game's whole sound, on top of the game's own sound settings and Windows' volume. Its steps
  follow a curve so they sound about even: 50% is a quarter of the level (-12 dB). **Mute in background** silences the
  game while another window has the focus; an overlay such as Steam's or Discord's does not count as another window
  while the game was in front.
- **Audio output** is the speakers the game mixes its sound for. Auto is 5.1 when your default output device has 5.1
  or more speakers, else stereo; Stereo or 5.1 chooses one whatever the device has (5.1 on stereo speakers is mixed
  down). For one run, `HOS_AUDIO_CHANNELS=2` or `6` chooses stereo or 5.1 and wins over the menu.
- **Microphone** is what the ocarina hears when the game's own microphone option is on (an instrument, or humming).
  Default follows Windows' default recording device; the list shows each microphone by name, and a change applies at
  once. A chosen microphone that is unplugged stays chosen (shown as not connected): Default stands in until it is
  back. On Linux (SDL2) two microphones with the same name cannot be told apart: the first is used. Windows must allow desktop apps to use the microphone
  (Settings, Privacy & security, Microphone). `HOS_MIC_LOG=1` logs what the game reads, a line a second.
- **Controller in background:** On keeps the controller working while another window has the focus. The keyboard and
  mouse still need the game's window.
- **Mouse camera:** Native turns the camera with the mouse one to one, as in a PC game. As the stick uses the mouse in
  place of the right stick. The <kbd>-</kbd> and <kbd>=</kbd> keys change the sensitivity in game too.
- **Disable camera centering:** On stops the game gradually turning the camera toward your movement, so it does not fight
  native mouse look. Off keeps the game's standard behavior. Changes apply immediately with either Mouse camera mode.
  Manual controls, explicit recentering and scripted camera headings still work; automatic pitch adjustment is unchanged.
- **Stick dead zone:** how far a stick moves before it counts, on each axis. Default is XInput's (about 24%); lower suits
  a precise stick, higher one that drifts. The game keeps a dead zone of its own after it.
- **Rumble strength** scales the controller's rumble: 100% is the game's own, Off turns it off. The game's HD rumble
  goes to a controller's heavy and light motors by its frequency.
- **Motion controls** (Controls tab, Motion page): the controller's gyroscope aims where the game uses motion, as on the Switch. It works with
  Switch Pro controllers and pads in Switch mode, DualSense and DualShock 4 (through SDL). Its row
  says whether the connected pad has a gyroscope; Off leaves the game seeing a pad lying still. **Motion sensitivity X/Y**
  scale the left-right and up-down aim (100% is the console's), **Invert motion X/Y** turn either direction around. The game gets the motion
  state as a Switch (and Eden) builds it, so how you hold the pad when motion starts does not matter. Motion follows the pad used
  last. The gyroscope's drift is learned while the pad rests on a table, so set it down for a second if the aim
  creeps. `HOS_MOTION_DEBUG=1` (in `hookshot_env.txt`) logs what the game gets twice a second.
- **Layout preset:** Nintendo has A on the right face button, Xbox / PC and Swap Face put A on the bottom one. Changing
  a button yourself sets it to Custom.

### Controls

Use a controller, or the keyboard and mouse. On the keyboard, <kbd>W</kbd> <kbd>A</kbd> <kbd>S</kbd> <kbd>D</kbd> move
and the arrow keys (or <kbd>I</kbd> <kbd>J</kbd> <kbd>K</kbd> <kbd>L</kbd>) turn the camera.
With the default keyboard bindings, press <kbd>E</kbd> to select **New Game** on the title screen.

**Mouse in the game's menus (Windows):** the title screen and its file list, the pause menu, the Key Items, Threads of
Time and Map pages, the options and the save dialogs free the mouse while they are shown. Point at an entry to select
it, left-click to choose it (A) and right-click to go back (B); the tabs, the L and R signs and the Back prompt can be
clicked too. The wheel turns the pause menu's pages and scrolls lists; on the map it changes floors and zooms. Drag
with the left button to pan the map and the tapestry or turn a stone on Key Items. The cursor stays hidden while you
play on a controller or the keyboard, until the mouse moves.

**Rumble:** a Nintendo Switch Pro Controller or Joy-Con plays the game's HD rumble as the Switch does, each side and
both frequency bands as the game asks, with SDL3 (the Windows game brings it; on Linux the system's SDL3, where it has
one). Other controllers, Switch 2 controllers, a pair of Joy-Cons used as one controller, and SDL2's own library get
the game's rumble on their two motors. The menu's Rumble strength scales it too. `HOS_HD_RUMBLE=0` sends the Switch
controllers the motor rumble too. On Linux, SDL talks to the Switch controller itself through its hidraw device, which
needs read and write access for your user; Steam's udev rules (the `steam-devices` package on most distributions) give
it. Without them the kernel's hid-nintendo driver runs the controller, and it gets the motor rumble. HD rumble goes to
anything SDL reports as a Switch Pro Controller or Joy-Con, and that includes third-party controllers in Switch mode
(8BitDo, GameSir and others; SDL gives them Nintendo's ids). Some of them may turn it into weak rumble or none: set
`HOS_HD_RUMBLE=0` to give them the plain motor rumble.

To change which gamepad button or key presses a Switch button, or which keys move and turn the camera, open the
Controls tab's Controls page. Choose a row and a column (Gamepad or Keyboard), press <kbd>Enter</kbd> (or the bottom
face button), then the new button or key. <kbd>Esc</kbd> cancels, <kbd>Delete</kbd> clears it, and Reset to defaults
puts them all back. A gamepad button taken from another Switch button swaps with it. The page saves them in
`hookshot_options.ini`.

<details>
<summary>Writing the controls in hookshot_options.ini yourself</summary>

```ini
pad_a=0
key_a=69,13
```

`pad_<button>` is a gamepad input by position: 0 bottom face button, 1 right, 2 left, 3 top, 4 Select or Back, 5 Home,
6 Start, 7 and 8 the stick presses, 9 and 10 the shoulder buttons, 11 to 14 the D-pad (up, down, left, right), 15 and
16 the triggers, -1 none. `key_<button>` is one or two
[Windows key codes](https://learn.microsoft.com/windows/win32/inputdev/virtual-key-codes) in decimal (69 is
<kbd>E</kbd>, 13 <kbd>Enter</kbd>), 0 none; the mouse's buttons are 1 (left), 2 (right), 4 (middle), 5 and 6 (side
buttons), and count while the mouse is captured. The buttons are `a` `b` `x` `y` `l` `r` `zl` `zr` `plus` `minus` `ls`
`rs` `left` `up` `right` `down`, and for keys only the left stick's and the camera's directions: `move_up`
`move_down` `move_left` `move_right` `cam_up` `cam_down` `cam_left` `cam_right`. A button the file leaves out keeps
its default.

</details>

## Mods

Put mods in a `mods` folder in the game folder, beside `hookshot.exe` (or point `HOS_MODS` at another folder), in the
layout emulators use: `mods/<name>/romfs/...` holds files that replace or add to the game's own. Deeper layouts such as
`mods/contents/<title id>/<name>/romfs` work too. A folder whose name starts with `-` or `_` is off. When two mods
have the same file, the one whose folder name sorts last wins, so name them `01-...`, `02-...` to set the order.

Only RomFS mods are loaded. `exefs` patches (`.pchtxt`, `.ips`) are left out: Hookshot compiles the game's code ahead
of time, so patching its instructions would need a rebuild. The log (`hookshot_log.txt`) names each mod and the files
read from it.

A mod file larger than the game's own does not load unless the resource size table allows for it:
`System/Resource/ResourceSizeTable.Product.111.Nin_Ounce_NVN2.rsizetable.zs` gives each file the memory the game sets
aside for it (by the CRC32 of its path without `.zs`; for a texture, its decompressed size + 280). Past that, the game
goes on without the mod's file, or a loading screen waits for good. A mod that makes files bigger (HD
textures, longer parameter files) ships the table with its entries grown. Since only one mod's table is used, mods that
each grow files need one table with all their entries, in the mod that sorts last.

## Build from source

For developers, and for players who prefer the command line. The builder windows run the same script,
`nx2/make_game.py`. [CONTRIBUTING.md](CONTRIBUTING.md) has more.

<details>
<summary>Windows, from the command line</summary>

```powershell
python -I nx2/make_game.py --nup "C:\path\your-game.nup" --out "C:\Games\Hookshot" --language en-US
python -I nx2/make_game.py --romfs "C:\path\romfs" --exefs "C:\path\exefs" --out "C:\Games\Hookshot" --language en-US
```

Add `--check` with your `.nup` or `--exefs` to only check the game's version. It builds nothing.
Add `--log "C:\path\build.log"` to also save the build's output to a file (UTF-8, replaced if it exists); it works
with `--check` and `--update` too, and on Linux.
`HOOKSHOT_JOBS=<n>` (or `--jobs <n>`) limits how many files compile at once.
`HOOKSHOT_MEM_LIMIT_GB=<n>` lets the compilers take that many GB together, whatever is free now; up to 4 always run.

You need:

- Python 3 from python.org (the Microsoft Store's Python installs packages where `python -I` does not look), with
  `pip install -r requirements.txt` (core tools plus the button-prompt packages).
- [llvm-mingw](https://github.com/mstorsjo/llvm-mingw) (the `ucrt-x86_64` build), unpacked as `llvm-mingw` in the
  clone or with `HOOKSHOT_MINGW` set to its folder. Without it the build uses the clang from
  [emsdk](https://github.com/emscripten-core/emsdk) at `C:\emsdk` with Visual Studio's C++ tools and the Windows SDK
  (`HOOKSHOT_MSVC=1` forces that route).
- What the builder's `tools` folder carries and a clone does not. Run `HookshotBuilder.exe` once: the folder is
  `%LOCALAPPDATA%\HookshotBuilder\versions\<version>\HookshotBuilder\tools`. The builder sets the variables itself;
  from the command line, set them before you run `make_game.py`:
  - `tools\cpm`: the Vulkan headers and FFmpeg. Set `RX_CPM` to this folder. Without it (and without system
    Vulkan / SPIR-V / VMA headers or `HOOKSHOT_*_HEADERS`), the standalone build stops instead of shipping a
    game with no renderer.
  - `tools\wgpu-native`: set `WGPU_NATIVE` to this folder.
  - `tools\third_party`: the prebuilt files a clone lacks (`a64emit`, `lld-link`, `zbic` and SDL2). Copy its `.dll`,
    `.exe`, `.lib` and `.sha1` files to the same places under `third_party\`.
  - `tools\work`: copy it to `work\`. It holds the hot-function list, the link order, the profile and the icon;
    without them the game builds but runs slower.
- Visual Studio 2022 with .NET 8, only if you want to change the builder itself.

</details>

<details>
<summary>Linux, the AppImage from the command line</summary>

```sh
./Hookshot-<version>-x86_64.AppImage --cli --nup ~/your-game.nup --out ~/Games/Hookshot   # make_game.py's options
./Hookshot-<version>-x86_64.AppImage --play                    # the game the builder built last, without the window
./Hookshot-<version>-x86_64.AppImage --play ~/Games/Hookshot   # the game in that folder
./Hookshot-<version>-x86_64.AppImage --update ~/Games/Hookshot # the new release, and that folder built again
```

`HOOKSHOT_JOBS=<n>` (or `--jobs <n>` with `--cli`) limits how many files compile at once.
`HOOKSHOT_MEM_LIMIT_GB=<n>` lets the compilers take that many GB together, whatever is free now. Linux stops a compiler
that does not fit; it is then compiled again alone at the end.

In a game folder, `hookshot` is the launcher and the game itself is `bin/hookshot`. The builder's settings are in
`~/.config/hookshot/builder.ini`.

</details>

<details>
<summary>Linux, without the AppImage</summary>

You need `clang` and `lld` (LLVM 23 or newer reads the play profile; an older one builds without it), Python 3 with
`pip install -r requirements.txt`, FFmpeg's development files (with dav1d, for the movies) and SDL3 (SDL2 works too).
Then run `python -I nx2/make_game.py ...` as on Windows. Vulkan / SPIR-V / VMA headers come from the distro, from
`HOOKSHOT_*_HEADERS`, or from a CPM cache via `RX_CPM`.

`scripts/linux/deps.sh` fetches and builds all of these into `build-linux/deps`, and `scripts/linux/appimage.sh` makes
the AppImage from them. A folder built from a source checkout has no launcher: `hookshot` there is the game.

</details>

<details>
<summary>The Windows game, built on Linux</summary>

Unpack llvm-mingw's Linux build (`ucrt-ubuntu-22.04-x86_64`), then run `make_game.py` with `RX_TARGET=windows` and
`HOOKSHOT_MINGW` set to its folder. The objects go to `~/.cache/hookshot-builder-windows`, apart from the Linux game's.
The game folder runs under Proton or on Windows.

</details>

### Running the game from the command line

The built game is `bin\hookshot.exe` on Windows and `bin/hookshot` in a packaged Linux game folder. A build from a
source checkout has `hookshot.exe` or `hookshot` in its build folder, with no launcher beside it. The `hookshot.exe`
or `hookshot` launcher in the game folder does not pass these arguments to the game, so start the game directly to
use them.

| Argument | What it does |
|---|---|
| `image.bin` | The game image to run. Without it the game uses the `image.bin`, `romfs` and `user` in its folder |
| `--romfs <folder>` | The extracted RomFS folder |
| `--user <folder>` | Where the game keeps per-user data: saves, caches and temp files (and `mouse_sens.txt` when `HOS_MOUSE_SENS` is set; the menu keeps the sensitivity otherwise). Default: `user` in the game folder on Windows, `~/.local/share/hookshot` on Linux; with an explicit image path, `user` in the current folder |
| `--trace` | Log every Horizon OS call (the same as `HOS_TRACE=1`) |
| `--prepare-shaders` | Prepare the shaders as the first start does, then exit without starting the game (no build step runs it) |

For example, keep saves somewhere else:

```powershell
cd "C:\Games\Hookshot"
.\bin\hookshot.exe --user "D:\Hookshot data"
```

```sh
cd ~/Games/Hookshot
./bin/hookshot --user "$HOME/hookshot-data"
```

`hookshot_env.txt` and the other test switches are documented below.

<details>
<summary>AMD FSR 3.1 (every build)</summary>

**AMD FSR 3.1** in the Graphics tab's **Upscaler** row (`dlss=3` in `hookshot_options.ini`; `RX_VK_FSR=1` for one run,
`RX_VK_FSR=0` never) upscales in place of the game's own network, and with **Frame generation** at 2x its frame
interpolation can make the frame in between with `RX_VK_FSR_FG=1` (opt-in: the game draws its HUD into the same picture
and FSR 3.1 has no HUD-less colour to keep it still, so the HUD smears; by default the renderer's own makes it). Both are AMD's FidelityFX
SDK 1.1.4 shaders (`third_party/fidelityfx-sdk`, MIT), compiled into the renderer: no AMD runtime or DLL is needed, and
the row offers FSR 3.1 on any Vulkan 1.3 GPU with push descriptors, extended storage image formats and storage writes
without a format (`vk: fsr3: ... can run on this GPU` in the log). Its inputs are the scene's colour, its depth, motion
from the camera, and the same camera jitter DLSS uses (`RX_VK_FSR_JITTER=0` turns it off); things that move by
themselves can trail for now.

</details>

<details>
<summary>NVIDIA DLSS (optional, NVIDIA's SDK under NVIDIA's license)</summary>

A game built with NVIDIA's DLSS SDK offers **NVIDIA DLSS** and **NVIDIA DLAA** in the Graphics tab's **Upscaler** row on
NVIDIA RTX cards (`dlss=` in `hookshot_options.ini`, `RX_VK_DLSS=0/1/2` for one run): DLSS Super Resolution in place of
the game's own upscaler, with camera jitter (**NVIDIA Reflex** needs no SDK and is in
every build). NVIDIA's files are NVIDIA's, under its own license, the
[NVIDIA RTX SDKs license](https://github.com/NVIDIA/DLSS/blob/9981c6350dc58c0ce21f024fd65e31e851c31689/LICENSE.txt).
Hookshot never includes or redistributes them: each build downloads them for itself, and only after you accept that
license. Never share a game folder built with them, and do not post builds made with them.

- **Windows, the Hookshot Builder:** tick **NVIDIA DLSS (downloads NVIDIA's SDK under NVIDIA's license)** before you
  build. It is off by default and shows NVIDIA's license when you tick it. The build downloads the SDK into
  `%LOCALAPPDATA%\HookshotBuilder\ngx-sdk` and puts DLSS's runtime, `nvngx_dlss.dll`, in the game folder's `ngx` folder.
- **Windows, the command line:** `python -I scripts/ngx_sdk.py --platform windows <sdk folder>` asks you to accept
  NVIDIA's license (or pass `--accept-nvidia-license`) and fetches the headers, `nvsdk_ngx_s.lib` and `nvngx_dlss.dll`,
  each checked against its SHA-256. Then build with `HOOKSHOT_NGX_SDK=<sdk folder>`: `make_game.py` copies
  `nvngx_dlss.dll` into `<game folder>\ngx`. NGX is also pointed at `%LOCALAPPDATA%\Hookshot\ngx`, and at
  `RX_VK_DLSS_DIR` when it is set, and uses the newest `nvngx_dlss.dll` it finds across them (to try a given one, make
  sure no other folder has a newer one). Never copy NGX's core, `_nvngx.dll`, beside the game: it comes with NVIDIA's
  driver.
- **Linux:** the same with `--platform linux` (or `scripts/linux/ngx-sdk.sh`): `libnvsdk_ngx.a` for the build and
  `libnvidia-ngx-dlss.so` for the game folder's `ngx` folder (also looked for in `$XDG_DATA_HOME/hookshot/ngx`). NGX's
  core comes with NVIDIA's Linux driver. NVIDIA's NGX on Linux loads the runtime only from a folder whose path is all
  ASCII: with the game in a folder named otherwise (`~/Games/Zelda-Café`), put `libnvidia-ngx-dlss.so.*` in
  `$XDG_DATA_HOME/hookshot/ngx` (`~/.local/share/hookshot/ngx`) or another ASCII folder named by `RX_VK_DLSS_DIR`.

The **DLSS model** row chooses DLSS's network, by NVIDIA's preset letter, for every mode: **Transformer (K)**, the
transformer model and the one tested most here (the default); **Transformer 2 (M)**, NVIDIA's second-generation
transformer as it picks it for Performance; **Transformer 2 (L)**, the same generation as tuned for Ultra Performance;
**NVIDIA default**, which lets DLSS's runtime pick for each mode, so it can change with a runtime update. The runtime
the SDK comes with (310.9.16) has all of them. A change applies at once, without a restart (`dlss_model=` in
`hookshot_options.ini`, 0 to 3 in that order). `RX_VK_DLSS_PRESET=<letter>` (or `0` for NVIDIA's default) chooses
the preset for one run and wins over the row; the log's `vk: NVIDIA DLSS: ... preset <letter>` line says which one was
asked for, and with `RX_VK_DLSS_LOG=1` NGX's own `Using App hint Preset <letter>` lines say which it took.

**8 GB cards:** DLAA draws the 3D at full size, and DLSS and DLAA add images of their own beside the game's. In busy
areas that can pass what the driver allows the game, and the game then stutters: Quality or Balanced is safer there.
The log's `vk: status:` line every 600 frames shows the video memory in use of the allowance, with DLSS's details
(its images' size, the jitter and the actor motion) appended while it draws, and a `vk: over the driver's
video-memory allowance` line says when the game passed it.

The game's log says whether DLSS started, and why not when it did not (`vk: NVIDIA DLSS:` lines in `hookshot_log.txt`).
NGX starts on demand: when the Insert menu first opens (to know whether the Upscaler can offer DLSS) or at the first
gameplay upscale with DLSS chosen, so on the title screen the log has no NGX lines yet.
With `RX_VK_DLSS_LOG=1` NGX's own lines go there too (`ngx:`). Some of them look like errors but are not:
`failed to load NGXCore: 126` (twice) is NVIDIA's library looking for `_nvngx.dll` and `nvngx.dll` beside the game, which
are not there on purpose, before it loads the driver's; `Feature ... failed to load from cache` is NGX finding no model
of its own downloads (`C:\ProgramData\NVIDIA\NGX\models`) before it uses the game folder's `nvngx_dlss.dll`.

</details>

<details>
<summary>AMD FSR 4 (optional, AMD's DLLs not included)</summary>

A game built with FSR 4 offers **AMD FSR 4** and **AMD FSR 4 Native AA** in the Graphics tab's **Upscaler** row: AMD's
machine-learned temporal upscaler in place of the game's own, on the same inputs as DLSS (the scene's colour and depth, the
camera's and the characters' motion, and the camera jitter). Native AA draws the 3D at full size and smooths its edges.
Unlike FSR 3.1 (above), it runs AMD's own DLLs, so it needs them beside the game. Choose it in the menu (`dlss=4` or `5`
in `hookshot_options.ini`, `RX_VK_FSR4=1` or `2` for one run, `RX_VK_FSR4=0` to leave it out).

- **Windows, the Hookshot Builder:** tick **AMD FSR 4** before you build. Nothing is downloaded.
- **The command line:** `make_game.py --fsr` (or `HOOKSHOT_FSR=1` for `nx2/build.py`). Rebuilding a folder built with
  it (`--update`) keeps it; `--no-fsr` takes it out.
- **AMD's files:** Hookshot includes only AMD's MIT-licensed API headers (`third_party/fidelityfx`). Put
  `amd_fidelityfx_loader_vk.dll` and `amd_fidelityfx_upscaler_vk.dll` from the
  [FidelityFX SDK](https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK) 2.4 release (`Kits/FidelityFX/signedbin`)
  beside the game's exe (`bin\hookshot.exe`) or in the game folder. (`RX_VK_FSR_DIR` names another folder, for testing:
  set it in the environment or a `HOS_ENV_FILE` file; `hookshot_env.txt` takes no paths.) Without them the Upscaler row
  says so and offers the rest. On Linux, a Vulkan FSR 4 library (`amd_fidelityfx_upscaler_vk.so`, such as fsr4-vk's)
  takes their place.

The log's `vk: AMD FSR 4:` lines say which of AMD's upscalers it found for the card and which it uses (the newest FSR 4;
never an older FSR in its place), and why not when it did not start. Tested on an RX 6700 XT (RDNA 2).

</details>

<details>
<summary>Switches for testing (hookshot_env.txt)</summary>

Switches to test (`RX_VK_NOOPT=1` and the others) go in `hookshot_env.txt` in the game folder, one `NAME=VALUE` a
line, on Windows and Linux. The running game reads it, not the builder. A test run can name another file with
`HOS_ENV_FILE=<path>`; the game then reads that one instead and leaves `hookshot_env.txt` alone.
`hookshot_env.txt` sets only the game's own switches (names that start with `RX_`, `HOS_`, `HOOKSHOT_`, `EDEN_`,
`NVN_`, `TOTK_` or `SDL_`, but not SDL's library names such as `SDL_VULKAN_LIBRARY`), and no value that is a path except
`RX_VK_DLSS_DIR`'s (a folder on this PC, not a network share), and no value at all for the switches that name a file
or folder (`HOS_AUDIO_DUMP`, `RX_VK_SHOTS` and the like) or press buttons on a timer (`HOS_INPUT_SCRIPT`,
`RX_VK_MENU_SCRIPT`); other lines are left out, and the log says so. Switches that need a path, or other variables, go
in a file named by `HOS_ENV_FILE`.

To enable the debug tools, turn **Debug tools** on in the menu's Debug tab (or add `HOS_OOT_CHEATS=1` to
`hookshot_env.txt` in the game folder). The tools then show below it on the same tab. The tab's Developer section,
always shown, has the Descriptor reuse and Sampler cache rows.

`RX_VK_UI_GAME_FONT=0` draws the menu with the included font (Libertinus) even when the game's files have the game's own
menu font. `RX_VK_UI_PROMPTS=pad` (or `keys`) shows the controller's (or the keyboard's) prompts whatever was used last,
for screenshots.

For a first run on a 4 GB card such as a GTX 1650, `RX_VK_LOW_SPEC=1` starts with the Minimum (4GB) preset, with
frame generation and upscaling off. It applies only when there is no `hookshot_options.ini` yet; after that, change
the settings in the in-game menu.

`RX_VK_MOVIE_UPSCALE=linear` replaces the movies' neural upscale with the plain linear one. The default, `auto`, keeps
the networks and falls back only when a movie frame takes the GPU more than 40 ms. That is on NVIDIA cards: on other
cards, or where the GPU cannot multiply the networks' matrices itself, the movies always get the linear upscale. It does
not change the gameplay upscaler, and movies can look softer. `RX_VK_NETWORK_KEEP=all` takes precedence and keeps the
movie networks.

`RX_VK_SKIP_CODE=<prefix,...>` leaves out the draws of every program with a stage whose native code key starts with one
of the prefixes (the keys the log prints after "its code:"). On a Steam Deck, `RX_VK_SKIP_CODE=2c56dc1006942f74`
avoids a GPU hang in Kokiri Forest and the Great Deku Tree: the GPU runs for seconds in the programs that share that
task shader (a culling pass) until the kernel resets it ([#817](https://github.com/NotRexed/Hookshot/issues/817)).
It is a workaround, not a fix: those are task + mesh programs, so the geometry they draw goes with them, and key models
are missing while it is set. Off unless set.

The switches for scripted test runs, screenshots, frame dumps and profiles are in the
[development guide](docs/development.md#switches-for-testing-and-debugging).

`RX_VK_WB_MAX_KB=<KB>` stops the write-back of written GPU bindings larger than that. OoT writes tens of MB of culling
lists and per-frame buffers through the GPU that the CPU never reads, and copying them back sat on every submit's
memory sync: in Hyrule Field on a 10 GB RTX 3080, about 66 MB and 4.4 ms a submit, holding the scene at 45-48 fps.
`RX_VK_WB_MAX_KB=1024` still copies the small results the CPU does read (the exposure meter and the like) and took the
same scene to 59-60 fps. `0` or unset copies every written binding, as before.

</details>

## How it works

1. `nx2/lift.py` translates the game's ARM64 code to C.
2. `nx2/build.py` compiles that C together with `host/`, which plays the part of the console's system.
3. `host/nvn_native.c` records the game's NVN2 graphics calls, and `gpu/vk/` replays them on Vulkan.
4. Switch 2 Ampere shaders are lowered to Maxwell (`lower_to_maxwell.h`) and translated to SPIR-V by Eden's shader
   recompiler.

More detail is in the [development guide](docs/development.md) and the [design notes](docs/design.md).

## Want to help?

Testing on other graphics cards and reporting the result already helps a lot, and so does playing further into the
game than anyone has yet.

Bigger ways to help:

- **Linux testing.** The Linux build (`host/posix`) has been tested on several distributions and cards: reports from
  others still help.
- **Fixes in your own fork.** Fork the project, fix what you find and send the change back. Keep game files, keys and
  anything generated from your game out of it.

[CONTRIBUTING.md](CONTRIBUTING.md) has the setup, the test commands, the code conventions and what a good pull request
looks like.

## Credits

Hookshot exists thanks to the work of many people:

- **NotRexed**: Hookshot, BlueShell (Mario Kart World), Skybound (Tears of the Kingdom) and the a64-kit tools.
- **[Eden](https://git.eden-emu.dev/eden-emu/eden)** and **Eglantine**: the shader recompiler and Switch 2 shader work.
- **suyu**: the graphics decoders and the AArch64 translator.
- **[seedds/nxnative](https://github.com/seedds/nxnative)**: reference for how task and mesh shaders work.
- **[EvilBoyce / evilmfkr](https://github.com/evilmfkr/Hookshot)** (EvilOOT): the GPU culling that brings back Kokiri's foliage
  (trees, ferns, grass, falling leaves, fireflies), the ambient light probes, the pond's water, the game's own fog, the freeze
  after Load (Horizon's mutex handoff) and the exposure flicker fix.
- **[zortos293/Lichii](https://github.com/zortos293/Lichii)**: reference for Ampere shader lowering, and its compare-exchange retry fix.
- **[mstorsjo/llvm-mingw](https://github.com/mstorsjo/llvm-mingw)**: the bundled Windows compiler (no Visual Studio needed).
- **NVIDIA DLSS**: builds made with NVIDIA's DLSS SDK (optional, downloaded by each build, never bundled) use NVIDIA DLSS
  Super Resolution, NVIDIA's technology. NVIDIA and DLSS are trademarks of NVIDIA Corporation.
- **AMD FSR 3.1 and FSR 4**: every build has AMD FidelityFX Super Resolution 3.1, built from AMD's MIT-licensed FidelityFX
  SDK shaders; builds made with FSR 4 (optional; AMD's DLLs are never bundled) use AMD FidelityFX Super Resolution 4
  through AMD's MIT-licensed FSR API headers. Both are AMD's technology. AMD, Radeon and FidelityFX are trademarks of Advanced Micro
  Devices, Inc.
- **[kinnay/zbic](https://github.com/kinnay/zbic)**, **Opus** and **SDL**: decompression, audio and controllers.
- **[sostenesfreitas/ocarina-recomp](https://github.com/sostenesfreitas/ocarina-recomp)**: this README's layout, and its notes
  confirmed the mesh stage's control section.
- **[MythosOfs/Orchid](https://github.com/MythosOfs/Orchid)**: the fog and exposure workaround for Ocarina of Time.
- **Mesa (NAK)**: the reference for Ampere's instruction encoding.
- Everyone who sent fixes: SkippySteve (Linux and the AppImage, and many more), monsterlag, klimovich008, hckrman101 (NVIDIA
  DLSS, DLAA and Reflex, the exposure flicker and fog fixes, build speed, CI), madebyjordan (AMD FSR 4.1), N3oTraX (FSR 4 on
  Linux), shayderrr, gab9281, Wpaif, nicholasgower, ZurielAtr, Joey-Magnus, Zorkats,
  d3zessete, chrispository, vzeol, leonidasmark, Segmentree, ShyVortex, hiKareeem and i900gaming, among others.

## License

Hookshot is free software under the [GNU General Public License, version 3 or later](LICENSE) (GPL-3.0-or-later).
It includes code from Eden, suyu and Orchid, which are under the GPL too. Third-party parts under other licenses that
work with the GPL (Sirit, the Vulkan Memory Allocator, SDL, Opus, Dear ImGui, zstd, the Libertinus fonts, zbic and the
a64-kit tools) keep their own notices in their folders.

Hookshot is an unofficial fan project, not affiliated with or endorsed by Nintendo. The Legend of Zelda and Ocarina of
Time are trademarks of Nintendo.
