"""Textual TUI for Lode Runner.

Widgets:
  * BoardView      — Strip-based renderer, 28×16 grid.
  * StatusPanel    — level title, gold count, tick count.
  * ControlsPanel  — key legend.
  * RichLog        — event feedback.
  * flash_bar      — transient single-line message.

Movement is turn-based on key press. The game ticks once per key press
(including "space" for no-op / wait). Guards therefore move only when
the player does — this matches the TUI idiom and avoids a real-time
timer. A toggle for real-time mode could come in Phase E.
"""

from __future__ import annotations

from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.geometry import Size
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Footer, Header, RichLog, Static

from . import engine as E
from . import tiles
from .engine import Game, TickResult
from .levels import PACKS, Pack, LevelData
from .screens import HelpScreen, LevelSelectScreen, LostScreen, WonScreen


# Key → action table. Movement keys are set priority=True so scrollable
# widgets don't eat them.
_KEY_ACTIONS: dict[str, int] = {
    "left":  E.ACT_LEFT,  "h": E.ACT_LEFT,  "a": E.ACT_LEFT,
    "right": E.ACT_RIGHT, "l": E.ACT_RIGHT, "d": E.ACT_RIGHT,
    "up":    E.ACT_UP,    "k": E.ACT_UP,    "w": E.ACT_UP,
    "down":  E.ACT_DOWN,  "j": E.ACT_DOWN,  "s": E.ACT_DOWN,
    "z": E.ACT_DIG_L,    "comma": E.ACT_DIG_L,
    "x": E.ACT_DIG_R,    "full_stop": E.ACT_DIG_R,
    "space": E.ACT_NONE,
}


# --------------------------------------------------------------------
# Board renderer
# --------------------------------------------------------------------


class BoardView(Widget):
    """Renders the Lode Runner grid.

    The grid is fixed at 28 × 16 so we don't bother with viewport
    scrolling — we center it inside the widget. The render path builds
    one Strip per widget row, reading the live Game on every call.
    """

    DEFAULT_CSS = ""

    def __init__(self, app_ref: "LodeRunnerApp", **kw) -> None:
        super().__init__(**kw)
        self._app = app_ref

    def get_content_width(self, container: Size, viewport: Size) -> int:
        g = self._app.game
        return max((g.width if g else 28) + 4, 32)

    def get_content_height(
        self, container: Size, viewport: Size, width: int
    ) -> int:
        g = self._app.game
        return max((g.height if g else 16) + 2, 18)

    def render_line(self, y: int) -> Strip:
        g = self._app.game
        if g is None:
            return Strip.blank(self.size.width)

        widget_w = self.size.width
        widget_h = self.size.height
        pad_x = max(0, (widget_w - g.width) // 2)
        pad_y = max(0, (widget_h - g.height) // 2)

        board_y = y - pad_y
        if board_y < 0 or board_y >= g.height:
            return Strip.blank(widget_w, tiles.S_EMPTY)

        segments: list[Segment] = []
        if pad_x > 0:
            segments.append(Segment(" " * pad_x, tiles.S_EMPTY))

        row_segs: list[Segment] = []
        for x in range(g.width):
            glyph, style = _compose_cell(g, x, board_y)
            row_segs.append(Segment(glyph, style))
        segments.extend(_rle(row_segs))

        used = pad_x + g.width
        if used < widget_w:
            segments.append(Segment(" " * (widget_w - used), tiles.S_EMPTY))
        return Strip(segments)


def _compose_cell(g: Game, x: int, y: int) -> tuple[str, Style]:
    """Return (glyph, style) for cell (x,y), composing terrain + objects."""
    # Objects render on top of terrain.
    if g.runner == (x, y):
        vis = g.visible_tile(x, y)
        if vis == E.LADDER:
            bg = tiles.BG_LADDER
        elif vis == E.ROPE:
            bg = tiles.BG_ROPE
        else:
            bg = tiles.BG_DEFAULT
        return tiles.GLYPH_RUNNER, Style.parse(f"bold rgb(90,220,255) on {bg}")

    guard = g.guard_at(x, y)
    if guard is not None:
        if guard.carrying_gold:
            return tiles.GLYPH_GUARD_GOLD, tiles.S_GUARD_GOLD
        return tiles.GLYPH_GUARD, tiles.S_GUARD

    if (x, y) in g.gold_positions:
        return tiles.GLYPH_GOLD, tiles.S_GOLD

    # Terrain.
    t = g.visible_tile(x, y)
    return tiles.tile_glyph(t), tiles.tile_style(t, x, y)


def _rle(segs: list[Segment]) -> list[Segment]:
    """Coalesce adjacent same-style segments for cheaper repaint."""
    if not segs:
        return segs
    out = [segs[0]]
    for s in segs[1:]:
        last = out[-1]
        if s.style == last.style:
            out[-1] = Segment(last.text + s.text, last.style)
        else:
            out.append(s)
    return out


# --------------------------------------------------------------------
# Side panels
# --------------------------------------------------------------------


class StatusPanel(Static):
    def __init__(self, app_ref: "LodeRunnerApp") -> None:
        super().__init__("", id="status")
        self._app = app_ref
        self._last: tuple | None = None

    def refresh_panel(self) -> None:
        a = self._app
        g = a.game
        if g is None:
            return
        snap = (a.pack.name, a.level_idx, g.tick_count,
                g.gold_left(), g.total_gold, g.won, g.dead, len(g.guards),
                len(g.holes))
        if snap == self._last:
            return
        self._last = snap
        t = Text()
        t.append(f"Pack   {a.pack.display}\n", style="bold rgb(180,200,240)")
        t.append(f"Level  {a.level_idx + 1} / {len(a.pack)}\n",
                 style="rgb(220,220,235)")
        if g.title:
            t.append(f"       {g.title}\n", style="rgb(150,150,170)")
        t.append("\n")
        remaining = g.gold_left()
        collected = g.total_gold - remaining
        gold_color = ("bold rgb(120,230,120)" if remaining == 0
                      else "bold rgb(255,220,80)")
        t.append("Gold    ", style="rgb(150,150,170)")
        t.append(f"{collected} / {g.total_gold}\n", style=gold_color)
        t.append("Guards  ", style="rgb(150,150,170)")
        t.append(f"{len(g.guards)}\n", style="bold rgb(230,230,240)")
        t.append("Holes   ", style="rgb(150,150,170)")
        t.append(f"{len(g.holes)}\n", style="rgb(220,220,235)")
        t.append("Tick    ", style="rgb(150,150,170)")
        t.append(f"{g.tick_count}\n", style="rgb(220,220,235)")
        if g.won:
            t.append("\n★ LEVEL WON", style="bold rgb(120,230,120)")
        elif g.dead:
            t.append("\n✗ DEAD", style="bold rgb(255,120,120)")
        elif remaining == 0:
            t.append("\n↑ climb to top!", style="bold rgb(255,220,80)")
        self.update(t)


class ControlsPanel(Static):
    def __init__(self) -> None:
        t = Text()
        t.append("Controls\n", style="bold rgb(180,200,240)")
        rows = [
            ("←→↑↓ / hjkl",  "move"),
            ("z / x",         "dig left / right"),
            ("space",         "wait"),
            ("u",             "undo"),
            ("r",             "reset"),
            ("n / p",         "next / prev"),
            ("L",             "level select"),
            ("?",             "help"),
            ("q",             "quit"),
        ]
        for k, desc in rows:
            t.append(f"  {k:<14}", style="bold rgb(255,220,80)")
            t.append(f"{desc}\n", style="rgb(200,200,215)")
        super().__init__(t, id="controls")


# --------------------------------------------------------------------
# The App
# --------------------------------------------------------------------


class LodeRunnerApp(App):
    CSS_PATH = "tui.tcss"
    TITLE = "Lode Runner TUI"
    SUB_TITLE = ""

    BINDINGS = [
        # Movement + dig + wait — priority=True so scrollable
        # widgets don't intercept.
        *[Binding(k, f"play('{k}')", show=False, priority=True)
          for k in _KEY_ACTIONS.keys()],
        Binding("u", "undo", "undo", priority=True),
        Binding("r", "reset", "reset"),
        Binding("n", "next_level", "next"),
        Binding("p", "prev_level", "prev"),
        Binding("L", "select_level", "levels"),
        Binding("question_mark", "help", "help"),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self, pack_name: str | None = None,
                 level_idx: int = 0) -> None:
        super().__init__()
        self.pack: Pack = (
            next((p for p in PACKS if p.name == pack_name), PACKS[0])
            if pack_name else PACKS[0]
        )
        self.level_idx = max(0, min(level_idx, len(self.pack) - 1))
        self.game: Game | None = None
        # widgets
        self.board: BoardView | None = None
        self.status_panel: StatusPanel | None = None
        self.flash_bar: Static | None = None
        self.message_log: RichLog | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        self.board = BoardView(self, id="board")
        self.status_panel = StatusPanel(self)
        self.flash_bar = Static("", id="flash")
        self.message_log = RichLog(id="log", max_lines=500, wrap=True,
                                   markup=True)
        with Vertical(id="left"):
            yield self.board
            yield self.flash_bar
        with Vertical(id="right"):
            yield self.status_panel
            yield ControlsPanel()
            yield self.message_log
        yield Footer()

    def on_mount(self) -> None:
        self._load_current()

    # ---- level management ------------------------------------------

    def _load_current(self) -> None:
        data: LevelData = self.pack[self.level_idx]
        self.game = data.load()
        self.sub_title = (f"{self.pack.display} — level "
                          f"{self.level_idx + 1}/{len(self.pack)}")
        if self.status_panel:
            self.status_panel.refresh_panel()
        if self.board:
            self.board.refresh()
        if self.message_log:
            self.message_log.write(
                f"[bold rgb(180,200,240)]▶ {self.game.title}[/] "
                f"({len(self.game.gold_positions)} gold, "
                f"{len(self.game.guards)} guards)"
            )
        self._flash(self.game.title)

    def _flash(self, msg: str) -> None:
        if self.flash_bar:
            self.flash_bar.update(msg)

    def load_level(self, pack: Pack, idx: int) -> None:
        self.pack = pack
        self.level_idx = max(0, min(idx, len(pack) - 1))
        self._load_current()

    # ---- actions ---------------------------------------------------

    def action_play(self, key: str) -> None:
        if self.game is None or self.game.won or self.game.dead:
            return
        act = _KEY_ACTIONS.get(key, E.ACT_NONE)
        r: TickResult = self.game.tick(act)
        if r.gold_collected:
            self._flash(f"+ gold  ({self.game.gold_left()} left)")
        elif r.won:
            self._flash("★ level complete")
        elif r.dead:
            self._flash(f"✗ {r.reason}")
        if self.board:
            self.board.refresh()
        if self.status_panel:
            self.status_panel.refresh_panel()
        if r.won:
            self._on_win()
        elif r.dead:
            self._on_lose(r.reason)

    def action_undo(self) -> None:
        if self.game and self.game.undo():
            self._flash(f"undo — tick {self.game.tick_count}")
            if self.board:
                self.board.refresh()
            if self.status_panel:
                self.status_panel.refresh_panel()

    def action_reset(self) -> None:
        if self.game is None:
            return
        self._load_current()
        if self.message_log:
            self.message_log.write("[rgb(220,180,90)]↺ reset[/]")

    def action_next_level(self) -> None:
        if self.level_idx + 1 < len(self.pack):
            self.level_idx += 1
            self._load_current()
        else:
            self._flash(f"end of pack ({self.pack.display})")

    def action_prev_level(self) -> None:
        if self.level_idx > 0:
            self.level_idx -= 1
            self._load_current()
        else:
            self._flash(f"start of pack ({self.pack.display})")

    def action_select_level(self) -> None:
        self.push_screen(LevelSelectScreen(PACKS, self.pack, self.level_idx))

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    # ---- win / lose ------------------------------------------------

    def _on_win(self) -> None:
        if self.game is None:
            return
        if self.message_log:
            self.message_log.write(
                f"[bold rgb(120,230,120)]★ WON[/] — "
                f"{self.game.tick_count} ticks"
            )
        self.push_screen(
            WonScreen(gold=self.game.total_gold,
                      ticks=self.game.tick_count,
                      has_next=self.level_idx + 1 < len(self.pack))
        )

    def _on_lose(self, reason: str) -> None:
        if self.message_log:
            self.message_log.write(
                f"[bold rgb(255,120,120)]✗ DEAD[/] — {reason}"
            )
        self.push_screen(LostScreen(reason=reason or "you died"))


def run(pack: str | None = None, level: int = 0) -> None:
    LodeRunnerApp(pack_name=pack, level_idx=level).run()
