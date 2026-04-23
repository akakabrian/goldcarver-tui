# Lode Runner TUI — Design Decisions

## Engine: pure-Python clean-room reimplementation

The classic Broderbund Lode Runner (1983) mechanics are simple enough to
reimplement directly in Python — like sokoban-tui and crimson-fields-tui,
we do not ship a native engine. Rules are ~300 lines.

Reference vendored under `vendor/lode-runner-total-recall/` — Simon Hung's
HTML5 remake (`SimonHung/LodeRunner_TotalRecall`). We use it for:

- 150 classic level layouts (`lodeRunner.v.classic.js`)
- 150 professional levels (`lodeRunner.v.professional.js`)
- 51 championship levels (`lodeRunner.v.championship.js`)
- 17 revenge levels (`lodeRunner.v.revenge.js`)
- Rules reference only — the TotalRecall engine uses sub-cell pixel
  offsets (xOffset/yOffset) for smooth animation; we collapse to one
  cell per tick for TUI semantics.

## Tile grid: 28×16 classic

From `lodeRunner.def.js`: `NO_OF_TILES_X=28`, `NO_OF_TILES_Y=16`.

Tile glyphs (source map):

| src | tile        | TUI glyph | notes                              |
|-----|-------------|-----------|------------------------------------|
| ` ` | EMPTY       | ` `       | walk through, fall through         |
| `#` | BRICK       | `▓`       | solid, diggable                    |
| `@` | SOLID       | `█`       | solid, NOT diggable (concrete)     |
| `H` | LADDER      | `╫`       | climbable both ways                |
| `-` | ROPE        | `─`       | hand-over-hand traverse, hang      |
| `X` | TRAP        | `░`       | looks like brick, fall through     |
| `S` | HIDE LADDER | ` `       | invisible until all gold collected |
| `$` | GOLD        | `¤`       | collect all to reveal S ladders    |
| `0` | GUARD       | `Ж`       | enemy AI                           |
| `&` | RUNNER      | `☺`       | player spawn                       |

## Movement + tick semantics (classic, discrete)

One action per tick. Player and guards move one cell per tick.
Gravity applies *after* player action resolution each tick, unless
standing on: brick, solid, ladder, or rope.

Rules (clean-room, matched against TotalRecall runner.js logic):

- **Walk L/R**: target cell must not be brick/solid/trap.
- **Up**: only on ladder, or moving up from a ladder cell.
- **Down**: onto ladder, rope, or empty (begin fall).
- **Rope**: you hang below it; can walk L/R along it; drop with `down`.
- **Gravity**: if the cell below is empty/rope (and not "on a rope"
  itself) the actor falls one cell per tick. On rope → stays.
- **Dig left / dig right**: replace the cell one row below and one
  column L/R with HOLE, if it is a plain brick. Hole refills after N
  ticks (default 40). Guard in hole at refill time dies; respawns.
- **Guard AI**: one-cell-per-tick pathfinding toward runner. Guards
  follow the same movement rules as the runner but cannot dig.
- **Gold collection**: runner steps onto gold cell → gold removed,
  score++. Guards can also "carry" gold (drop on empty climb).
- **Exit**: when all gold is collected, HLADR_T cells become visible
  ladders reaching to the top row. Runner reaches top row → level won.

## Level format (internal)

28×16 ASCII rows using the mapping above. Stored as a list of strings
(one per row), 28 chars wide, 16 rows deep. Parser returns a
`Level` dataclass with the grid and the player/guard spawn points.

Packs are `.lev` files: one level per "block" separated by a blank or
`---` line, preceded by an optional `; <title>` line.

## Controls

| Key                | Action                   |
|--------------------|--------------------------|
| left / `h` / `a`   | move left                |
| right / `l` / `d`  | move right               |
| up / `k` / `w`     | climb up / rope up (no)  |
| down / `j` / `s`   | climb down / drop        |
| `z` or `,`         | dig left                 |
| `x` or `.`         | dig right                |
| `u`                | undo last action         |
| `r`                | reset level              |
| `n` / `p`          | next / prev level        |
| `L`                | level-select screen      |
| space              | pause/step               |
| `?`                | help                     |
| `q`                | quit                     |

No mouse in v0; keyboard primary.

## Packs bundled

| name         | count | source                                    | license |
|--------------|------:|-------------------------------------------|---------|
| classic      |   150 | Broderbund 1983 layouts via TotalRecall   | layouts are decades-old public records; TotalRecall ships them freely |
| championship |    51 | Championship Lode Runner 1984             | ditto   |
| professional |   150 | Professional Lode Runner (GB64)           | ditto   |
| revenge      |    17 | Revenge of Lode Runner (Apple II)         | ditto   |
| handmade     |    1+ | built-ins for testing                     | CC0     |

The TotalRecall project is open source under a permissive readme;
we redistribute only the ASCII level strings (not sprites/sounds)
and credit Simon Hung. If a takedown arrives we fall back to the
"handmade" pack.

## Gate order (tui-game-build skill, 7 stages)

1. Research — DONE.
2. Engine — pure-Python `engine.py`. Gate: REPL tick + move + dig.
3. TUI scaffold — 4-panel Textual app. Gate: launch, run, dig.
4. QA harness — 20+ scenarios before polish.
5. Perf — baseline; only optimize if needed.
6. Robustness — out-of-bounds, malformed level, unknown glyph.
7. Polish (phased):
   - A: UI beauty (bg colors, pattern on brick walls)
   - B: Submenus (level select, help, won)
   - C: (optional) agent REST API
   - D: (optional) sound
   - E: Mouse

## Intentionally-not-in-MVP

- Pixel-accurate sub-cell animation (sprite engine semantics).
  TotalRecall's xOffset/yOffset logic is animation polish only; we
  use discrete integer tiles one-cell-per-tick. Play feel is closer
  to NetHack+Boulder Dash than to arcade LR — that's the honest
  TUI interpretation.
- Score / time / "lives" scoring system. We track gold-collected
  and won/lost; scoring can come in Phase E polish.
- Multiple runners (co-op). Single runner only.

## Layout

```
loderunner-tui/
├── loderunner.py              # entry: argparse → run(...)
├── pyproject.toml
├── Makefile
├── DECISIONS.md               # this file
├── vendor/
│   └── lode-runner-total-recall/  # Simon Hung's HTML5 remake (reference)
├── loderunner_tui/
│   ├── __init__.py
│   ├── engine.py              # Game, tick, move, dig, gravity, guard AI
│   ├── levels.py              # Pack loader; parses the vendored .js files
│   ├── tiles.py               # glyph/style tables
│   ├── app.py                 # LodeRunnerApp, BoardView, panels
│   ├── screens.py             # Help, LevelSelect, Won, Lost
│   └── tui.tcss
└── tests/
    ├── qa.py
    ├── playtest.py
    └── perf.py
```
