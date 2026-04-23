"""Modal screens: Help, LevelSelect, Won, Lost."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

if TYPE_CHECKING:
    from .app import LodeRunnerApp


class HelpScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "close"),
        Binding("question_mark", "app.pop_screen", "close"),
        Binding("q", "app.pop_screen", "close"),
    ]

    def compose(self) -> ComposeResult:
        t = Text()
        t.append("Lode Runner TUI — Controls\n\n", style="bold rgb(255,220,80)")
        rows = [
            ("Move left",       "←  /  h  /  a"),
            ("Move right",      "→  /  l  /  d"),
            ("Climb up",        "↑  /  k  /  w"),
            ("Climb / drop",    "↓  /  j  /  s"),
            ("Dig left",        "z  /  ,"),
            ("Dig right",       "x  /  ."),
            ("Wait / stop",     "space"),
            ("Undo",            "u"),
            ("Reset level",     "r"),
            ("Next / prev",     "n / p"),
            ("Level select",    "L"),
            ("Quit",            "q"),
        ]
        for desc, keys in rows:
            t.append(f"  {desc:<18}", style="rgb(200,200,220)")
            t.append(f"{keys}\n", style="bold rgb(255,255,255)")
        t.append("\nGlyphs\n", style="bold rgb(180,200,240)")
        t.append("  ☺ runner   Ж guard   ★ guard w/ gold\n",
                 style="rgb(220,220,235)")
        t.append("  ¤ gold     ▓ brick   █ solid (concrete)\n",
                 style="rgb(220,220,235)")
        t.append("  ╫ ladder   ─ rope    ░ trap\n", style="rgb(220,220,235)")
        t.append("\nCollect all gold, then climb to the top row.\n",
                 style="rgb(200,200,220)")
        t.append("Dig bricks to trap guards — but holes refill!\n",
                 style="rgb(200,200,220)")
        t.append("\nesc / ? to close", style="rgb(150,150,170)")
        yield Vertical(Static(t), id="help-panel")


class WonScreen(ModalScreen):
    BINDINGS = [
        Binding("n", "next", "next level"),
        Binding("r", "retry", "retry"),
        Binding("L", "select", "level select"),
        Binding("escape", "close", "back"),
    ]

    def __init__(self, gold: int, ticks: int, has_next: bool) -> None:
        super().__init__()
        self.gold = gold
        self.ticks = ticks
        self.has_next = has_next

    def compose(self) -> ComposeResult:
        t = Text()
        t.append("★ LEVEL COMPLETE ★\n\n", style="bold rgb(255,220,80)")
        t.append(f"{self.gold} gold   {self.ticks} ticks\n\n",
                 style="bold rgb(230,230,240)")
        nxt = "n next · " if self.has_next else ""
        t.append(f"{nxt}r retry · L levels · esc",
                 style="rgb(180,200,240)")
        yield Vertical(Static(t), id="won-panel")

    def _lr_app(self) -> "LodeRunnerApp":
        from .app import LodeRunnerApp
        return cast(LodeRunnerApp, self.app)

    def action_next(self) -> None:
        a = self._lr_app()
        if self.has_next:
            a.pop_screen()
            a.action_next_level()

    def action_retry(self) -> None:
        a = self._lr_app()
        a.pop_screen()
        a.action_reset()

    def action_select(self) -> None:
        a = self._lr_app()
        a.pop_screen()
        a.action_select_level()

    def action_close(self) -> None:
        self.app.pop_screen()


class LostScreen(ModalScreen):
    BINDINGS = [
        Binding("r", "retry", "retry"),
        Binding("L", "select", "level select"),
        Binding("escape", "close", "back"),
    ]

    def __init__(self, reason: str) -> None:
        super().__init__()
        self.reason = reason

    def compose(self) -> ComposeResult:
        t = Text()
        t.append("✗ RUNNER DOWN ✗\n\n", style="bold rgb(255,120,120)")
        t.append(f"{self.reason}\n\n", style="rgb(230,230,240)")
        t.append("r retry · L levels · esc", style="rgb(180,200,240)")
        yield Vertical(Static(t), id="lost-panel")

    def _lr_app(self) -> "LodeRunnerApp":
        from .app import LodeRunnerApp
        return cast(LodeRunnerApp, self.app)

    def action_retry(self) -> None:
        a = self._lr_app()
        a.pop_screen()
        a.action_reset()

    def action_select(self) -> None:
        a = self._lr_app()
        a.pop_screen()
        a.action_select_level()

    def action_close(self) -> None:
        self.app.pop_screen()


class LevelSelectScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "close"),
        Binding("q", "app.pop_screen", "close"),
    ]

    def __init__(self, packs, current_pack, current_idx: int) -> None:
        super().__init__()
        self._packs = packs
        self._current_pack = current_pack
        self._current_idx = current_idx

    def compose(self) -> ComposeResult:
        options: list[Option] = []
        initial_highlight = 0
        for p in self._packs:
            options.append(
                Option(
                    Text(f"━━ {p.display} ━━  ({len(p)} levels)",
                         style="bold rgb(180,200,240)"),
                    id=f"hdr:{p.name}",
                    disabled=True,
                )
            )
            for i in range(len(p)):
                label = Text()
                label.append(f"  {p.name} #{i + 1:>3}",
                             style="rgb(220,220,235)")
                lvl = p[i]
                if lvl.title and lvl.title != f"{p.display} #{i + 1}":
                    label.append(f"  {lvl.title}", style="rgb(150,150,170)")
                options.append(Option(label, id=f"lvl:{p.name}:{i}"))
                if p is self._current_pack and i == self._current_idx:
                    initial_highlight = len(options) - 1
        ol = OptionList(*options, id="level-list")
        self._ol = ol
        self._initial_highlight = initial_highlight
        hint = Static(
            Text("enter select · esc close", style="rgb(150,150,170)")
        )
        yield Vertical(ol, hint, id="select-panel")

    def on_mount(self) -> None:
        try:
            self._ol.highlighted = self._initial_highlight
        except Exception:
            pass
        self._ol.focus()

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        opt_id = event.option.id or ""
        if not opt_id.startswith("lvl:"):
            return
        _, pack_name, idx_s = opt_id.split(":")
        idx = int(idx_s)
        pack = next(p for p in self._packs if p.name == pack_name)
        from .app import LodeRunnerApp
        a = cast(LodeRunnerApp, self.app)
        a.pop_screen()
        a.load_level(pack, idx)
