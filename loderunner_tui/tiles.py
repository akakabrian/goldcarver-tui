"""Glyph + style tables for rendering the Lode Runner board."""

from __future__ import annotations

from rich.style import Style

from . import engine as E

# --- glyphs ---------------------------------------------------------
# Brick uses a 2-glyph pattern keyed on (x+y)&1 so a long wall reads as
# masonry rather than a flat block (palette rule #2 from tui-game-build).
GLYPH_BRICK_A = "▓"
GLYPH_BRICK_B = "▒"
GLYPH = {
    E.EMPTY:   " ",
    E.BRICK:   GLYPH_BRICK_A,   # default — renderer alternates via tile_glyph_at
    E.SOLID:   "█",
    E.LADDER:  "╫",
    E.ROPE:    "─",
    E.TRAP:    "▓",             # looks like brick (can't tell until you fall)
    E.HOLE:    " ",              # empty look (dug out)
    E.HLADDER: " ",             # invisible until all gold collected
}

GLYPH_GOLD = "¤"
GLYPH_RUNNER = "☺"
GLYPH_GUARD = "Ж"
GLYPH_GUARD_GOLD = "★"  # guard carrying gold

# --- backgrounds ----------------------------------------------------
BG_DEFAULT = "rgb(8,8,12)"
BG_BRICK = "rgb(28,18,14)"
BG_SOLID = "rgb(40,30,24)"
BG_LADDER = "rgb(10,14,20)"
BG_ROPE = "rgb(12,12,16)"

# --- styles ---------------------------------------------------------
S_EMPTY = Style.parse(f"on {BG_DEFAULT}")
S_BRICK = Style.parse(f"rgb(200,120,60) on {BG_BRICK}")
S_BRICK_ALT = Style.parse(f"rgb(180,100,50) on {BG_BRICK}")
S_SOLID = Style.parse(f"rgb(150,140,130) on {BG_SOLID}")
S_LADDER = Style.parse(f"bold rgb(240,220,90) on {BG_LADDER}")
S_ROPE = Style.parse(f"rgb(220,200,140) on {BG_ROPE}")
S_TRAP = Style.parse(f"rgb(160,90,50) on {BG_BRICK}")       # looks like brick
S_HOLE = Style.parse(f"rgb(40,40,48) on {BG_DEFAULT}")

S_GOLD = Style.parse(f"bold rgb(255,220,60) on {BG_DEFAULT}")
S_RUNNER = Style.parse(f"bold rgb(90,220,255) on {BG_DEFAULT}")
S_GUARD = Style.parse(f"bold rgb(255,90,90) on {BG_DEFAULT}")
S_GUARD_GOLD = Style.parse(f"bold rgb(255,180,60) on {BG_DEFAULT}")


def tile_style(tile: str, x: int, y: int) -> Style:
    """Return the rich Style for a terrain tile.

    `x, y` are used to alternate brick shade so a big wall doesn't read
    as one flat block (palette rule from tui-game-build)."""
    if tile == E.BRICK:
        return S_BRICK if (x + y) & 1 else S_BRICK_ALT
    if tile == E.SOLID:
        return S_SOLID
    if tile == E.LADDER:
        return S_LADDER
    if tile == E.ROPE:
        return S_ROPE
    if tile == E.TRAP:
        return S_TRAP
    if tile == E.HOLE:
        return S_HOLE
    return S_EMPTY


def tile_glyph(tile: str) -> str:
    return GLYPH.get(tile, " ")


def tile_glyph_at(tile: str, x: int, y: int) -> str:
    """Position-aware glyph — brick cycles between two patterns."""
    if tile == E.BRICK:
        return GLYPH_BRICK_A if (x + y) & 1 else GLYPH_BRICK_B
    return GLYPH.get(tile, " ")
