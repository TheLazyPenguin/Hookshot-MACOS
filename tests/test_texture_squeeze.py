"""The 97% driver's-limit squeeze waits while VMA's blocks hold room.

At the driver's limit, texture_frame set the texture budget below what the textures held every 10 frames. Evicting frees
space inside VMA's blocks, which the driver still counts, so the count stayed at the limit and the budget shrank again: a
ratchet. On a 4 GB RX 5500M a paused game (its scene draws nothing) lost 1700 MB of textures in seconds, made them again on
unpausing (a long wait), and the HUD's GPU-drawn hearts came back as black glyphs until an area change. The rule now waits
while the blocks hold an eighth of the allowance free; RX_VK_SQUEEZE_ALWAYS=1 squeezes as before.

python -I -B tests/test_texture_squeeze.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VK = ROOT / "gpu" / "vk"


def main():
    tex = (VK / "vk_texture.cpp").read_text(encoding="utf-8")
    if "const bool room_in_blocks" not in tex:
        raise SystemExit("the 97% squeeze runs whatever room VMA's blocks hold (a ratchet that drains a paused game's textures)")
    squeeze = tex[tex.index("const bool room_in_blocks"):]
    squeeze = squeeze[:squeeze.index("budget = std::min")]
    if "block_free >= allowed / 8" not in squeeze or "&& !room_in_blocks)" not in squeeze:
        raise SystemExit("the 97% squeeze runs whatever room VMA's blocks hold (a ratchet that drains a paused game's textures)")
    if 'getenv("RX_VK_SQUEEZE_ALWAYS")' not in tex:
        raise SystemExit("RX_VK_SQUEEZE_ALWAYS=1 does not bring the old squeeze back")
    if "room in the blocks: not squeezed" not in tex:
        raise SystemExit("the VRAM log line does not say when the squeeze waited")
    print("the driver's-limit squeeze waits while VMA's blocks hold room: ok")


if __name__ == "__main__":
    main()
