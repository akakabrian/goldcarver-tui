"""Pure-Python Lode Runner engine (clean-room; TotalRecall runner.js for ref).

Grid is `grid[y][x]` — `y` is the ROW going DOWN, `x` is the column.
Tiles are single ASCII chars from the level format:

    ' '  EMPTY      walk / fall through
    '#'  BRICK      solid; diggable; refills after N ticks
    '@'  SOLID      solid; NOT diggable (concrete)
    'H'  LADDER     climb up/down; counts as floor
    '-'  ROPE       hand-over-hand traverse; hang below
    'X'  TRAP       looks like brick but falls through (a.k.a. false brick)
    'S'  HLADDER    hidden ladder; appears only when all gold gathered
    '$'  GOLD       pickup (tile itself stays EMPTY after pickup)
    '0'  GUARD      spawn marker (tile becomes EMPTY; guard added)
    '&'  RUNNER     spawn marker (tile becomes EMPTY; runner placed)

Semantics (classic discrete, one cell per tick):
  * Player does ONE action per tick: left / right / up / down / dig_L /
    dig_R / stop.
  * After the player action we resolve GRAVITY for the player, then we
    tick every guard (AI move + gravity), then we advance dig-hole
    timers. A hole refills at the end of its timer; if a guard sits in
    it, the guard "dies" and respawns at a top-row empty cell, dropping
    any carried gold at the death spot.
  * Gold is in `gold_positions: set[(x,y)]`. When the runner steps onto
    a gold cell, the position is removed from the set. When all gold is
    collected, hidden ladders (`hidden_ladders: set[(x,y)]`) become real
    ladders.
  * Win: all gold collected AND runner on top row (y == 0).
  * Lose: runner is crushed by a refilling hole (currently standing in
    a filling cell) or falls into a trap cell with solid below and a
    guard above that digs (rare) — simplest: runner dies if inside a
    hole when it refills.

This is INTEGER-GRID semantics. The classic game has sub-cell pixel
offsets for smooth animation; we collapse those to whole-cell steps so
the game plays naturally as a turn-based TUI.
"""

from __future__ import annotations

import copy
from collections import deque
from dataclasses import dataclass, field

# --- tile constants --------------------------------------------------

EMPTY = " "
BRICK = "#"
SOLID = "@"
LADDER = "H"
ROPE = "-"
TRAP = "X"
HLADDER = "S"  # hidden ladder — renders empty until all gold taken
GOLD = "$"
GUARD_SPAWN = "0"
RUNNER_SPAWN = "&"

# Ephemeral hole tile — a dug brick mid-refill. Not part of the source
# map; only appears in the live grid.
HOLE = "."

SOLID_SET = frozenset({BRICK, SOLID, TRAP})  # blocks horizontal move
# what counts as "standing on" (prevents fall):
STANDABLE_BELOW = frozenset({BRICK, SOLID, LADDER, TRAP})
# climbable: you can move through these vertically or hold position
CLIMBABLE = frozenset({LADDER, ROPE})

# Default number of ticks a hole stays open before refilling.
DEFAULT_HOLE_TICKS = 40

# Actions
ACT_NONE = 0
ACT_LEFT = 1
ACT_RIGHT = 2
ACT_UP = 3
ACT_DOWN = 4
ACT_DIG_L = 5
ACT_DIG_R = 6

ACTIONS = {ACT_NONE, ACT_LEFT, ACT_RIGHT, ACT_UP, ACT_DOWN,
           ACT_DIG_L, ACT_DIG_R}


@dataclass
class Guard:
    x: int
    y: int
    carrying_gold: bool = False
    # Ticks until auto-climb-out when trapped in a hole.
    in_hole: int = 0


@dataclass
class Hole:
    """A dug brick. When `ticks` reaches 0 it refills."""
    x: int
    y: int
    ticks: int


@dataclass
class TickResult:
    """Outcome of one tick."""
    moved: bool = False
    gold_collected: int = 0
    won: bool = False
    dead: bool = False
    reason: str = ""


@dataclass
class Game:
    """A playable Lode Runner position.

    `grid[y][x]` is the TERRAIN layer only (including HLADDER which is
    hidden until all gold is gone, and HOLE while a hole is open).
    Runner position, guards, gold, and holes are tracked separately.
    """
    grid: list[list[str]]
    width: int
    height: int
    runner: tuple[int, int]         # (x, y)
    guards: list[Guard]
    gold_positions: set[tuple[int, int]]
    hidden_ladders: set[tuple[int, int]]
    total_gold: int
    holes: list[Hole] = field(default_factory=list)
    hole_ticks: int = DEFAULT_HOLE_TICKS
    # History for reset.
    _initial: dict | None = None
    # For undo — one entry per tick (bounded so memory is predictable).
    _undo_stack: list[dict] = field(default_factory=list)
    max_undo: int = 500
    title: str = ""
    # Status
    won: bool = False
    dead: bool = False
    tick_count: int = 0

    # ---- construction ------------------------------------------------

    @classmethod
    def parse(cls, text: str, title: str = "",
              hole_ticks: int = DEFAULT_HOLE_TICKS) -> "Game":
        rows = [r.rstrip("\n\r") for r in text.splitlines()]
        # Keep all rows — a valid level may have top rows that are all
        # empty tiles. We only reject a COMPLETELY empty string.
        if not rows:
            raise ValueError("empty level")
        width = max(len(r) for r in rows)
        # Pad to a rectangle with EMPTY.
        rows = [r.ljust(width, " ") for r in rows]
        height = len(rows)

        grid: list[list[str]] = []
        runner: tuple[int, int] | None = None
        guards: list[Guard] = []
        gold: set[tuple[int, int]] = set()
        hidden: set[tuple[int, int]] = set()

        for y, row in enumerate(rows):
            new_row: list[str] = []
            for x, ch in enumerate(row):
                if ch == GOLD:
                    gold.add((x, y))
                    new_row.append(EMPTY)
                elif ch == HLADDER:
                    hidden.add((x, y))
                    new_row.append(EMPTY)
                elif ch == GUARD_SPAWN:
                    guards.append(Guard(x=x, y=y))
                    new_row.append(EMPTY)
                elif ch == RUNNER_SPAWN:
                    runner = (x, y)
                    new_row.append(EMPTY)
                elif ch in (EMPTY, BRICK, SOLID, LADDER, ROPE, TRAP):
                    new_row.append(ch)
                else:
                    # Unknown glyph: treat as empty, don't crash.
                    new_row.append(EMPTY)
            grid.append(new_row)

        if runner is None:
            raise ValueError(f"level has no runner (& character): {title!r}")

        g = cls(
            grid=grid, width=width, height=height,
            runner=runner, guards=guards,
            gold_positions=gold, hidden_ladders=hidden,
            total_gold=len(gold), title=title, hole_ticks=hole_ticks,
        )
        g._snapshot_initial()
        return g

    def _snapshot_initial(self) -> None:
        self._initial = self._state()

    def _state(self) -> dict:
        return {
            "grid": [row[:] for row in self.grid],
            "runner": self.runner,
            "guards": [Guard(g.x, g.y, g.carrying_gold, g.in_hole)
                       for g in self.guards],
            "gold_positions": set(self.gold_positions),
            "hidden_ladders": set(self.hidden_ladders),
            "holes": [Hole(h.x, h.y, h.ticks) for h in self.holes],
            "won": self.won, "dead": self.dead,
            "tick_count": self.tick_count,
        }

    def _restore(self, snap: dict) -> None:
        self.grid = [row[:] for row in snap["grid"]]
        self.runner = snap["runner"]
        self.guards = [Guard(g.x, g.y, g.carrying_gold, g.in_hole)
                       for g in snap["guards"]]
        self.gold_positions = set(snap["gold_positions"])
        self.hidden_ladders = set(snap["hidden_ladders"])
        self.holes = [Hole(h.x, h.y, h.ticks) for h in snap["holes"]]
        self.won = snap["won"]
        self.dead = snap["dead"]
        self.tick_count = snap["tick_count"]

    def reset(self) -> None:
        if self._initial is not None:
            self._restore(self._initial)
            self._undo_stack.clear()

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._restore(self._undo_stack.pop())
        return True

    # ---- queries -----------------------------------------------------

    def cell(self, x: int, y: int) -> str:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[y][x]
        # Sides are walls; the top and bottom are floor-less/implicit-floor.
        return SOLID  # out-of-bounds behaves like solid

    def visible_tile(self, x: int, y: int) -> str:
        """The tile as the player would see it — HLADDER stays hidden
        until all gold is collected, then renders as a LADDER."""
        if (x, y) in self.hidden_ladders:
            return LADDER if not self.gold_positions else EMPTY
        return self.cell(x, y)

    def effective_tile(self, x: int, y: int) -> str:
        """The tile as movement rules see it — HLADDER is a ladder when
        exposed (all gold collected). While gold remains it's EMPTY
        and cannot be climbed."""
        if (x, y) in self.hidden_ladders:
            return LADDER if not self.gold_positions else EMPTY
        return self.cell(x, y)

    def gold_left(self) -> int:
        return len(self.gold_positions)

    def guard_at(self, x: int, y: int) -> Guard | None:
        for g in self.guards:
            if g.x == x and g.y == y:
                return g
        return None

    def is_standable(self, x: int, y: int) -> bool:
        """True if an actor at (x, y) has support (doesn't fall)."""
        if x < 0 or x >= self.width:
            return True
        if y >= self.height - 1:
            return True  # floor-of-level as implicit support
        here = self.effective_tile(x, y)
        if here in CLIMBABLE:
            return True  # on ladder or gripping rope
        below = self.effective_tile(x, y + 1)
        if below in STANDABLE_BELOW:
            return True
        # Standing ON a guard's head doesn't count as support — guards
        # aren't stable platforms in the classic game.
        return False

    # ---- tick --------------------------------------------------------

    def tick(self, action: int = ACT_NONE) -> TickResult:
        """Advance one tick with the given runner action."""
        if self.won or self.dead:
            return TickResult(reason="game_over")
        if action not in ACTIONS:
            raise ValueError(f"bad action: {action!r}")

        # Push undo snapshot (bounded).
        snap = self._state()
        self._undo_stack.append(snap)
        if len(self._undo_stack) > self.max_undo:
            self._undo_stack.pop(0)

        res = TickResult()

        # --- 1. Runner action ---------------------------------------
        if action == ACT_DIG_L:
            if self._dig(-1):
                res.moved = True
            # digging is an action; runner doesn't move this tick
        elif action == ACT_DIG_R:
            if self._dig(1):
                res.moved = True
        else:
            if self._runner_move(action):
                res.moved = True

        # --- 2. Runner gravity --------------------------------------
        rx, ry = self.runner
        if not self.is_standable(rx, ry):
            # Fall one cell if below is not solid.
            if ry + 1 < self.height:
                below = self.effective_tile(rx, ry + 1)
                if below not in SOLID_SET:
                    self.runner = (rx, ry + 1)
                    res.moved = True

        # --- 3. Gold pickup (for runner) ----------------------------
        if self.runner in self.gold_positions:
            self.gold_positions.discard(self.runner)
            res.gold_collected += 1

        # --- 4. Guard ticks -----------------------------------------
        self._tick_guards()

        # --- 5. Hole lifecycle --------------------------------------
        new_holes: list[Hole] = []
        for h in self.holes:
            h.ticks -= 1
            if h.ticks <= 0:
                # refill: restore to BRICK. If runner is in the cell,
                # dead. If guard is in the cell, the guard dies, respawns
                # at top, and drops any carried gold at the death spot.
                if self.runner == (h.x, h.y):
                    self.dead = True
                    res.dead = True
                    res.reason = "crushed"
                dead_g: Guard | None = None
                for g in self.guards:
                    if g.x == h.x and g.y == h.y:
                        dead_g = g
                        break
                if dead_g is not None:
                    # drop gold
                    if dead_g.carrying_gold:
                        self.gold_positions.add((dead_g.x, dead_g.y))
                        dead_g.carrying_gold = False
                    # respawn at a top-row empty cell (search for one)
                    spawn = self._find_guard_respawn()
                    if spawn is None:
                        # remove guard entirely if nowhere to go
                        self.guards.remove(dead_g)
                    else:
                        dead_g.x, dead_g.y = spawn
                        dead_g.in_hole = 0
                self.grid[h.y][h.x] = BRICK
            else:
                new_holes.append(h)
        self.holes = new_holes

        # --- 6. Win check -------------------------------------------
        rx, ry = self.runner
        if not self.gold_positions and ry == 0:
            self.won = True
            res.won = True

        # --- 7. Guard-catches-runner --------------------------------
        if not self.dead:
            for g in self.guards:
                if g.x == self.runner[0] and g.y == self.runner[1] \
                        and g.in_hole == 0:
                    self.dead = True
                    res.dead = True
                    res.reason = "caught"
                    break

        self.tick_count += 1
        return res

    # ---- runner mechanics -------------------------------------------

    def _runner_move(self, action: int) -> bool:
        x, y = self.runner
        here = self.effective_tile(x, y)
        below = self.effective_tile(x, y + 1) if y + 1 < self.height else SOLID

        if action == ACT_NONE:
            return False

        if action == ACT_LEFT or action == ACT_RIGHT:
            dx = -1 if action == ACT_LEFT else 1
            nx = x + dx
            if nx < 0 or nx >= self.width:
                return False
            target = self.effective_tile(nx, y)
            if target in SOLID_SET:
                return False
            # A guard in the cell blocks the runner.
            if self.guard_at(nx, y) is not None:
                return False
            self.runner = (nx, y)
            return True

        if action == ACT_UP:
            # Only allowed if on a ladder (current cell is ladder). The
            # runner cannot climb up through a ladder that's just below.
            if here != LADDER:
                return False
            if y - 1 < 0:
                return False
            target = self.effective_tile(x, y - 1)
            if target in SOLID_SET:
                return False
            if self.guard_at(x, y - 1) is not None:
                return False
            self.runner = (x, y - 1)
            return True

        if action == ACT_DOWN:
            if y + 1 >= self.height:
                return False
            target = self.effective_tile(x, y + 1)
            if target in SOLID_SET:
                return False
            # If we're on a rope, pressing down drops us (handled by
            # gravity on next tick); for discrete logic we just step off.
            if self.guard_at(x, y + 1) is not None:
                return False
            self.runner = (x, y + 1)
            return True

        return False

    def _dig(self, dx: int) -> bool:
        """Dig the brick diagonally-below (dx = -1 or +1). Must have
        empty cell directly above the target (classic rule). Target
        must be BRICK (not SOLID/TRAP/LADDER/etc.)."""
        x, y = self.runner
        tx, ty = x + dx, y + 1
        if ty >= self.height:
            return False
        if tx < 0 or tx >= self.width:
            return False
        if self.grid[ty][tx] != BRICK:
            return False
        # Need empty above the brick (otherwise you can't dig from above).
        above = self.grid[y][tx]
        if above not in (EMPTY, ROPE):
            # Note: a hidden ladder at `above` that isn't exposed yet
            # reads as EMPTY in `grid` (we put EMPTY there at parse),
            # so this check works.
            return False
        # Convert to HOLE and track.
        self.grid[ty][tx] = HOLE
        self.holes.append(Hole(tx, ty, self.hole_ticks))
        return True

    def _find_guard_respawn(self) -> tuple[int, int] | None:
        """Find a top-row empty cell for a guard to respawn in."""
        for y in range(self.height):
            for x in range(self.width):
                if self.grid[y][x] == EMPTY and self.guard_at(x, y) is None \
                        and self.runner != (x, y):
                    return (x, y)
        return None

    # ---- guard AI ----------------------------------------------------

    def _tick_guards(self) -> None:
        for guard in self.guards:
            # If trapped in a hole, climb-out timer tracks.
            if guard.in_hole > 0:
                guard.in_hole -= 1
                continue
            # If the cell the guard is on is a HOLE, they're trapped.
            if self.grid[guard.y][guard.x] == HOLE:
                guard.in_hole = 8
                continue
            self._guard_one_step(guard)
            # Gravity for guard.
            if not self.is_standable(guard.x, guard.y) \
                    and guard.y + 1 < self.height:
                below = self.effective_tile(guard.x, guard.y + 1)
                if below not in SOLID_SET:
                    guard.y += 1

            # Gold behavior: pick up if on gold and not already carrying.
            if not guard.carrying_gold \
                    and (guard.x, guard.y) in self.gold_positions:
                # Guards pick up gold with some probability; for simplicity
                # always pick up.
                self.gold_positions.discard((guard.x, guard.y))
                guard.carrying_gold = True
            # Drop carried gold occasionally — if guard is climbing a
            # ladder and there's empty space here, drop with 10% chance.
            # Deterministic: drop when carrying and on ladder at certain
            # tick parity.
            elif guard.carrying_gold \
                    and self.effective_tile(guard.x, guard.y) == LADDER \
                    and (self.tick_count + guard.x + guard.y) % 23 == 0:
                # Drop in an empty cell below-ish.
                self.gold_positions.add((guard.x, guard.y))
                guard.carrying_gold = False

    def _guard_one_step(self, guard: Guard) -> None:
        """Move the guard one cell toward the runner.

        Classic guards use a pathfinding heuristic — prefer ladder/rope
        to get vertically aligned with the runner, then approach
        horizontally. Implementation is a simple BFS with bounded depth.
        """
        target = self.runner
        # Quick-out: already at runner.
        if (guard.x, guard.y) == target:
            return
        step = self._bfs_step(guard.x, guard.y, target)
        if step is None:
            return
        nx, ny = step
        # Don't stack two guards on the same cell.
        if self.guard_at(nx, ny) is not None:
            return
        guard.x, guard.y = nx, ny

    def _bfs_step(self, sx: int, sy: int,
                  target: tuple[int, int],
                  max_nodes: int = 400) -> tuple[int, int] | None:
        """Breadth-first search from (sx, sy) toward target. Returns the
        first-step (nx, ny), or None if no path within bound.

        Neighbors: up (if on ladder), down (if below passable),
        left/right (if passable), fall (below is empty)."""
        if (sx, sy) == target:
            return None
        seen: dict[tuple[int, int], tuple[int, int] | None] = {(sx, sy): None}
        q: deque[tuple[int, int]] = deque([(sx, sy)])
        nodes = 0
        while q and nodes < max_nodes:
            nodes += 1
            x, y = q.popleft()
            if (x, y) == target:
                # Reconstruct step.
                prev = (x, y)
                # walk back to the FIRST step from (sx, sy)
                while True:
                    parent = seen[prev]
                    if parent is None or parent == (sx, sy):
                        return prev
                    prev = parent
            for nx, ny in self._guard_neighbors(x, y):
                if (nx, ny) in seen:
                    continue
                seen[(nx, ny)] = (x, y)
                q.append((nx, ny))
        # If we saw the target at all, reconstruct.
        if target in seen:
            prev = target
            while True:
                parent = seen[prev]
                if parent is None or parent == (sx, sy):
                    return prev
                prev = parent
        # Otherwise return the neighbor closest to the target (greedy
        # fallback) so guards keep nagging the player.
        best: tuple[int, int] | None = None
        best_d = 1 << 30
        for (x, y) in seen:
            if (x, y) == (sx, sy):
                continue
            d = abs(x - target[0]) + abs(y - target[1])
            if d < best_d:
                best_d = d
                best = (x, y)
        if best is None:
            return None
        # walk back to the first step
        prev = best
        while True:
            parent = seen[prev]
            if parent is None or parent == (sx, sy):
                return prev
            prev = parent

    def _guard_neighbors(self, x: int, y: int) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        here = self.effective_tile(x, y)
        # Horizontal (passable if not solid, and has support or is on rope)
        for dx in (-1, 1):
            nx = x + dx
            if nx < 0 or nx >= self.width:
                continue
            t = self.effective_tile(nx, y)
            if t in SOLID_SET:
                continue
            out.append((nx, y))
        # Up: only from ladder
        if y - 1 >= 0 and here == LADDER:
            t = self.effective_tile(x, y - 1)
            if t not in SOLID_SET:
                out.append((x, y - 1))
        # Down: if below is not solid
        if y + 1 < self.height:
            t = self.effective_tile(x, y + 1)
            if t not in SOLID_SET:
                out.append((x, y + 1))
        return out
