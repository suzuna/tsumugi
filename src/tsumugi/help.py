"""Ctrl+G で開くキーバインド一覧。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

KEYS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "File",
        [
            ("Ctrl+S", "Save"),
            ("Ctrl+Q", "Close tab (quit when last)"),
            ("Ctrl+B", "Open file explorer"),
            ("Ctrl+E", "Toggle sidebar tree"),
            ("Ctrl+W", "Switch sidebar / editor"),
            ("Ctrl+T", "New tab"),
            ("Ctrl+PgUp / PgDn", "Previous / next tab"),
            ("Alt+, / Alt+.", "Previous / next tab (*)"),
        ],
    ),
    (
        "Edit",
        [
            ("Ctrl+Z / Ctrl+Y", "Undo / redo"),
            ("Ctrl+C", "Copy (line if no selection)"),
            ("Ctrl+X", "Cut (line if no selection)"),
            ("Ctrl+V", "Paste"),
            ("Ctrl+K", "Cut line"),
            ("Ctrl+D", "Duplicate line"),
            ("Alt+Up / Alt+Down", "Move line up / down"),
            ("Ctrl+A", "Select all"),
            ("Shift+Arrows", "Select"),
        ],
    ),
    (
        "Search",
        [
            ("Ctrl+F", "Find"),
            ("Ctrl+N / Ctrl+P", "Find next / previous"),
        ],
    ),
    (
        "Explorer",
        [
            ("Enter", "Open file / expand directory"),
            ("Backspace", "Go to parent directory"),
            (".", "Toggle hidden files"),
            ("Esc", "Close"),
        ],
    ),
]


def _help_text() -> str:
    out: list[str] = []
    for section, rows in KEYS:
        out.append(f"[b]{section}[/b]")
        for key, desc in rows:
            out.append(f"  [$accent]{key:<20}[/] {desc}")
        out.append("")
    out.append("(*) only in terminals that support the kitty keyboard protocol")
    return "\n".join(out).rstrip()


class HelpScreen(ModalScreen[None]):
    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen > VerticalScroll {
        width: 60;
        max-width: 90%;
        height: auto;
        max-height: 85%;
        border: round $accent;
        border-title-align: left;
        border-subtitle-align: right;
        background: $surface;
        padding: 0 1;
    }
    """

    BINDINGS = [Binding("escape,ctrl+g,ctrl+q,q", "close", show=False)]

    def compose(self) -> ComposeResult:
        with VerticalScroll() as box:
            box.border_title = "tsumugi help"
            box.border_subtitle = "Esc: close"
            yield Static(_help_text())

    def action_close(self) -> None:
        self.dismiss(None)
