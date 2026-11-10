# Window-thread pointer samples

The host publishes one `MkwVkPointer` sample: client position and client dimensions
in physical pixels, held buttons, pending presses, and wheel motion. The renderer
consumes it without querying the window system. This does not change API version 10.

On Windows the DPI-aware window thread samples the cursor in screen space and
converts it to the current client area. Move, resize, DPI, mouse and focus events
refresh the sample; the existing timer refreshes a stationary pointer too. Mouse
capture for camera motion remains separate from the free menu pointer. Focus loss,
minimization and camera capture discard pending menu input.

On SDL, window-unit dimensions, pixel dimensions and the floating-point cursor
position are queried on the main thread. Coordinates are scaled before rounding
down to pixels, preserving fractional motion and negative positions outside the
top/left edges. The renderer's drawable-size callback reads the same cached pixel
dimensions, including while the pointer is inactive. Resize publishes them before
notifying the renderer. Failed/zero-size samples do not accept input.

`host/display_pointer.h` holds the sample behind a short SRW lock (the POSIX shim
uses a pthread rwlock). Publication merges pending button edges and wheel motion;
reads consume edges and whole notches once, retaining fractional notches. Reset
discards input without erasing the drawable dimensions. No SDL/window call runs
with that lock held.

The Insert menu remains in swapchain coordinates, independently of the game's
presentation rectangle or letterbox bars. Its existing window-to-swapchain mapping
is unchanged. This patch does not add a game-coordinate inverse transform, change
menu layout scaling, or change relative mouse camera sensitivity.

## Checks

`python -I -B tests/test_display_pointer.py --cxx g++` compiles the actual sampling
and consumption functions from both hosts. Its SDL mocks reject foreign-thread
queries. It covers stationary-cursor resize, 96/120/144/192-DPI-equivalent pixel
ratios, fractional/negative/invalid coordinates, focus/capture/minimization,
one-shot presses, fractional wheel accumulation, and 100,000 concurrent samples.
`tests/test_menu_hit.py` checks the existing overlay mapping and hit regions.

Synthetic pixel ratios are not evidence of physical multi-monitor DPI migration.
Real-window and short game integration results must identify their actual build
and environment; no game data is required by the public tests.


Review follow-up: Windows clears the menu sample once on entering camera capture;
captured motion and periodic refreshes do not query the pointer or take the
publisher lock. Leave tracking is armed once until leave, cancelled on capture,
and retried after a failed registration.

SDL button-down uses the event x/y, scaled using the window/pixel geometry at the
event. The first pending press keeps that position and geometry until a take,
while the drawable-size callback continues to return the latest dimensions.
Subsequent coalesced button edges remain ORed; this one-position API associates
them with the first pending press. After consumption, the next read sees the
latest cursor sample. Loss of eligibility clears pending presses and wheel state.
The source-based tests exercise the actual move handler, capture transition and
SDL down handler, including a cursor move/resize before renderer consumption.


After the game-menu mouse support landed, Windows publishes a separate mailbox
for that consumer. Its game-thread read takes the coherent point, latched press
and fractional wheel without querying Windows or draining the Insert menu's
input. Insert retains wheel priority; the game menu receives it while Insert is
closed (including while the cursor is hidden), and the play-only wheel route is
unchanged. Menu transitions, capture and focus loss clear pending input.

Both Windows button handlers now publish the message's signed client coordinates,
so a later cursor poll or resize cannot move the pending click. The fixture runs
the actual game-menu consumer, both button helpers, menu transitions and wheel
message route, including cross-thread consumption and independent mailboxes.
