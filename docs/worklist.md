# Work list

The prioritized list of open work, scored as [docs/workflow.md](workflow.md) describes: **score = severity weight x
reach x confidence** (S0 8, S1 5, S2 3, S3 1; reach 0-1 from `scripts/hardware_report.py` and the Steam survey;
confidence 1.0 reproduced with a log, 0.7 two or more reporters with logs, 0.4 one report or no log). Work from the
top of **Open**. A GitHub issue stays the full record; this list is the order.

How to use it:

- **Pick:** take the highest-scored row with no owner that you can reproduce on your hardware, claim it in Discord
  #dev-work, and put your name in *Owner* in the same PR that starts the work (or a one-line PR).
- **Add:** a new report becomes a row in **Open** with its three parts filled in, so the score can be checked. Link the
  issue or the Discord thread. One row per problem: if a row already covers it, add the link to that row and raise its
  confidence instead of adding a second row.
- **Move:** when a PR merges, move the row to **Fixed, waiting for a release** with the PR; when a release ships it,
  delete the row (the release notes are the record). A row nobody can reproduce for two weeks, with logs asked for,
  goes to **Parked**.
- Keep each table sorted by score, highest first. Re-score when new logs or hardware numbers arrive.

Agents may add and re-score rows; a person reviews the change like any other PR.

## Open

| Score | Problem | S | Reach | Conf. | Owner | Links |
|---:|---|---|---:|---:|---|---|
| 4.6 | Windows updater checks asset length but not GitHub's SHA256 digest before setup launch or ZIP extraction; verify both download routes (signing remains separate) | S0 | 0.57 | 1.0 | monsterlag | #1679; #1792; actual updater accepts same-length altered setup/ZIP in authored HTTP tests; fixed 20/20 cases pass |
| 2.1 | Ground and outdoor textures garble after a while of play and come back after a restart or going to the title; the logs differ on what the texture cache does: aris (9070 XT 16 GB) runs into the fixed 6 GB texture budget (6144 MB even on 16 GB cards, `vk_texture.cpp` texture_frame), peaking at 5941 MB, with 191 eviction passes of 20+ textures from present 1920 on (18,522 retired); steuer (9070 XT) stays at 3.3 GB, far under it, yet retires 28,003, the render-target sweeps; Flavor (RX 6700 XT) at 4.8 GB, with VRAM at 9.6 of the 10.0 GB the driver allows. `RX_VK_ASTC_RGBA8=1` took effect for aris (texture arrays 4x larger) and did not help. Reports: 9070 XT x2 (logs, v2.0.13), RX 6700 XT (v2.0.14 log; "entering new areas sometimes textures never load until a restart"), RTX 4080 (no log), RTX 5060 Ti (v2.0.5 log). Next: a long walk with `RX_VK_LOG_REMADE=1` (logs textures made again and sampled EMPTY), at the default budget and at a small `RX_VK_VRAM_MB`; for users at the budget, try a bigger `RX_VK_VRAM_MB` | S2 | 1.0 | 0.7 | Joey-Magnus | #993; #bug-reporting "texture glitch on 9070 XT", "Ground design is not loading properly", "Dodongo Cavern, floor texture glitch", "General texture loading hooking issues"; merged rows: "Ground looks smeared, without detail" (Kokiri Forest / Lost Woods, Dodongo's Cave, Hyrule Field) and "AMD RX 9070 XT: texture glitch that appears after some play" (#57, #1006) |
| 2.1 | Camera turns in Kokiri Forest stutter: 46 fps minimum, dips to 38 (14700KF); goal is a 60 fps minimum | S2 | 1.0 | 0.7 | Joey-Magnus | Reddit report; #1762 (+13.5% in the village view; 57 of 60); next: the once-a-frame CPU wait for the GPU in take_capture (exposure page): +20% without it, design asked of hckrman101 in #dev-work |
| 2.0 | Antivirus flags HookshotBuilder.exe (Defender `Wacatac.H!ml` / `Wacatac.B!ml`, Chrome on v2.0.12): new unsigned exe, no reputation. Waiting on the SignPath open-source signing application; then sign in `windows-builder.yml` and publish the signed files | S1 | 0.57 | 0.7 | NotRexed (SignPath) | #1003, #525, #1620; checksums: #1307 |
| 1.2 | Link keeps playing a jump animation in dialogue after the Gohma fight (gameplay fine): cutscenes and dialogue run at the frame rate above a 60 cap since #1612 (v2.0.13); work-around: cap at 60 | S2 | 1.0 | 0.4 | | #1742 (#1726 closed into it); #bug-reporting "My link is jumping forever" |
| 1.1 | Setup stops when Windows' tar.exe cannot be found (launch error 2); explain the missing tool and manual Windows repair steps. Reach uses Windows' upper bound; the missing-tool subset is unknown | S1 | 0.57 | 0.4 | monsterlag | #1896; #1922; diagnostic alternative tested: Windows 18 cases, Linux 16; affected-machine repair remains unverified |
| 1.0 | Source checks fail after stream/descriptor admission merges: missing production stream_insert dependency and descriptor-pool fixture environment. CI-first; reproduced on main | S3 | 1.0 | 1.0 | Arkex-ai | [#1813](https://github.com/NotRexed/Hookshot/issues/1813), [claim](https://discord.com/channels/1568810484818378804/1569019786766188665/1569763504758464609) |
| 0.6 | Windows Builder's Show details link opens the log when blank footer space is clicked; limit its hit area to its content | S3 | 0.57 | 1.0 | monsterlag | #1842; actual offscreen WPF footer reproduces two blank-space hit failures and four label/Cancel controls |
| 0.6 | Zora's Domain textures missing in the adult timeline (points to VRAM pressure, not the dump) | S2 | 0.3 | 0.7 | | #bug-reporting "Zora Domain textures missing?" |
| 0.5 | Sacred Forest Meadow fairy fountain grotto: floor and walls invisible (RTX 2070 Super) | S2 | 0.4 | 0.4 | | #bug-reporting thread |
| 0.4 | Voices in the wrong language | S3 | 1.0 | 0.4 | | #1460 (needs a save past Gohma) |
| 0.39 | RTX 30: crash a few frames into gameplay after the intro (null write in game code on OptimizeChangeBanc, after a fragment program reads a storage buffer at an unmapped address 0x4180000000000200); since v2.0.12, still on v2.0.14; not on RTX 40 | S0 | 0.07 | 0.7 | | #1697 (logs v2.0.13 and v2.0.14); #dev-work findings |
| 0.29 | Amd RX 580 (Polaris, no mesh shaders): hair renders white and bright, and the game crashes when Link moves; a second RX 580 8 GB user reports the same | S1 | 0.145 | 0.4 | | #bug-reporting "Amd rx 580 crashes" (no log yet) |
| 0.22 | RTX 3070 with Frame generation on: uncaught C++ exception in hookshot_vk.dll on the first FSR 3 frame-generation inputs as gameplay starts (v2.0.13) | S0 | 0.07 | 0.4 | | #1786 (closed as a duplicate of #1697, but a different crash) |
| 0.11 | Intel GPU: black screen after loading a save (or on the Deku Tree), sound only, very low fps; three reports, no logs yet; tracked in the GitHub issue linked in #bug-reporting replies (#999) | S0 | 0.035 | 0.4 | | #bug-reporting "Intel G3E. Title and intro loads...", "intel arc b580 problems", "game gets stuck on a black screen when loading a save (intel gpu... gulp...)" |
| 0.11 | Crash at the door after the owl intro (Navi wakes Link, 2.0.13): access violation in `igvk64.dll` at start-up; GPU: Intel UHD Graphics (i3-1115G4, 128 MB shared, no mesh shaders: the best-effort fallback, #1001); reach is Intel's 3.5% | S0 | 0.035 | 0.4 | | #bug-reporting "2.0.13 Crash after you see the owl during intro cutscene" (5 logs) |


## Fixed, waiting for a release

| Problem | Fixed by | Notes |
|---|---|---|
| Every OoT shader program now translates (10 did not: TLD.MS, LDG/STG ordering, ISBERD.O, an immediate read as R254 + compute local memory, R2UR, a loop ending at its self-branch) | #1769, #1778, #1789, #1800, #1806, #1810 | in `main`, not in v2.0.13 |
| 1D surface loads (SULD.1D) stop 16-17 compute programs from translating; fits the green glow on a Legion Go 2 (890M) | #1447 | in `main`, not in v2.0.13 (log: #bug-reporting "Bugs 2.0.13 Dodaza") |
| Integer min/max with a wide immediate (IMNMX) does not translate | #1451 | in `main`, not in v2.0.13 (log: #bug-reporting "Bugs 2.0.13 Dodaza") |
| Insert menu purple with HDR10 on (v2.0.13 GDI overlay drawn into the HDR swapchain unconverted) | `main`'s ImGui overlay (`hdr10()`) | needs the release branch merged back into `main` |

## Parked

| Problem | Why parked | Links |
|---|---|---|
| | | |
