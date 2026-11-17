"""Ctrl+G で開くキーバインド一覧。"""

from __future__ import annotations

from rich.text import Text
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
            ("Ctrl+O", "Open directory"),
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
            ("Ctrl+R", "Replace"),
        ],
    ),
    (
        "Explorer",
        [
            ("Enter", "Open file / expand directory"),
            ("Right", "Expand directory"),
            ("Left", "Collapse directory / go to parent"),
            ("o", "Open directory under cursor"),
            ("Backspace", "Open parent directory"),
            (".", "Toggle hidden files"),
            ("s", "Toggle name order (asc / desc)"),
            ("r / F2", "Rename (sidebar only)"),
            ("d", "Move to trash (sidebar only)"),
            ("m", "New directory (sidebar only)"),
            ("Esc", "Close"),
        ],
    ),
]


NOTE = (
    "(*) only with TEXTUAL_DISABLE_KITTY_KEY=0 in terminals that support"
    " the kitty keyboard protocol"
)


class HelpText(Static):
    """キーの一覧。キーの列の色は component class で付ける（カスタム CSS で変えられるように）。"""

    COMPONENT_CLASSES = {"help--key"}

    DEFAULT_CSS = """
    HelpText > .help--key {
        color: $accent;
    }
    """

    def render(self) -> Text:
        key_style = self.get_component_rich_style("help--key", partial=True)
        text = Text()
        for section, rows in KEYS:
            text.append(section, style="bold")
            text.append("\n")
            for key, desc in rows:
                text.append("  ")
                text.append(f"{key:<20}", style=key_style)
                text.append(f" {desc}\n")
            text.append("\n")
        text.append(NOTE)
        return text


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
            yield HelpText()

    def action_close(self) -> None:
        self.dismiss(None)
