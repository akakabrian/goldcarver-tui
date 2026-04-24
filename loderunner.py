#!/usr/bin/env python3
"""Entry point for goldcarver-tui."""

from __future__ import annotations

import argparse
import sys

from goldcarver_tui.app import run
from goldcarver_tui.levels import PACKS


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="goldcarver-tui",
        description="Terminal Lode Runner — classic 150 levels + more.",
    )
    ap.add_argument(
        "--pack", "-p", default=None,
        help=f"pack name (default: {PACKS[0].name}). "
             f"Choices: {', '.join(p.name for p in PACKS)}"
    )
    ap.add_argument("--level", "-l", type=int, default=1,
                    help="level number within pack (1-based, default 1)")
    ap.add_argument("--list", action="store_true",
                    help="list packs and exit")
    args = ap.parse_args()

    if args.list:
        for p in PACKS:
            print(f"  {p.name:<14} {len(p):>4} levels  — {p.display}")
            print(f"              {p.credit}")
        return 0

    run(pack=args.pack, level=args.level - 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
