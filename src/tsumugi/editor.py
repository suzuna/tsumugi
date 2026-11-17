"""1ファイル分のバッファ。micro 風のキーバインドを持つ TextArea。"""

from __future__ import annotations

from itertools import count
from pathlib import Path

from textual.binding import Binding
from textual.widgets import TextArea
from textual.widgets.text_area import Document, Selection

_ids = count(1)

# notified_sig の初期値（まだ何も知らせていない）
_NOT_NOTIFIED = object()


def file_sig(path: Path) -> tuple[int, int] | None:
    """ディスク上のファイルの (mtime_ns, size)。なければ None。変わったかの判定に使う。"""
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


class Buffer(TextArea):
    """micro 風の操作をする編集バッファ。

    path が None のときは無題（未保存）バッファ。
    """

    # 選択範囲: ansi テーマの既定は「反転 + 文字色 ANSI 黒」で、反転すると
    # 背景色の文字が黒地に乗って読めない。文字色を既定に戻して反転だけにする。
    # DEFAULT_CSS に置くのは、ユーザーのカスタム CSS で上書きできるようにするため
    DEFAULT_CSS = """
    Buffer:ansi .text-area--selection {
        color: ansi_default;
        background: transparent;
        text-style: reverse;
    }
    """

    # TextArea のデフォルトのうち micro と食い違うものを上書きする
    BINDINGS = [
        Binding("ctrl+a", "select_all", "Select all", show=False),
        Binding("ctrl+e", "noop", show=False),
        Binding("ctrl+c", "copy", "Copy", show=False),
        Binding("ctrl+x", "cut", "Cut", show=False),
        Binding("ctrl+v", "paste", "Paste", show=False),
        Binding("ctrl+k", "cut_line", "Cut line", show=False),
        Binding("ctrl+d", "duplicate_line", "Duplicate line", show=False),
        Binding("ctrl+u", "noop", show=False),
        Binding("ctrl+w", "noop", show=False),
        Binding("alt+up", "move_line(-1)", "Move line up", show=False),
        Binding("alt+down", "move_line(1)", "Move line down", show=False),
    ]

    def __init__(
        self, text: str = "", path: Path | None = None, soft_wrap: bool = False
    ) -> None:
        super().__init__(
            text,
            id=f"buf-{next(_ids)}",
            soft_wrap=soft_wrap,
            tab_behavior="indent",
            show_line_numbers=True,
            highlight_cursor_line=True,
        )
        self.path = path
        # 改行が混ざったファイルは1種類の改行でつなぎ直されるので、生の text ではなく
        # self.text と比べる（開いた直後から編集中に見えないように）
        self.saved_text = self.text
        # 最後に読み書きしたときのディスク上のファイルの状態
        self.disk_sig: tuple[int, int] | None = None
        # 編集中に外で変わったと知らせ済みの状態（同じ変更を何度も知らせないため）
        self.notified_sig: object = _NOT_NOTIFIED

    # ---- 状態 ----

    @property
    def dirty(self) -> bool:
        return self.text != self.saved_text

    @property
    def display_name(self) -> str:
        return self.path.name if self.path else "No name"

    @property
    def is_pristine_empty(self) -> bool:
        """無題・空・未変更のバッファ（ファイルを開いたら置き換えてよいもの）。"""
        return self.path is None and self.text == "" and not self.dirty

    def save(self, path: Path | None = None) -> Path:
        if path is not None:
            self.path = path
        if self.path is None:
            raise ValueError("no file name")
        text = self.text
        # self.text は開いたときの改行コードでつながっているので、そのまま書く
        self.path.write_text(text, encoding="utf-8", newline="")
        self.saved_text = text
        self.disk_sig = file_sig(self.path)
        self.notified_sig = _NOT_NOTIFIED
        return self.path

    def reload_from_disk(self, text: str, sig: tuple[int, int] | None) -> None:
        """ディスクから読み直した内容に置き換える。undo で戻せ、カーソルは同じ位置に残す。

        改行コードが変わっていたら、replace では前の改行コードのまま残るので丸ごと読み直す
        （このときは undo の履歴が消える）。
        """
        row, col = self.cursor_location
        if Document(text).newline != self.document.newline:
            self.load_text(text)
        else:
            self.replace(text, self.document.start, self.document.end)
        row = min(row, self.document.line_count - 1)
        col = min(col, len(self.document.get_line(row)))
        self.move_cursor((row, col))
        self.saved_text = self.text
        self.disk_sig = sig
        self.notified_sig = _NOT_NOTIFIED

    # ---- micro 固有の動作 ----

    def action_noop(self) -> None:
        pass

    def _line_text_with_newline(self, row: int) -> str:
        line = self.document.get_line(row)
        return line + self.document.newline

    def action_copy(self) -> None:
        """選択があればそれを、なければ現在行をコピー（micro と同じ）。"""
        text = self.selected_text or self._line_text_with_newline(
            self.cursor_location[0]
        )
        self.app.copy_to_clipboard(text)
        self.app.show_message(
            "Copied selection" if self.selected_text else "Copied line"
        )

    def action_cut(self) -> None:
        if self.read_only:
            return
        if self.selection.is_empty:
            self.action_cut_line()
            return
        super().action_cut()

    def action_cut_line(self) -> None:
        """現在行を切り取ってクリップボードへ。"""
        if self.read_only:
            return
        row = self.cursor_location[0]
        text = self._line_text_with_newline(row)
        self.selection = Selection.cursor((row, 0))
        self.action_delete_line()
        self.app.copy_to_clipboard(text)

    def action_paste(self) -> None:
        if self.read_only:
            return
        text = self.app.read_clipboard()
        if not text:
            return
        if result := self.replace(text, *self.selection):
            self.move_cursor(result.end_location)

    def action_duplicate_line(self) -> None:
        if self.read_only:
            return
        if not self.selection.is_empty:
            start, end = sorted(self.selection)
            text = self.get_text_range(start, end)
            self.insert(text, end)
            return
        row, col = self.cursor_location
        line = self.document.get_line(row)
        self.insert(self.document.newline + line, (row, len(line)))
        self.move_cursor((row + 1, col))

    def action_move_line(self, direction: int) -> None:
        if self.read_only:
            return
        row, col = self.cursor_location
        target = row + direction
        if not 0 <= target < self.document.line_count:
            return
        lines = [self.document.get_line(row), self.document.get_line(target)]
        top = min(row, target)
        bottom = max(row, target)
        start = (top, 0)
        end = (bottom, len(self.document.get_line(bottom)))
        if direction < 0:
            new = lines[0] + self.document.newline + lines[1]
        else:
            new = lines[1] + self.document.newline + lines[0]
        self.replace(new, start, end)
        self.move_cursor((target, col))

    # ---- 検索 ----

    def find(self, needle: str, start: tuple[int, int], forward: bool = True) -> bool:
        """start から needle を探して選択する。見つからなければ False。末尾で折り返す。"""
        if not needle:
            return False
        lines = self.document.lines
        n = len(lines)
        srow, scol = start
        if forward:
            order = [(srow, scol)] + [((srow + i) % n, 0) for i in range(1, n + 1)]
            for row, col in order:
                idx = lines[row].find(needle, col)
                if idx >= 0:
                    self._select_match(row, idx, needle)
                    return True
        else:
            order = [(srow, scol)] + [((srow - i) % n, None) for i in range(1, n + 1)]
            for row, col in order:
                line = lines[row]
                end = len(line) if col is None else col
                idx = line.rfind(needle, 0, end)
                if idx >= 0:
                    self._select_match(row, idx, needle)
                    return True
        return False

    def _select_match(self, row: int, col: int, needle: str) -> None:
        self.selection = Selection((row, col), (row, col + len(needle)))
        self.scroll_cursor_visible(center=True)
