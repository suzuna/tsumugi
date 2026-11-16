"""micro 風のステータスバー（反転表示の1行）。"""

from __future__ import annotations

from rich.text import Text
from textual.widget import Widget


class StatusBar(Widget):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        width: 1fr;
        /* 反転は CSS で付ける（カスタム CSS で text-style: none にして色を指定できるように） */
        text-style: reverse;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._left = ""

    def update_status(self, name: str, dirty: bool, row: int, col: int, newline: str) -> None:
        mark = " +" if dirty else ""
        eol = "dos" if newline == "\r\n" else "unix"
        self._left = f" {name}{mark} ({row + 1},{col + 1}) | {eol} | utf-8"
        self.refresh()

    def render(self) -> Text:
        right = "Ctrl-g for help "
        width = self.size.width
        pad = max(1, width - len(self._left) - len(right))
        text = Text(self._left + " " * pad + right, no_wrap=True)
        text.truncate(width)
        return text
