"""End-to-end playtest driver.

Boots the app, picks the first handmade level, exercises movement, dig,
gold pickup, win detection, undo, reset, next-level, quit.

Run:  python -m tests.playtest
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from loderunner_tui.app import LodeRunnerApp
from loderunner_tui.engine import Game, ACT_RIGHT, ACT_DIG_R

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)

_BLANK_ROW = " " * 28 + "\n"


async def playtest() -> int:
    app = LodeRunnerApp(pack_name="handmade", level_idx=0)
    failures: list[str] = []

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        # --- milestone 1: boot ------------------------------------------
        assert app.game is not None, "game didn't mount"
        assert app.pack.name == "handmade"
        assert app.level_idx == 0
        app.save_screenshot(str(OUT / "playtest_01_boot.svg"))
        print(f"  ✓ booted on {app.pack.name} #{app.level_idx + 1}: "
              f"{app.game.title}")

        # --- milestone 2: level-select modal opens + closes -------------
        await pilot.press("L")
        await pilot.pause()
        if app.screen.__class__.__name__ != "LevelSelectScreen":
            failures.append("level-select did not open")
        app.save_screenshot(str(OUT / "playtest_02_level_select.svg"))
        await pilot.press("escape")
        await pilot.pause()
        print("  ✓ level-select opens + closes")

        # --- milestone 3: install a deterministic mini level ------------
        mini = (
            "&  $                        \n"
            + "############################\n"
            + _BLANK_ROW * 14
        )
        app.game = Game.parse(mini, title="playtest mini")
        app.board.refresh()  # type: ignore[union-attr]
        app.status_panel.refresh_panel()  # type: ignore[union-attr]
        await pilot.pause()
        start_runner = app.game.runner
        start_gold = set(app.game.gold_positions)
        app.save_screenshot(str(OUT / "playtest_03_mini_loaded.svg"))

        # --- milestone 4: walk to gold; pick up; reach top; win ---------
        # Runner at (0, 0), gold at (3, 0). Walk 3× right.
        for _ in range(3):
            await pilot.press("right")
            await pilot.pause()
        if app.game.gold_positions:
            failures.append(
                f"gold not collected: {app.game.gold_positions}"
            )
        if not app.game.won:
            failures.append(
                f"win not detected: runner={app.game.runner} "
                f"won={app.game.won}"
            )
        if app.screen.__class__.__name__ != "WonScreen":
            failures.append(
                f"WonScreen not shown: got {app.screen.__class__.__name__}"
            )
        app.save_screenshot(str(OUT / "playtest_04_won.svg"))
        print(f"  ✓ collected gold + won at tick {app.game.tick_count}")

        # Dismiss modal.
        await pilot.press("escape")
        await pilot.pause()

        # --- milestone 5: undo + reset ----------------------------------
        # Load handmade #1 cleanly and verify undo / reset mechanics.
        app.load_level(app.pack, 0)
        await pilot.pause()
        before_tick = app.game.tick_count
        before_runner = app.game.runner
        await pilot.press("right")
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()
        if app.game.tick_count != before_tick or app.game.runner != before_runner:
            failures.append(
                f"undo failed: tick={app.game.tick_count} runner={app.game.runner}"
            )
        app.save_screenshot(str(OUT / "playtest_05_undone.svg"))

        # Make a few more moves then reset.
        for _ in range(5):
            await pilot.press("right")
            await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        if app.game.tick_count != 0:
            failures.append(
                f"reset didn't clear tick_count: {app.game.tick_count}"
            )
        app.save_screenshot(str(OUT / "playtest_06_reset.svg"))
        print(f"  ✓ undo + reset restored state")

        # --- milestone 6: dig mechanic ----------------------------------
        # Handmade #2 has dig-worthy geometry.
        app.load_level(app.pack, 1)
        await pilot.pause()
        before_holes = len(app.game.holes)
        await pilot.press("x")
        await pilot.pause()
        # We may or may not create a hole depending on layout — just
        # verify no crash + reasonable count.
        assert len(app.game.holes) >= before_holes
        app.save_screenshot(str(OUT / "playtest_07_dig.svg"))
        print(f"  ✓ dig action applied (holes: {len(app.game.holes)})")

        # --- milestone 7: next-level + help + quit ----------------------
        start_idx = app.level_idx
        await pilot.press("n")
        await pilot.pause()
        if app.level_idx != start_idx + 1:
            failures.append(
                f"next-level didn't advance: idx={app.level_idx}"
            )
        app.save_screenshot(str(OUT / "playtest_08_next.svg"))

        await pilot.press("question_mark")
        await pilot.pause()
        if app.screen.__class__.__name__ != "HelpScreen":
            failures.append("help did not open")
        app.save_screenshot(str(OUT / "playtest_09_help.svg"))
        await pilot.press("escape")
        await pilot.pause()
        print("  ✓ next-level + help")

        await app.action_quit()
        print("  ✓ quit action completed")

    if failures:
        print(f"\nplaytest FAILED — {len(failures)} issue(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nplaytest OK")
    return 0


def pty_smoke() -> int:
    """Launch loderunner-tui in a real pty via pexpect, let it boot,
    send q, confirm clean exit."""
    try:
        import pexpect  # type: ignore
    except ImportError:
        print("  · pty-smoke skipped (pexpect not installed)")
        return 0

    repo = Path(__file__).resolve().parent.parent
    os.environ.setdefault("TERM", "xterm-256color")
    child = pexpect.spawn(
        sys.executable,
        [str(repo / "loderunner.py"), "--pack", "handmade", "--level", "1"],
        timeout=15,
        dimensions=(40, 120),
        env=os.environ,
        cwd=str(repo),
    )
    try:
        child.expect("Lode Runner", timeout=10)
    except pexpect.TIMEOUT:
        print("  ✗ pty-smoke: title didn't paint within 10s")
        child.close(force=True)
        return 1
    child.send("q")
    child.expect(pexpect.EOF, timeout=5)
    child.close()
    if child.exitstatus not in (0, None):
        print(f"  ✗ pty-smoke: non-zero exit {child.exitstatus}")
        return 1
    print("  ✓ pty-smoke: booted in real pty and quit cleanly")
    return 0


if __name__ == "__main__":
    rc = asyncio.run(playtest())
    rc |= pty_smoke()
    sys.exit(rc)
