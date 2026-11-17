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
        self._mark = ""
        self._right = ""

    def update_status(
        self, path: str, dirty: bool, row: int, col: int, newline: str
    ) -> None:
        eol = {"\r\n": "dos", "\r": "mac"}.get(newline, "unix")
        self._path = path
        self._mark = " +" if dirty else ""
        # 左の先頭の空白とそろうよう、右端にも空白を1つ置く
        self._right = f"({row + 1},{col + 1}) | {eol} | utf-8 "
        self.refresh()

    def render(self) -> Text:
        # パスと編集中の印は左、行と列・改行コード・文字コードは右端に寄せる
        width = self.size.width
        # 先頭の空白 + 印 + 右側 + 左右の間の最低1マス を除いた幅がパスに使える
        budget = width - 1 - cell_len(self._mark) - cell_len(self._right) - 1
        # 幅が足りなければパスの頭を … にして、ファイル名と右側は残す
        left = " " + truncate_left(self._path, max(budget, 0)) + self._mark
        pad = max(1, width - cell_len(left) - cell_len(self._right))
        text = Text(left + " " * pad + self._right, no_wrap=True)
        text.truncate(width)
        return text
