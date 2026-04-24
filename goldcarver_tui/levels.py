"""Parse Lode Runner level packs from the vendored TotalRecall JS files.

Each pack file (e.g. `lodeRunner.v.classic.js`) is a JavaScript source
declaring `var classicData = [ "...", "...", ... ]` — one string literal
per level. Each string is `NO_OF_TILES_X * NO_OF_TILES_Y` (28 × 16 =
448) characters when concatenated, because the original source JSs use
JavaScript string concatenation to make each row of the map look like
a row in the source. We just strip the JS boilerplate and extract the
string contents.

We don't need a real JS parser — we regex for quoted string blocks in
a specific array identifier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .engine import Game

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "lode-runner-total-recall"

WIDTH = 28
HEIGHT = 16
EXPECTED_SIZE = WIDTH * HEIGHT


@dataclass(frozen=True)
class LevelData:
    raw: str           # 448-char flat string, W*H
    title: str = ""

    def to_text(self) -> str:
        """Slice the flat string into HEIGHT rows of WIDTH."""
        return "\n".join(
            self.raw[i * WIDTH:(i + 1) * WIDTH]
            for i in range(HEIGHT)
        )

    def load(self) -> Game:
        return Game.parse(self.to_text(), title=self.title)


@dataclass
class Pack:
    name: str
    display: str
    credit: str
    levels: list[LevelData]

    def __len__(self) -> int:
        return len(self.levels)

    def __getitem__(self, i: int) -> LevelData:
        return self.levels[i]


# ---- JS parser -----------------------------------------------------

# Concatenated string literals look like:
#     "row0row0row0..." +
#     "row1row1row1..." +
#     ...
#     "row15row15row15",
#
# We extract each quoted chunk for a given array variable name.

_VAR_START = re.compile(r"var\s+(\w+Data)\s*=\s*\[")
_STR = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _extract_levels_from_js(text: str) -> list[str]:
    """Return one concatenated W*H string per level in the JS file."""
    m = _VAR_START.search(text)
    if not m:
        return []
    # Walk from `[` forward, splitting into per-level buckets. Each
    # level ends at a `,` that is NOT inside a string. Simpler: find
    # all top-level string literals, grouping contiguous-with-`+`
    # literals into one level.
    start = m.end()
    # Trim to the matching `]`.
    depth = 1
    i = start
    end = len(text)
    while i < end:
        c = text[i]
        if c == '"':
            # Skip over string
            i += 1
            while i < end:
                if text[i] == '\\':
                    i += 2
                    continue
                if text[i] == '"':
                    i += 1
                    break
                i += 1
            continue
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1
    body = text[start:end]

    # Now split `body` into tokens: commas at depth 0 separate levels.
    levels: list[str] = []
    buf: list[str] = []

    def flush():
        if buf:
            full = "".join(buf)
            levels.append(full)
        buf.clear()

    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        if c == '"':
            # Consume string
            j = i + 1
            chunk: list[str] = []
            while j < n:
                if body[j] == '\\':
                    if j + 1 < n:
                        chunk.append(body[j + 1])
                    j += 2
                    continue
                if body[j] == '"':
                    break
                chunk.append(body[j])
                j += 1
            buf.append("".join(chunk))
            i = j + 1
            continue
        if c == ',':
            flush()
            i += 1
            continue
        # skip whitespace, `+`, comments
        if body[i:i + 2] == "//":
            nl = body.find("\n", i)
            if nl == -1:
                break
            i = nl + 1
            continue
        if body[i:i + 2] == "/*":
            close = body.find("*/", i + 2)
            if close == -1:
                break
            i = close + 2
            continue
        i += 1
    flush()
    return levels


# ---- specific pack loaders ----------------------------------------

_PACKS_META = [
    ("classic",      "Classic Lode Runner",       "lodeRunner.v.classic.js",
     "Broderbund 1983 (layouts) — via SimonHung/LodeRunner_TotalRecall"),
    ("championship", "Championship Lode Runner",  "lodeRunner.v.championship.js",
     "Broderbund 1984 (layouts) — via TotalRecall"),
    ("professional", "Professional Lode Runner",  "lodeRunner.v.professional.js",
     "Irem 1984 (layouts) — via TotalRecall"),
    ("revenge",      "Revenge of Lode Runner",    "lodeRunner.v.revenge.js",
     "Sierra 1995 (layouts) — via TotalRecall"),
]


def _build_pack(name: str, display: str, fname: str, credit: str) -> Pack | None:
    path = VENDOR / fname
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    raws = _extract_levels_from_js(text)
    levels: list[LevelData] = []
    for i, raw in enumerate(raws, start=1):
        # Sanity check — many packs have exact-size strings, but some
        # levels may be a few cells short due to source typos. Pad.
        if len(raw) < EXPECTED_SIZE:
            raw = raw.ljust(EXPECTED_SIZE, " ")
        elif len(raw) > EXPECTED_SIZE:
            # some championship levels ship slightly-long; truncate
            raw = raw[:EXPECTED_SIZE]
        levels.append(LevelData(raw=raw, title=f"{display} #{i}"))
    if not levels:
        return None
    return Pack(name=name, display=display, credit=credit, levels=levels)


# ---- handmade pack -------------------------------------------------
# Small, tractable, CC0 levels for quick testing + fallback if the
# vendor tree is missing.

_HANDMADE: list[tuple[str, str]] = [
    ("Handmade #1 — First Steps",
     "                            "
     "                            "
     "         $                  "
     "   H########################"
     "   H                        "
     "   H      $                 "
     "   H #######                "
     "   H                    $   "
     "   H                ########"
     "   H                        "
     "   H            $           "
     "   H #####################  "
     "   H                        "
     "   H  &                     "
     "   H                        "
     "############################"),
    ("Handmade #2 — Dig!",
     "                            "
     "                            "
     "  $         $          $    "
     "###H####################H###"
     "   H                    H   "
     "   H    & ###    ####   H   "
     "   H    ###     $       H   "
     "   H  ######    ####    H   "
     "   H     $              H   "
     "   H     H######        H   "
     "   H     H              H   "
     "   H     H   0          H   "
     "   H     H##########    H   "
     "   H     H              H   "
     "   H  $                 H   "
     "############################"),
    ("Handmade #3 — Rope",
     "                            "
     "                            "
     "  &                         "
     "  H------------      $      "
     "  H           H###########  "
     "  H     $     H             "
     "  H ##########H   --------  "
     "  H           H             "
     "  H   0       H    $        "
     "  H###########H #########   "
     "  H           H             "
     "  H    $      H             "
     "  H###########H             "
     "  H                         "
     "  H                         "
     "############################"),
]


def _build_handmade() -> Pack:
    levels = [LevelData(raw=raw, title=title) for title, raw in _HANDMADE]
    return Pack(
        name="handmade",
        display="Handmade",
        credit="goldcarver-tui authors — CC0",
        levels=levels,
    )


def _all_packs() -> list[Pack]:
    out: list[Pack] = [_build_handmade()]
    for name, display, fname, credit in _PACKS_META:
        try:
            p = _build_pack(name, display, fname, credit)
        except Exception as e:  # pragma: no cover
            import sys
            print(f"warning: pack {name} failed: {e}", file=sys.stderr)
            p = None
        if p is not None:
            out.append(p)
    return out


PACKS: list[Pack] = _all_packs()


def pack_by_name(name: str) -> Pack:
    for p in PACKS:
        if p.name == name:
            return p
    raise KeyError(f"no such pack: {name!r}. Have: {[p.name for p in PACKS]}")


def total_levels() -> int:
    return sum(len(p) for p in PACKS)
