"""1ファイル分のバッファ。micro 風のキーバインドを持つ TextArea。"""

from __future__ import annotations

from itertools import count
from pathlib import Path

from textual import events
from textual.binding import Binding
from textual.widgets import TextArea
from textual.widgets.text_area import Document, Selection
from tree_sitter import Language

from .syntax import detect_language, is_builtin, load_language

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
        self,
        text: str = "",
        path: Path | None = None,
        soft_wrap: bool = False,
        max_lines: int = 3000,
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
        # これより行数が多いファイルはハイライトしない（0 なら常にしない）
        self.max_lines = max_lines

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
        self.update_language()

    def moved_copy(self) -> Buffer:
        """別のペインへ移すための作り直し。中身・保存の状態・undo の履歴・選択範囲を引き継ぐ。

        Textual では mount 済みのウィジェットを別の親へ付け替えられないので、新しく作って
        元のほうを外す。undo の履歴（Edit）は適用先の TextArea を引数で受け取る作りなので、
        そのまま渡せる。
        """
        new = Buffer(
            self.text, self.path, soft_wrap=self.soft_wrap, max_lines=self.max_lines
        )
        new.saved_text = self.saved_text
        new.disk_sig = self.disk_sig
        new.notified_sig = self.notified_sig
        new.history = self.history
        new._restore_selection = self.selection
        return new

    _restore_selection: Selection | None = None

    def on_mount(self) -> None:
        # 言語を変えるとカーソルが先頭に戻るので、選択範囲を戻す前に決める。
        # on_mount の中ではまだ is_mounted が False なので、自分のフラグで見る
        self._language_ready = True
        self.update_language()
        if self._restore_selection is not None:
            self.selection = self._restore_selection
            self._restore_selection = None
            self.call_after_refresh(self.scroll_cursor_visible)

    # ---- シンタックスハイライト ----

    def update_language(self) -> None:
        """パスと行数からハイライトの言語を決め直す。

        開いたとき・ディスクから読み直したとき・名前が変わったときに呼ぶ。編集中は呼ばない
        （行数が上限をまたぐたびに色が付いたり消えたりしないように）。
        """
        if not self._language_ready:
            return  # on_mount で決める
        name = None
        if 0 < self.max_lines and self.document.line_count <= self.max_lines:
            name = detect_language(self.path, self.document.get_line(0))
        self._pending_language = None
        if name is None or is_builtin(name) or name in self._languages:
            self._set_language(name)
            return
        # language-pack の文法は初回にダウンロードするので、画面を止めないようスレッドで取る。
        # 取れるまではハイライトなしにしておく
        self._set_language(None)
        self._pending_language = name
        self.run_worker(
            lambda: self._load_language(name),
            thread=True,
            group="syntax",
            exclusive=True,
        )

    # マウントして、言語を決めてよくなったか
    _language_ready = False
    # language-pack から取っている途中の言語
    _pending_language: str | None = None

    def _load_language(self, name: str) -> None:
        loaded = load_language(name)
        self.app.call_from_thread(self._apply_loaded, name, loaded)

    def _apply_loaded(self, name: str, loaded: tuple[Language, str] | None) -> None:
        if not self.is_mounted or self._pending_language != name:
            return  # 取っている間に閉じたか、名前が変わって別の言語になった
        self._pending_language = None
        if loaded is None:
            self.app.show_message(f"Cannot load syntax for {name}")
            return
        self.register_language(name, *loaded)
        self._set_language(name)

    def _set_language(self, name: str | None) -> None:
        """言語を切り替える。TextArea は切り替えると先頭へ戻るので、位置を戻す。"""
        if self.language == name:
            return
        selection = self.selection
        scroll = self.scroll_offset
        self.language = name
        self.selection = selection
        self.scroll_to(scroll.x, scroll.y, animate=False, immediate=True)

    # ---- micro 固有の動作 ----

    def action_noop(self) -> None:
        pass

    async def _on_key(self, event: events.Key) -> None:
        # Enter は TextArea._on_key の中で "\n" を入れているので、Binding では届かない
        if event.key == "enter" and not self.read_only:
            event.stop()
            event.prevent_default()
            self._newline_with_indent()
            return
        await super()._on_key(event)

    def _newline_with_indent(self) -> None:
        """改行して、今の行の先頭の空白を新しい行に引き継ぐ。

        改行したあと今の行が空白だけになるなら、その空白は消す（空行に空白を残さない）。
        """
        start, end = sorted(self.selection)
        row, col = start
        line = self.document.get_line(row)
        indent = line[: len(line) - len(line.lstrip(" \t"))]
        # インデントの途中にカーソルがあるときは、カーソルより左の分だけ引き継ぐ
        indent = indent[:col]
        end_line = self.document.get_line(end[0])
        if not line[:col].strip() and not end_line[end[1] :].strip():
            start = (row, 0)
            end = (end[0], len(end_line))
        # 1回の edit にまとめて、undo 1回で戻るようにする
        self.replace("\n" + indent, start, end, maintain_selection_offset=False)

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

    # ---- 置換 ----
    # 置換は本文の文字列での位置（index）で扱う。探す文字列は改行を含まない

    def index_of(self, location: tuple[int, int]) -> int:
        return self.document.get_index_from_location(location)

    def location_of(self, index: int) -> tuple[int, int]:
        return self.document.get_location_from_index(index)

    def find_index(self, needle: str, start: int, limit: int) -> int | None:
        """start 以降で最初の needle の位置。limit 以降から始まるものは見ない。折り返さない。"""
        idx = self.text.find(needle, start)
        return idx if 0 <= idx < limit else None

    def select_index(self, index: int, length: int) -> None:
        self.selection = Selection(
            self.location_of(index), self.location_of(index + length)
        )
        self.scroll_cursor_visible(center=True)

    def replace_index(self, index: int, length: int, text: str) -> None:
        """index から length 文字を text に置き換える。1回の undo で戻る単位にする。"""
        self.history.checkpoint()
        self.replace(text, self.location_of(index), self.location_of(index + length))
        self.history.checkpoint()
