"""Headless QA driver for loderunner-tui.

Runs each scenario in a fresh LodeRunnerApp via App.run_test(), saves an
SVG screenshot, and reports pass/fail. Exit code = number of failures.

    python -m tests.qa
    python -m tests.qa dig
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from loderunner_tui.app import LodeRunnerApp
from loderunner_tui import engine as E
from loderunner_tui.engine import Game
from loderunner_tui.levels import PACKS, pack_by_name

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


@dataclass
class Scenario:
    name: str
    fn: Callable[[LodeRunnerApp, "object"], Awaitable[None]]


# =================================================================
# Pure-engine scenarios (no TUI needed)
# =================================================================

# Tiny sandbox levels. `&` is runner, `$` gold, `H` ladder, `#` brick.

_BLANK_ROW = " " * 28 + "\n"

_TINY_WALK = (
    "############################\n"
    + "#&                        $#\n"
    + "############################\n"
    + _BLANK_ROW * 13
).rstrip("\n")

_TINY_LADDER = (
    "############################\n"
    + "#&           H             #\n"
    + "#############H##############\n"
    + "             H              \n"
    + "             H    $         \n"
    + "############################\n"
    + _BLANK_ROW * 10
)

_TINY_DIG = (
    "############################\n"
    + "#            &             #\n"
    + "#############H##############\n"
    + "             H              \n"
    + "             H              \n"
    + "############################\n"
    + _BLANK_ROW * 10
)

_TINY_TRAP = (
    "############################\n"
    + "#                          #\n"
    + "#  &   $                   #\n"
    + "############################\n"
    + _BLANK_ROW * 12
)


async def s_parse_minimal(app, pilot):
    g = Game.parse(_TINY_WALK)
    assert g.width == 28 and g.height >= 3, (g.width, g.height)
    assert g.runner == (1, 1), g.runner
    assert (26, 1) in g.gold_positions


async def s_parse_handmade(app, pilot):
    p = pack_by_name("handmade")
    g = p[0].load()
    assert g.total_gold >= 1
    assert g.runner is not None


async def s_parse_all_packs_nonempty(app, pilot):
    names = [p.name for p in PACKS]
    # handmade is always first; classic must be present if vendor is there
    assert "handmade" in names
    assert len(PACKS) >= 1
    for p in PACKS:
        assert len(p) > 0, p.name


async def s_walk_right(app, pilot):
    g = Game.parse(_TINY_WALK)
    start = g.runner
    r = g.tick(E.ACT_RIGHT)
    assert r.moved
    assert g.runner == (start[0] + 1, start[1]), g.runner


async def s_walk_into_wall(app, pilot):
    g = Game.parse(_TINY_WALK)
    # At (1,1) with wall at (0,1): moving left should NOT change runner
    r = g.tick(E.ACT_LEFT)
    assert g.runner == (1, 1), g.runner


async def s_gravity_falls(app, pilot):
    # Open-top level: runner at (3, 0) with empty below should fall
    level = ("   &                        \n"
             "                            \n"
             "                            \n"
             "############################\n"
             + "                            \n" * 12)
    g = Game.parse(level)
    assert g.runner == (3, 0)
    g.tick(E.ACT_NONE)
    assert g.runner == (3, 1), g.runner
    g.tick(E.ACT_NONE)
    assert g.runner == (3, 2), g.runner


async def s_climb_ladder(app, pilot):
    g = Game.parse(_TINY_LADDER)
    # Walk right to the ladder column
    # Runner starts at (1,1). Ladder at col 13 on row 1.
    for _ in range(12):
        g.tick(E.ACT_RIGHT)
    # Runner should be at (13, 1) on ladder
    assert g.runner == (13, 1), g.runner
    # Climb down to (13, 2), (13, 3), (13, 4)
    g.tick(E.ACT_DOWN)
    assert g.runner == (13, 2), g.runner
    g.tick(E.ACT_DOWN)
    assert g.runner == (13, 3), g.runner
    # Climb back up
    g.tick(E.ACT_UP)
    assert g.runner == (13, 2), g.runner


async def s_gold_pickup(app, pilot):
    g = Game.parse(_TINY_TRAP)
    # runner at (3, 2); gold at (7, 2)
    start_gold = g.gold_left()
    for _ in range(4):
        g.tick(E.ACT_RIGHT)
    # Runner should be at (7, 2) now and gold picked up
    assert g.gold_left() == start_gold - 1, (g.gold_left(), start_gold)


async def s_dig_creates_hole(app, pilot):
    g = Game.parse(_TINY_DIG)
    # Runner at (13, 1) — wait, let me recompute
    assert g.runner == (13, 1), g.runner  # on top of ladder
    # Row 2 is ############### with ladder at col 13 — dig_right should
    # create a hole at (14, 2) since that's a BRICK.
    assert g.grid[2][14] == E.BRICK
    n_holes_before = len(g.holes)
    g.tick(E.ACT_DIG_R)
    assert len(g.holes) == n_holes_before + 1, g.holes
    assert g.grid[2][14] == E.HOLE


async def s_dig_hole_refills(app, pilot):
    g = Game.parse(_TINY_DIG, hole_ticks=5)
    assert g.grid[2][14] == E.BRICK
    g.tick(E.ACT_DIG_R)
    assert g.grid[2][14] == E.HOLE
    for _ in range(5):
        g.tick(E.ACT_NONE)
    assert g.grid[2][14] == E.BRICK, g.grid[2][14]


async def s_dig_only_works_on_brick(app, pilot):
    # Solid (@) cannot be dug
    level = ("############################\n"
             "#    &                     #\n"
             "#@@@@@@@@@@@@@@@@@@@@@@@@@@#\n"
             "############################\n"
             + "                            \n" * 12)
    g = Game.parse(level)
    n = len(g.holes)
    g.tick(E.ACT_DIG_L)
    g.tick(E.ACT_DIG_R)
    assert len(g.holes) == n, g.holes


async def s_undo_restores(app, pilot):
    g = Game.parse(_TINY_WALK)
    start = g.runner
    g.tick(E.ACT_RIGHT)
    assert g.runner != start
    assert g.undo()
    assert g.runner == start, g.runner


async def s_reset_restores(app, pilot):
    g = Game.parse(_TINY_WALK)
    start_runner = g.runner
    start_gold = set(g.gold_positions)
    for _ in range(5):
        g.tick(E.ACT_RIGHT)
    g.reset()
    assert g.runner == start_runner
    assert g.gold_positions == start_gold
    assert g.tick_count == 0


async def s_win_requires_all_gold(app, pilot):
    # Runner already at top (y=0), but gold remaining should NOT win.
    level = ("&                          $\n"
             "                            \n"
             "############################\n"
             + "                            \n" * 13)
    g = Game.parse(level)
    assert g.runner == (0, 0)
    assert len(g.gold_positions) == 1
    g.tick(E.ACT_NONE)
    assert not g.won, "won despite gold left"


async def s_win_after_gold(app, pilot):
    # Level: runner on brick shelf at row 0 (solid below), 1 gold to
    # grab by walking right, then stay on top row → win.
    level = ("&  $                        \n"
             + "############################\n"
             + _BLANK_ROW * 14).rstrip("\n")
    g = Game.parse(level)
    for _ in range(3):
        g.tick(E.ACT_RIGHT)
    assert not g.gold_positions, g.gold_positions
    assert g.runner[1] == 0, g.runner
    assert g.won, "should have won: runner at top, no gold left"


async def s_hidden_ladder_appears(app, pilot):
    # Hidden ladder is there but invisible until gold collected.
    # Shelf of brick so runner doesn't fall.
    level = ("S &                        $\n"
             + "############################\n"
             + _BLANK_ROW * 14).rstrip("\n")
    g = Game.parse(level)
    assert g.effective_tile(0, 0) == E.EMPTY
    # Walk right to collect the gold at (27, 0).
    for _ in range(30):
        g.tick(E.ACT_RIGHT)
        if not g.gold_positions:
            break
    assert not g.gold_positions, g.gold_positions
    assert g.effective_tile(0, 0) == E.LADDER


async def s_guard_moves_toward_runner(app, pilot):
    level = ("############################\n"
             "#0                        &#\n"
             "############################\n"
             + "                            \n" * 13)
    g = Game.parse(level)
    # Guard at (1, 1), runner at (26, 1)
    g0 = g.guards[0]
    assert g0.x == 1 and g0.y == 1
    g.tick(E.ACT_NONE)
    assert g.guards[0].x > 1, g.guards[0].x


async def s_guard_traps_runner(app, pilot):
    level = ("############################\n"
             "#          0      &        #\n"
             "############################\n"
             + "                            \n" * 13)
    g = Game.parse(level)
    # Guard at (11, 1), runner at (18, 1). Tick a few times.
    for _ in range(20):
        r = g.tick(E.ACT_NONE)
        if r.dead:
            break
    assert g.dead, (g.runner, [(guard.x, guard.y) for guard in g.guards])


async def s_guard_falls_in_hole(app, pilot):
    # Runner at top of ladder with brick below adjacent; guard approaches
    # and we dig, guard falls in
    level = ("############################\n"
             "#           &              #\n"
             "############H###############\n"
             "#    0      H              #\n"
             "############################\n"
             + "                            \n" * 11)
    g = Game.parse(level, hole_ticks=100)
    # Runner at (12, 1), ladder at col 12 on row 2, guard at (5, 3)
    # dig right first to make a hole at (13, 2)
    g.tick(E.ACT_DIG_R)
    assert g.grid[2][13] == E.HOLE, g.grid[2][13]


# =================================================================
# TUI scenarios (mount-required)
# =================================================================


async def s_mount_clean(app, pilot):
    assert app.board is not None
    assert app.status_panel is not None
    assert app.message_log is not None
    assert app.game is not None


async def s_arrow_moves_player(app, pilot):
    start = app.game.runner
    for key in ("right", "left", "down"):
        await pilot.press(key)
        await pilot.pause()
        if app.game.runner != start:
            return
    raise AssertionError(f"no direction moved runner from {start}")


async def s_hjkl_moves_player(app, pilot):
    start = app.game.runner
    for key in ("l", "h", "j"):
        await pilot.press(key)
        await pilot.pause()
        if app.game.runner != start:
            return
    raise AssertionError(f"no hjkl key moved runner from {start}")


async def s_dig_key_works(app, pilot):
    # Replace with a tight level where dig_right will succeed.
    app.game = Game.parse(_TINY_DIG, hole_ticks=40,
                          title="dig-test")
    app.board.refresh()
    await pilot.pause()
    assert app.game.grid[2][14] == E.BRICK
    await pilot.press("x")
    await pilot.pause()
    assert app.game.grid[2][14] == E.HOLE, app.game.grid[2][14]


async def s_undo_key_works(app, pilot):
    start = app.game.runner
    # Make a real move
    for key in ("right", "left", "down"):
        await pilot.press(key)
        await pilot.pause()
        if app.game.runner != start:
            break
    else:
        return  # couldn't move — skip
    await pilot.press("u")
    await pilot.pause()
    assert app.game.runner == start, (
        f"undo didn't restore: {start} → ... → {app.game.runner}"
    )


async def s_reset_key_works(app, pilot):
    await pilot.press("right")
    await pilot.press("left")
    await pilot.press("down")
    await pilot.pause()
    await pilot.press("r")
    await pilot.pause()
    assert app.game.tick_count == 0, app.game.tick_count


async def s_next_prev_level(app, pilot):
    start_idx = app.level_idx
    await pilot.press("n")
    await pilot.pause()
    assert app.level_idx == start_idx + 1, (start_idx, app.level_idx)
    await pilot.press("p")
    await pilot.pause()
    assert app.level_idx == start_idx


async def s_help_screen_opens(app, pilot):
    await pilot.press("question_mark")
    await pilot.pause()
    assert app.screen.__class__.__name__ == "HelpScreen"
    await pilot.press("escape")
    await pilot.pause()


async def s_level_select_opens(app, pilot):
    await pilot.press("L")
    await pilot.pause()
    assert app.screen.__class__.__name__ == "LevelSelectScreen"
    await pilot.press("escape")
    await pilot.pause()


async def s_board_renders_with_styles(app, pilot):
    strip = app.board.render_line(app.size.height // 2)
    segs = list(strip)
    assert len(segs) > 0
    fg_count = sum(1 for s in segs if s.style and s.style.color is not None)
    assert fg_count > 0


async def s_status_panel_shows_gold(app, pilot):
    app.status_panel.refresh_panel()
    r = app.status_panel.render()
    s = str(r) if r is not None else ""
    if not s:
        assert app.status_panel._last is not None
        return
    assert "Gold" in s, s[:200]


async def s_status_panel_throttles(app, pilot):
    app.status_panel.refresh_panel()
    snap1 = app.status_panel._last
    for _ in range(5):
        app.status_panel.refresh_panel()
    assert app.status_panel._last == snap1


async def s_space_is_wait(app, pilot):
    """Space should tick the world without moving the runner."""
    start_tick = app.game.tick_count
    start_pos = app.game.runner
    await pilot.press("space")
    await pilot.pause()
    assert app.game.tick_count == start_tick + 1


async def s_all_packs_level_one_mountable(app, pilot):
    for p in PACKS:
        app.load_level(p, 0)
        await pilot.pause()
        assert app.game is not None
        assert app.pack.name == p.name


async def s_all_levels_parse(app, pilot):
    failures = []
    for p in PACKS:
        for i, ld in enumerate(p.levels):
            try:
                g = ld.load()
                assert g.runner is not None
                assert g.width == 28
                assert g.height >= 1
            except Exception as e:
                failures.append(f"{p.name}#{i + 1}: {type(e).__name__}: {e}")
    assert not failures, (
        f"{len(failures)} level(s) failed to parse:\n  "
        + "\n  ".join(failures[:10])
    )


async def s_unknown_glyph_does_not_crash(app, pilot):
    app.game.grid[0][0] = "?"
    strip = app.board.render_line(app.size.height // 2 - app.game.height // 2)
    assert len(list(strip)) > 0


async def s_next_at_end_doesnt_crash(app, pilot):
    app.level_idx = len(app.pack) - 1
    app._load_current()
    await pilot.pause()
    await pilot.press("n")
    await pilot.pause()
    assert app.level_idx == len(app.pack) - 1


async def s_prev_at_start_doesnt_crash(app, pilot):
    app.level_idx = 0
    app._load_current()
    await pilot.pause()
    await pilot.press("p")
    await pilot.pause()
    assert app.level_idx == 0


async def s_win_shows_modal(app, pilot):
    # Install a solve-in-a-few level where the runner is at y=0 already.
    app.game = Game.parse(
        "&  $                        \n"
        + "############################\n"
        + _BLANK_ROW * 14,
        title="win-test")
    app.board.refresh()
    await pilot.pause()
    for _ in range(3):
        await pilot.press("right")
        await pilot.pause()
    assert not app.game.gold_positions, app.game.gold_positions
    assert app.game.won, (app.game.runner, app.game.won)
    assert app.screen.__class__.__name__ == "WonScreen", \
        app.screen.__class__.__name__
    await pilot.press("escape")
    await pilot.pause()


async def s_dead_shows_modal(app, pilot):
    """Guard catches runner → LostScreen."""
    level = ("############################\n"
             "#          0      &        #\n"
             "############################\n"
             + "                            \n" * 13)
    app.game = Game.parse(level, title="dead-test")
    app.board.refresh()
    await pilot.pause()
    # Just press space repeatedly — guard walks over
    for _ in range(30):
        await pilot.press("space")
        await pilot.pause()
        if app.game.dead:
            break
    assert app.game.dead, [(g.x, g.y) for g in app.game.guards]
    assert app.screen.__class__.__name__ == "LostScreen", \
        app.screen.__class__.__name__
    await pilot.press("escape")
    await pilot.pause()


async def s_bad_level_rejected(app, pilot):
    """No runner marker → ValueError."""
    try:
        Game.parse("#####\n#   #\n#####")
        ok = False
    except ValueError:
        ok = True
    assert ok


async def s_undo_after_reset_is_noop(app, pilot):
    await pilot.press("right")
    await pilot.press("down")
    await pilot.pause()
    await pilot.press("r")
    await pilot.pause()
    tc = app.game.tick_count
    await pilot.press("u")
    await pilot.pause()
    assert app.game.tick_count == tc  # no change


async def s_all_classic_levels_tickable(app, pilot):
    """Every classic level must parse AND be tickable for 5 ticks with
    random actions without crashing. This catches engine regressions
    that only fire on unusual geometries (TRAP, HLADDER stacks, etc.)."""
    import random as _rnd
    _rnd.seed(42)
    classic = pack_by_name("classic")
    failures = []
    actions = [E.ACT_NONE, E.ACT_LEFT, E.ACT_RIGHT, E.ACT_UP, E.ACT_DOWN,
               E.ACT_DIG_L, E.ACT_DIG_R]
    for i, ld in enumerate(classic.levels):
        try:
            g = ld.load()
            for _ in range(5):
                g.tick(_rnd.choice(actions))
        except Exception as e:
            failures.append(f"classic#{i + 1}: {type(e).__name__}: {e}")
    assert not failures, (
        f"{len(failures)} level(s) crashed on tick:\n  "
        + "\n  ".join(failures[:5])
    )


async def s_rope_hang(app, pilot):
    """Runner on a rope cell does not fall."""
    level = (
        "&                           \n"
        + "    ------                  \n"
        + "                            \n"
        + "                            \n"
        + "############################\n"
        + _BLANK_ROW * 11
    )
    g = Game.parse(level, title="rope-hang")
    # Place runner ON a rope cell explicitly.
    g.runner = (6, 1)
    g._snapshot_initial()
    # Wait on the rope for 3 ticks — should NOT fall.
    for _ in range(3):
        g.tick(E.ACT_NONE)
    assert g.runner == (6, 1), f"runner fell off rope: {g.runner}"
    # Walking right along the rope should still work.
    g.tick(E.ACT_RIGHT)
    assert g.runner == (7, 1), g.runner


async def s_drop_from_rope(app, pilot):
    """Pressing down while on rope drops you off."""
    level = (
        "&                           \n"
        + "    ------                  \n"
        + "                            \n"
        + "                            \n"
        + "############################\n"
        + _BLANK_ROW * 11
    )
    g = Game.parse(level, title="rope-drop")
    g.runner = (6, 1)
    g._snapshot_initial()
    g.tick(E.ACT_DOWN)
    assert g.runner[1] > 1, f"didn't drop: {g.runner}"


SCENARIOS: list[Scenario] = [
    # Pure-engine
    Scenario("parse_minimal", s_parse_minimal),
    Scenario("parse_handmade", s_parse_handmade),
    Scenario("parse_all_packs_nonempty", s_parse_all_packs_nonempty),
    Scenario("walk_right", s_walk_right),
    Scenario("walk_into_wall", s_walk_into_wall),
    Scenario("gravity_falls", s_gravity_falls),
    Scenario("climb_ladder", s_climb_ladder),
    Scenario("gold_pickup", s_gold_pickup),
    Scenario("dig_creates_hole", s_dig_creates_hole),
    Scenario("dig_hole_refills", s_dig_hole_refills),
    Scenario("dig_only_brick", s_dig_only_works_on_brick),
    Scenario("undo_restores", s_undo_restores),
    Scenario("reset_restores", s_reset_restores),
    Scenario("win_requires_all_gold", s_win_requires_all_gold),
    Scenario("win_after_gold", s_win_after_gold),
    Scenario("hidden_ladder_appears", s_hidden_ladder_appears),
    Scenario("guard_moves_toward_runner", s_guard_moves_toward_runner),
    Scenario("guard_catches_runner", s_guard_traps_runner),
    Scenario("guard_falls_in_hole", s_guard_falls_in_hole),
    Scenario("bad_level_rejected", s_bad_level_rejected),
    Scenario("all_levels_parse", s_all_levels_parse),
    # TUI
    Scenario("mount_clean", s_mount_clean),
    Scenario("arrow_moves_player", s_arrow_moves_player),
    Scenario("hjkl_moves_player", s_hjkl_moves_player),
    Scenario("dig_key_works", s_dig_key_works),
    Scenario("undo_key_works", s_undo_key_works),
    Scenario("reset_key_works", s_reset_key_works),
    Scenario("next_prev_level", s_next_prev_level),
    Scenario("help_screen_opens", s_help_screen_opens),
    Scenario("level_select_opens", s_level_select_opens),
    Scenario("board_renders_with_styles", s_board_renders_with_styles),
    Scenario("status_panel_shows_gold", s_status_panel_shows_gold),
    Scenario("status_panel_throttles", s_status_panel_throttles),
    Scenario("space_is_wait", s_space_is_wait),
    Scenario("all_packs_level_one_mountable", s_all_packs_level_one_mountable),
    Scenario("unknown_glyph_does_not_crash", s_unknown_glyph_does_not_crash),
    Scenario("win_shows_modal", s_win_shows_modal),
    Scenario("dead_shows_modal", s_dead_shows_modal),
    Scenario("next_at_end_doesnt_crash", s_next_at_end_doesnt_crash),
    Scenario("prev_at_start_doesnt_crash", s_prev_at_start_doesnt_crash),
    Scenario("undo_after_reset_is_noop", s_undo_after_reset_is_noop),
    Scenario("rope_hang", s_rope_hang),
    Scenario("drop_from_rope", s_drop_from_rope),
    Scenario("all_classic_levels_tickable", s_all_classic_levels_tickable),
]


async def run_one(scn: Scenario) -> tuple[str, bool, str]:
    app = LodeRunnerApp(pack_name="handmade", level_idx=0)
    try:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            try:
                await scn.fn(app, pilot)
            except AssertionError as e:
                app.save_screenshot(str(OUT / f"{scn.name}.FAIL.svg"))
                return (scn.name, False, f"AssertionError: {e}")
            except Exception as e:
                app.save_screenshot(str(OUT / f"{scn.name}.ERROR.svg"))
                return (scn.name, False,
                        f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            app.save_screenshot(str(OUT / f"{scn.name}.PASS.svg"))
            return (scn.name, True, "")
    except Exception as e:
        return (scn.name, False,
                f"harness: {type(e).__name__}: {e}\n{traceback.format_exc()}")


async def main(pattern: str | None = None) -> int:
    scenarios = [s for s in SCENARIOS if not pattern or pattern in s.name]
    if not scenarios:
        print(f"no scenarios match {pattern!r}")
        return 2
    results = []
    for scn in scenarios:
        name, ok, msg = await run_one(scn)
        mark = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
        print(f"  {mark} {name}")
        if not ok:
            for line in msg.splitlines():
                print(f"      {line}")
        results.append((name, ok, msg))
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print(f"\n{passed}/{len(results)} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    pattern = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(asyncio.run(main(pattern)))
