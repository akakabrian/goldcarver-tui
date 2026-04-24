"""Hot-path benchmarks for goldcarver-tui.

The engine is tiny so these mostly guard against regressions. Baseline
numbers are printed — run again after any engine change to compare."""

from __future__ import annotations

import random
import time
from pathlib import Path

from goldcarver_tui.engine import (
    ACT_NONE, ACT_LEFT, ACT_RIGHT, ACT_UP, ACT_DOWN, ACT_DIG_L, ACT_DIG_R,
    Game,
)
from goldcarver_tui.levels import PACKS


def bench(label: str, fn, repeats: int = 2000) -> None:
    samples: list[int] = []
    for _ in range(min(200, repeats // 10 or 1)):
        fn()
    for _ in range(repeats):
        t0 = time.perf_counter_ns()
        fn()
        samples.append(time.perf_counter_ns() - t0)
    samples.sort()
    med = samples[len(samples) // 2] / 1000.0
    p99 = samples[int(len(samples) * 0.99)] / 1000.0
    print(f"  {label:<44} median {med:>8.2f} µs   p99 {p99:>8.2f} µs  (n={repeats})")


def main() -> None:
    # Pick the biggest classic level for a realistic run.
    classic = next(p for p in PACKS if p.name == "classic")
    sample = classic[0]  # classic #1
    xsb = sample.to_text()

    print(f"sample level: classic #{1} — 28×16, "
          f"{sample.raw.count('0')} guards, {sample.raw.count('$')} gold")

    print("\nEngine hot paths:")
    bench("Game.parse (classic #1)", lambda: Game.parse(xsb))

    # Single-move perf (on a fresh game each iter to avoid state drift).
    def one_move():
        g = Game.parse(xsb)
        g.tick(ACT_RIGHT)
    bench("Game.tick right (fresh)", one_move, repeats=1000)

    # Repeated-tick perf on one game (stateful, what a play session looks like).
    g = Game.parse(xsb)
    actions = [ACT_LEFT, ACT_RIGHT, ACT_UP, ACT_DOWN, ACT_NONE, ACT_DIG_L,
               ACT_DIG_R]
    random.seed(0)

    def many_ticks():
        for _ in range(50):
            g.tick(random.choice(actions))
    bench("Game.tick × 50 (stateful)", many_ticks, repeats=500)

    # BFS cost — guards pathfinding dominates in crowded levels.
    g2 = Game.parse(xsb)
    bench("Guard._bfs_step (one guard)",
          lambda: g2._bfs_step(g2.guards[0].x, g2.guards[0].y, g2.runner),
          repeats=500)

    # Load all packs.
    t0 = time.perf_counter_ns()
    total = 0
    for p in PACKS:
        for ld in p.levels:
            ld.load()
            total += 1
    elapsed = (time.perf_counter_ns() - t0) / 1e6
    print(f"\nParse all {total} levels across {len(PACKS)} packs: {elapsed:.1f} ms "
          f"({elapsed * 1000 / total:.1f} µs / level)")

    # Simulate 1000 random moves on a fresh game.
    g3 = Game.parse(xsb)
    random.seed(0)
    t0 = time.perf_counter_ns()
    for _ in range(1000):
        g3.tick(random.choice(actions))
    t1 = time.perf_counter_ns()
    print(f"1000 random ticks: {(t1 - t0) / 1e6:.2f} ms "
          f"({(t1 - t0) / 1000 / 1000:.2f} µs / tick)")


if __name__ == "__main__":
    main()
