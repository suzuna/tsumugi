"""micro 風のステータスバー（反転表示の1行）。"""

from __future__ import annotations

from pathlib import Path

from rich.cells import cell_len
from rich.text import Text
from textual.widget import Widget

from .explorer import display_path, truncate_left


def status_path(path: Path | None, cwd: Path) -> str:
    """ステータスバーに出すパス。cwd の下なら相対パス、外なら ~/...（ホームの外は絶対パス）。"""
    if path is None:
        return "No name"
    try:
        return str(path.relative_to(cwd))
    except ValueError:
        return display_path(path)


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
        self._path = ""
        self._info = ""

    def update_status(
        self, path: str, dirty: bool, row: int, col: int, newline: str
    ) -> None:
        mark = " +" if dirty else ""
        eol = "dos" if newline == "\r\n" else "unix"
        self._path = path
        self._info = f"{mark} ({row + 1},{col + 1}) | {eol} | utf-8"
        self.refresh()

    def render(self) -> Text:
        width = self.size.width
        fixed = 1 + cell_len(self._info)  # 先頭の空白 + パス以外
        # 幅が足りなければパスの頭を … にして、ファイル名や行と列は残す
        path = truncate_left(self._path, max(width - fixed, 0))
        text = Text(" " + path + self._info, no_wrap=True)
        text.truncate(width)
        return text
