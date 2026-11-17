"""tsumugi のアプリ本体。"""

from __future__ import annotations

import asyncio
import inspect
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import TextIO

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.theme import BUILTIN_THEMES, Theme
from textual.widget import Widget
from textual.widgets import DirectoryTree, TextArea

from .config import Config, load_config
from .editor import Buffer, file_sig
from .explorer import ExplorerPanel, ExplorerScreen, display_path, truncate_left
from .finder import FinderScreen
from .help import HelpScreen
from .panes import Pane
from .prompt import InfoBar
from .resize import EDITOR_MIN_WIDTH, SIDEBAR_MIN_WIDTH, EdgeDrag, clamp
from .scrollbar import install as install_scrollbar
from .statusbar import StatusBar, status_path
from .tabs import TabBar

# プロンプト入力中でも有効なアクション
_ALLOWED_WHILE_PROMPTING = {"find_next", "find_prev"}

# 開いているファイルがディスク上で変わっていないか見る間隔（秒）
DISK_CHECK_INTERVAL = 0.5


class AfterInput(Message):
    """先に届いたキーを処理し終えてから callback を実行するためのメッセージ。

    フォーカス中のウィジェットに積むと、先に積まれたキーと同じ道（ウィジェット → 親 →
    … → Screen → App）をたどって App に届く。キーのバインディング（矢印・Backspace など）は
    App まで上がってから実行されるので、App で受け取れば必ずそのあとになる。
    """

    def __init__(self, callback) -> None:
        super().__init__()
        self.callback = callback
        # Textual は送り主（作ったときに処理中だったウィジェット）を覚えていて、送り主が親に
        # いるとその親で伝わるのを止める。EditorScreen の中（タブのドロップなど）で作っても
        # App まで届くように、送り主を持たせない
        self._sender = None


class Sidebar(EdgeDrag, Vertical):
    """サイドバーの入れ物。右の区切り線をドラッグして幅を変えられる。"""

    def is_edge(self, screen_x: int, screen_y: int) -> bool:
        region, content = self.region, self.content_region
        return screen_x == region.right - 1 and content.right < region.right

    def on_edge_drag(self, screen_x: int, screen_y: int) -> None:
        parent = self.parent
        if not isinstance(parent, Widget):
            return
        # 区切り線がマウスの位置に来る幅
        width = screen_x - self.region.x + 1
        limit = parent.content_region.width - EDITOR_MIN_WIDTH
        self.styles.width = clamp(width, SIDEBAR_MIN_WIDTH, limit)


class EditorScreen(Screen[None]):
    DEFAULT_CSS = """
    EditorScreen {
        layout: vertical;
    }
    EditorScreen > #main {
        height: 1fr;
    }
    EditorScreen #sidebar {
        display: none;
        width: 30;
        height: 1fr;
        border-right: vkey $foreground 30%;
    }
    EditorScreen #sidebar.-visible {
        display: block;
    }
    /* ツリーにフォーカスがあるときは、見出しの帯に色を付ける（TabBar.-focused と同じ色）。
       :focus-within だと中の RootPath のスタイルが描き直されないので、クラスで切り替える */
    EditorScreen #sidebar.-focused RootPath {
        background: ansi_bright_black;
        /* 既定のくすんだ文字色（$text-muted）だとグレーの帯の上で読みにくい */
        color: ansi_default;
    }
    EditorScreen #editor-area {
        width: 1fr;
        height: 1fr;
        layout: horizontal;
    }
    /* 上下に分割 */
    EditorScreen #editor-area.-vertical {
        layout: vertical;
    }
    EditorScreen Pane.-second {
        border-left: vkey $foreground 30%;
    }
    EditorScreen #editor-area.-vertical > Pane.-second {
        border-left: none;
        border-top: hkey $foreground 30%;
    }
    EditorScreen Buffer {
        height: 1fr;
        border: none;
        /* 行番号が左端やサイドバーの区切り線にくっつかないよう左に1マス空ける */
        padding: 0 0 0 1;
        background: $background;
    }
    EditorScreen Buffer:focus {
        border: none;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "Save", priority=True),
        Binding("ctrl+w", "close_tab", "Close tab", priority=True),
        Binding("ctrl+q", "quit_all", "Quit", priority=True),
        Binding("ctrl+b", "explorer", "Explorer", priority=True),
        Binding("ctrl+t", "new_tab", "New tab", priority=True),
        Binding("alt+comma,ctrl+pageup", "prev_tab", "Previous tab", priority=True),
        Binding("alt+full_stop,ctrl+pagedown", "next_tab", "Next tab", priority=True),
        Binding("ctrl+f", "find", "Find", priority=True),
        Binding("ctrl+n", "find_next", "Find next", priority=True),
        Binding("ctrl+p", "find_prev", "Find previous", priority=True),
        Binding("ctrl+r", "replace", "Replace", priority=True),
        Binding("ctrl+g", "help", "Help", priority=True),
        Binding("ctrl+e", "toggle_sidebar", "Sidebar", priority=True),
        Binding("ctrl+j", "focus_tree", "Tree / pane", priority=True),
        Binding("ctrl+u", "switch_pane", "Switch pane", priority=True),
        Binding("ctrl+o", "quick_open", "Open file", priority=True),
        Binding("ctrl+backslash", "toggle_split", "Split", priority=True),
        Binding("ctrl+right_square_bracket", "move_tab", "Move tab", priority=True),
    ]

    def __init__(self, files: list[Path], config: Config) -> None:
        super().__init__()
        self._initial_files = files
        self._config = config
        # 最後にフォーカスがあったペイン（サイドバーから開くときの開き先）
        self._active_pane: Pane | None = None
        # 分割の切り替えやタブの移動を1つずつ順に行うためのロック
        self._layout_lock = asyncio.Lock()
        self.last_search = ""
        # ステータスバーのパスはここからの相対パスで出す
        self.cwd = Path.cwd().resolve()
        # ツリーの起点は起動したディレクトリ（`tsumugi <dir>` なら main で chdir 済み）
        self.explorer_root = self.cwd
        self.explorer_show_hidden = False
        self.explorer_sort_desc = config.tree_sort == "desc"

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            # サイドバーの中身（ツリー）は最初に表示したときに作る
            yield Sidebar(id="sidebar")
            with Container(id="editor-area"):
                yield Pane(self._config.hide_single_tab)
        yield StatusBar()
        yield InfoBar()

    async def on_mount(self) -> None:
        for path in self._initial_files:
            await self.open_path(path)
        if not self.buffers:
            await self.add_buffer(self._new_buffer())
        if self._config.sidebar:
            await self.action_toggle_sidebar()
            # ファイル指定で起動したらすぐ書けるようにエディタへ。なしならツリーから選ぶ
            if self._initial_files:
                self.app.focus_editor()
        if self._config.warnings:
            self.message(self._config.warnings[0])
        self.set_interval(DISK_CHECK_INTERVAL, self._check_disk)

    # ---- 便利プロパティ ----

    @property
    def infobar(self) -> InfoBar:
        return self.query_one(InfoBar)

    @property
    def editor_area(self) -> Container:
        return self.query_one("#editor-area", Container)

    @property
    def panes(self) -> list[Pane]:
        return [w for w in self.editor_area.children if isinstance(w, Pane)]

    @property
    def active_pane(self) -> Pane:
        panes = self.panes
        if self._active_pane in panes:
            return self._active_pane
        return panes[0]

    @property
    def buffers(self) -> list[Buffer]:
        """全ペインのバッファ（左 / 上のペインから順に）。"""
        return [b for pane in self.panes for b in pane.buffers]

    @property
    def current(self) -> Buffer | None:
        return self.active_pane.current

    def pane_of(self, buf: Buffer) -> Pane:
        for pane in self.panes:
            if buf in pane.buffers:
                return pane
        raise LookupError(f"{buf!r} is not in any pane")

    @property
    def split(self) -> str | None:
        """分割の向き。"horizontal"（左右）/ "vertical"（上下）、分割していなければ None。"""
        if len(self.panes) < 2:
            return None
        return "vertical" if self.editor_area.has_class("-vertical") else "horizontal"

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if (
            self.is_mounted
            and self.infobar.active
            and action not in _ALLOWED_WHILE_PROMPTING
        ):
            return False
        return True

    def message(self, text: str) -> None:
        self.infobar.show_message(text)

    # ---- バッファ・タブ管理 ----

    def _new_buffer(self, text: str = "", path: Path | None = None) -> Buffer:
        return Buffer(
            text,
            path,
            soft_wrap=self._config.soft_wrap,
            max_lines=self._config.highlight_max_lines,
        )

    async def add_buffer(self, buf: Buffer, focus: bool = True) -> None:
        """バッファを今のペインのタブの末尾に加えて表示する。"""
        await self.active_pane.insert(buf)
        self.switch_to(buf, focus)

    def switch_to(self, buf: Buffer, focus: bool = True) -> None:
        """buf のあるペインで buf を表示し、そのペインを今のペインにする。"""
        pane = self.pane_of(buf)
        pane.show(buf)
        self._active_pane = pane
        if focus:
            buf.focus()
        self.refresh_bars()

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        # クリックや Ctrl+W でエディタにフォーカスが来たら、そのペインを今のペインにする
        for node in event.widget.ancestors_with_self:
            if isinstance(node, Pane):
                self._active_pane = node
                break
        # ツリーとエディタの間でフォーカスが移ったときも、タブバーの色を描き直す
        self.refresh_bars()

    def _sidebar_focused(self) -> bool:
        focused = self.focused
        return focused is not None and self.sidebar in focused.ancestors_with_self

    def refresh_bars(self) -> None:
        # ツリーにフォーカスがある間は、どのペインのタブバーも操作中の色にしない
        active = self.active_pane
        tree_focused = self._sidebar_focused()
        self.sidebar.set_class(tree_focused, "-focused")
        for pane in self.panes:
            pane.refresh_tabs(pane is active and not tree_focused)
        buf = active.current
        if buf is not None:
            row, col = buf.cursor_location
            self.query_one(StatusBar).update_status(
                status_path(buf.path, self.cwd),
                buf.dirty,
                row,
                col,
                buf.document.newline,
            )

    async def open_path(self, path: Path) -> None:
        """ファイルを開いて、そのタブにフォーカスを移す。"""
        path = path.expanduser().resolve()
        for buf in self.buffers:
            if buf.path == path:
                self.switch_to(buf)
                return
        if path.is_dir():
            self.message(f"{path} is a directory")
            return
        # 読む前に状態を取る（読んでいる間に変わったら、次の確認で読み直される）
        sig = file_sig(path)
        if path.exists():
            try:
                # newline="" で改行コード（LF / CRLF / CR）を変えずに読む
                text = path.read_text(encoding="utf-8", newline="")
            except UnicodeDecodeError:
                self.message(f"Cannot open {path.name}: not a UTF-8 text file")
                return
            except OSError as e:
                self.message(f"Cannot open {path.name}: {e.strerror}")
                return
        else:
            text = ""  # micro と同じく、存在しないファイルは新規として開く

        pane = self.active_pane
        cur = pane.current
        new = self._new_buffer(text, path)
        new.disk_sig = sig
        if cur is not None and cur.is_pristine_empty:
            # 空の無題バッファは置き換える
            await pane.replace(cur, new)
            self.switch_to(new)
        else:
            await self.add_buffer(new)
        if not path.exists():
            self.message(f"New file: {path}")

    async def close_buffer(self, buf: Buffer) -> None:
        pane = self.pane_of(buf)
        await pane.remove_buffer(buf)
        if pane.buffers:
            self.switch_to(pane.current or pane.buffers[0])
            return
        if len(self.panes) == 1:
            # 最後のタブを閉じても終了はしない（終了は Ctrl+Q）。空の無題バッファを残す
            await self.add_buffer(self._new_buffer())
            return
        # 分割していてペインが空になったら、分割をやめて残ったペインへ
        await self._close_empty_pane(pane)
        rest = self.active_pane
        self.switch_to(rest.current or rest.buffers[0])

    def on_tab_bar_clicked(self, event: TabBar.Clicked) -> None:
        pane = event.bar.parent
        if isinstance(pane, Pane) and 0 <= event.index < len(pane.buffers):
            self.switch_to(pane.buffers[event.index])

    def on_tab_bar_dropped(self, event: TabBar.Dropped) -> None:
        """タブのドラッグ & ドロップ。同じタブバーなら並べ替え、隣のペインならそこへ移す。"""
        src = event.bar.parent
        if not isinstance(src, Pane) or not 0 <= event.index < len(src.buffers):
            return
        buf = src.buffers[event.index]
        dst = next(
            (n for n in event.target.ancestors_with_self if isinstance(n, Pane)), None
        )
        if dst is None:
            return
        if dst is src:
            # 自分のペインのエディタ部分に落としたときは何もしない
            if event.target_index is not None:
                src.move_tab(buf, event.target_index)
                self.switch_to(buf)
            return
        self._after_pending_input(
            lambda: self._drop_to_pane(buf, dst, event.target_index)
        )

    async def _drop_to_pane(self, buf: Buffer, dst: Pane, index: int | None) -> None:
        async with self._layout_lock:
            # 待っている間に閉じたり分割をやめたりしていたら何もしない
            if buf not in self.buffers or dst not in self.panes:
                return
            await self.move_buffer(buf, dst, index)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self.refresh_bars()

    def on_text_area_selection_changed(self, event: TextArea.SelectionChanged) -> None:
        self.refresh_bars()

    # ---- アクション ----

    def _after_pending_input(self, callback) -> None:
        """フォーカス中のウィジェットに先に届いたキーを処理してから callback を実行する。

        priority のバインディングはキーが届いた時点ですぐ動くが、ふつうのキーは
        フォーカス中のウィジェットのキューに積まれてあとで処理される。文字と Ctrl+S が
        一度に届いたとき、文字が入る前に保存しないよう、キーと同じ道で後ろに回す。
        """
        target = self.app.focused
        if target is None:
            result = callback()
            if inspect.isawaitable(result):
                self.run_worker(result)
        else:
            target.post_message(AfterInput(callback))

    def action_save(self) -> None:
        self._after_pending_input(self._save)

    def _save(self, then=None) -> None:
        buf = self.current
        if buf is None:
            return
        if buf.path is None:
            # 相対パスは、ツリーで最後に見ていたフォルダ（サイドバーとオーバーレイで共有）から数える
            base = self.explorer_root

            def on_name(name: str) -> None:
                if not name.strip():
                    self.message("Save cancelled")
                    return
                target = Path(name.strip()).expanduser()
                if not target.is_absolute():
                    target = base / target
                target = target.resolve()
                if target.exists() and target != buf.path:
                    self._confirm_overwrite(buf, target, then)
                    return
                self._do_save(buf, target, then)

            # どこに保存されるかわかるよう、基準のフォルダをプロンプトに出す
            where = truncate_left(display_path(base).rstrip("/") + "/", 30)
            self.infobar.ask(
                f"Filename ({where}): ",
                on_name,
                on_cancel=lambda: self.message("Save cancelled"),
            )
            return
        self._do_save(buf, None, then)

    def _confirm_overwrite(self, buf: Buffer, target: Path, then=None) -> None:
        """名前を聞いて保存するとき、もうあるファイルなら上書きしていいか聞く（micro と同じ）。"""

        def on_answer(answer: str) -> None:
            if answer == "y":
                self._do_save(buf, target, then)
            else:
                self.message("Save cancelled")

        self.infobar.ask(
            f"{target.name} already exists, overwrite? (y,n,esc) ",
            on_answer,
            choices={"y", "n"},
            on_cancel=lambda: self.message("Save cancelled"),
        )

    def _do_save(
        self, buf: Buffer, path: Path | None, then=None, force: bool = False
    ) -> None:
        target = path if path is not None else buf.path
        if not force and target is not None and target == buf.path:
            # 開いたあとに外で書き換えられていたら、黙って上書きせずに聞く
            sig = file_sig(target)
            if sig is not None and sig != buf.disk_sig:
                self._confirm_overwrite_changed(buf, path, then)
                return
        created = False
        if target is not None and not target.parent.exists():
            # micro の mkparents と同じ: 設定が on のときだけ足りないフォルダを作る
            if not self._config.mkparents:
                self.message("Parent dirs don't exist, enable 'mkparents' in config")
                return
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                self.message(f"Error creating {target.parent}: {e.strerror}")
                return
            created = True
        old_path = buf.path
        try:
            saved = buf.save(path)
        except OSError as e:
            self.message(f"Error saving: {e.strerror}")
            return
        if buf.path != old_path:
            # 名前を付けて保存したら、新しい名前で言語を決め直す
            buf.update_language()
        self.message(f"Saved {saved}" + (" (created parent dirs)" if created else ""))
        self.refresh_bars()
        if then is not None:
            self.call_later(then)

    def _confirm_overwrite_changed(
        self, buf: Buffer, path: Path | None, then=None
    ) -> None:
        def on_answer(answer: str) -> None:
            if answer == "y":
                self._do_save(buf, path, then, force=True)
            else:
                self.message("Save cancelled")

        self.infobar.ask(
            f"{buf.display_name} changed on disk, overwrite? (y,n,esc) ",
            on_answer,
            choices={"y", "n"},
            on_cancel=lambda: self.message("Save cancelled"),
        )

    def _check_disk(self) -> None:
        """開いているファイルがディスク上で変わっていたら、読み直すか知らせる。"""
        if self.infobar.active:
            # プロンプト中はメッセージ欄が隠れているので、閉じてから見る
            return
        for buf in self.buffers:
            if buf.path is None:
                continue
            sig = file_sig(buf.path)
            if sig == buf.disk_sig or sig == buf.notified_sig:
                continue
            name = buf.display_name
            if sig is None:
                buf.notified_sig = sig
                self.message(f"{name} was deleted on disk")
                continue
            if buf.dirty:
                buf.notified_sig = sig
                self.message(f"{name} changed on disk")
                continue
            try:
                text = buf.path.read_text(encoding="utf-8", newline="")
            except UnicodeDecodeError:
                buf.notified_sig = sig
                self.message(f"Cannot reload {name}: not a UTF-8 text file")
                continue
            except OSError as e:
                buf.notified_sig = sig
                self.message(f"Cannot reload {name}: {e.strerror}")
                continue
            # 置き換えで TextArea.Changed が出るので、タブとステータスバーはそこで更新される
            buf.reload_from_disk(text, sig)
            self.message(f"Reloaded {name}")

    def action_close_tab(self) -> None:
        self._after_pending_input(self._close_tab)

    def _close_tab(self) -> None:
        buf = self.current
        if buf is None:
            return
        if not buf.dirty:
            self.run_worker(self.close_buffer(buf))
            return

        def on_answer(answer: str) -> None:
            if answer == "y":
                self._save(then=lambda: self.close_buffer(buf))
            elif answer == "n":
                self.run_worker(self.close_buffer(buf))

        self.infobar.ask(
            f"Save changes to {buf.display_name} before closing? (y,n,esc) ",
            on_answer,
            choices={"y", "n"},
        )

    def action_quit_all(self) -> None:
        self._after_pending_input(self._quit_all)

    def _quit_all(self) -> None:
        """全部のタブを閉じて終了する。未保存のタブは1つずつ、そのタブを表示して保存するか聞く。

        y で保存、n で保存しない、a で残りを全部保存。Esc や保存の失敗・キャンセルで
        終了をやめる（それまでに保存したファイルはそのまま）。
        """
        pending = [b for b in self.buffers if b.dirty]
        save_rest = False

        def ask_next() -> None:
            nonlocal save_rest
            # 聞いている間に閉じたり保存したりしたバッファは飛ばす
            while pending and not (pending[0] in self.buffers and pending[0].dirty):
                pending.pop(0)
            if not pending:
                self.app.exit()
                return
            buf = pending.pop(0)
            self.switch_to(buf)
            if save_rest:
                self._save(then=ask_next)
                return
            self.infobar.ask(
                f"Save changes to {buf.display_name} before quitting? (y,n,a,esc) ",
                on_answer,
                choices={"y", "n", "a"},
                on_cancel=lambda: self.message("Quit cancelled"),
            )

        def on_answer(answer: str) -> None:
            nonlocal save_rest
            if answer == "n":
                ask_next()
                return
            if answer == "a":
                save_rest = True
            # 保存に失敗したりキャンセルしたりしたら then は呼ばれず、そこで終了をやめる
            self._save(then=ask_next)

        ask_next()

    async def action_new_tab(self) -> None:
        await self.add_buffer(self._new_buffer())

    def _cycle(self, step: int) -> None:
        # タブの切り替えは今のペインの中だけ
        pane = self.active_pane
        buf = pane.current
        if buf is None or len(pane.buffers) < 2:
            return
        index = (pane.buffers.index(buf) + step) % len(pane.buffers)
        self.switch_to(pane.buffers[index])

    def action_prev_tab(self) -> None:
        self._cycle(-1)

    def action_next_tab(self) -> None:
        self._cycle(1)

    def action_explorer(self) -> None:
        screen = ExplorerScreen(
            self.explorer_root, self.explorer_show_hidden, self.explorer_sort_desc
        )

        async def on_close(path: Path | None) -> None:
            # オーバーレイの中で Backspace / o で移動していたら、そこを開く。
            # サイドバーのツリーも同じ起点に合わせる（移れなければ元のまま）
            self._set_root(screen.root)
            panel = self._sidebar_panel()
            if panel is not None and panel.root != self.explorer_root:
                panel.set_root(self.explorer_root)
            self.explorer_show_hidden = screen.show_hidden
            self.explorer_sort_desc = screen.sort_desc
            if path is not None:
                await self.open_path(path)
            else:
                self.app.focus_editor()

        self.app.push_screen(screen, on_close)

    def action_quick_open(self) -> None:
        async def on_close(path: Path | None) -> None:
            if path is not None:
                await self.open_path(path)
            else:
                self.app.focus_editor()

        self.app.push_screen(FinderScreen(self.explorer_root), on_close)

    # ---- サイドバー ----

    @property
    def sidebar(self) -> Sidebar:
        return self.query_one("#sidebar", Sidebar)

    @property
    def sidebar_visible(self) -> bool:
        return self.sidebar.has_class("-visible")

    def _sidebar_panel(self) -> ExplorerPanel | None:
        panels = self.sidebar.query(ExplorerPanel)
        return panels.first() if panels else None

    async def action_toggle_sidebar(self) -> None:
        sidebar = self.sidebar
        if self.sidebar_visible:
            sidebar.remove_class("-visible")
            self.app.focus_editor()
            return
        panel = self._sidebar_panel()
        if panel is None:
            panel = ExplorerPanel(
                self.explorer_root, self.explorer_show_hidden, self.explorer_sort_desc
            )
            await sidebar.mount(panel)
        else:
            # 隠している間にオーバーレイで移動していたら、そこに合わせる
            if panel.root != self.explorer_root:
                panel.set_root(self.explorer_root)
            if panel.show_hidden != self.explorer_show_hidden:
                panel.action_toggle_hidden()
            if panel.sort_desc != self.explorer_sort_desc:
                await panel.action_toggle_sort()
        sidebar.add_class("-visible")
        panel.tree.focus()

    def action_focus_tree(self) -> None:
        """サイドバーのツリーとエディタの間でフォーカスを移す。サイドバーが出ていなければ何もしない。

        エディタへ戻るときは、最後に操作していたペインへ戻る。
        """
        panel = self._sidebar_panel()
        if not self.sidebar_visible or panel is None:
            return
        if self.app.focused is panel.tree:
            self.app.focus_editor()
        else:
            panel.tree.focus()

    def action_switch_pane(self) -> None:
        """分割しているとき、もう一方のペインへフォーカスを移す。ツリーには行かない。"""
        panes = self.panes
        if len(panes) < 2:
            return
        other = panes[1] if self.active_pane is panes[0] else panes[0]
        if other.current is not None:
            other.current.focus()

    # ---- 分割 ----

    def action_toggle_split(self) -> None:
        self._after_pending_input(self._toggle_split)

    async def _toggle_split(self) -> None:
        """分割なし → 左右 → 上下 → 分割なし の順に切り替える。"""
        async with self._layout_lock:
            split = self.split
            if split is None:
                await self._split_with_current()
            elif split == "horizontal":
                # 左右で変えた幅は上下には引き継がない
                for pane in self.panes:
                    pane.reset_size()
                self.editor_area.add_class("-vertical")
            else:
                await self._unsplit()

    def action_move_tab(self) -> None:
        self._after_pending_input(self._move_tab)

    async def _move_tab(self) -> None:
        """今のタブを隣のペインへ移す。分割していなければ左右に分割して移す。"""
        async with self._layout_lock:
            buf = self.current
            if buf is None:
                return
            if self.split is None:
                await self._split_with_current()
                return
            src = self.active_pane
            dst = next(p for p in self.panes if p is not src)
            await self.move_buffer(buf, dst)

    async def move_buffer(
        self, buf: Buffer, dst: Pane, index: int | None = None
    ) -> Buffer:
        """buf を dst のペインの index の位置（省くと末尾）へ移して表示する。

        移したあとのバッファを返す。元のペインが空になったら分割をやめる。
        """
        src = self.pane_of(buf)
        new = await self._transfer(buf, dst, index)
        if not src.buffers:
            await self._close_empty_pane(src)
        self.switch_to(new)
        return new

    async def _transfer(
        self, buf: Buffer, dst: Pane, index: int | None = None
    ) -> Buffer:
        """buf を作り直して dst に加え、元のペインから外す（表示とフォーカスは呼ぶ側で）。"""
        new = buf.moved_copy()
        await dst.insert(new, index)
        await self.pane_of(buf).remove_buffer(buf)
        return new

    async def _split_with_current(self) -> None:
        """左右に分割して、今のタブを新しいペインへ移す。

        元のペインが空になったら空の無題バッファを開いておく。
        """
        buf = self.current
        if buf is None:
            return
        src = self.active_pane
        dst = Pane(self._config.hide_single_tab)
        dst.add_class("-second")
        await self.editor_area.mount(dst)
        new = await self._transfer(buf, dst)
        if not src.buffers:
            empty = self._new_buffer()
            await src.insert(empty)
            src.show(empty)
        self.switch_to(new)

    async def _unsplit(self) -> None:
        """2つ目のペインのタブを1つ目の後ろにまとめて、分割をやめる。

        空の無題バッファは、ほかにタブがあれば捨てる。フォーカスしていたバッファはそのまま。
        """
        first, second = self.panes
        focused = self.current
        moved: dict[Buffer, Buffer] = {}
        for buf in list(second.buffers):
            moved[buf] = await self._transfer(buf, first)
        await self._close_empty_pane(second)
        focused = moved.get(focused, focused) if focused is not None else None
        for buf in list(first.buffers):
            if buf.is_pristine_empty and len(first.buffers) > 1:
                await first.remove_buffer(buf)
        if focused not in first.buffers:
            focused = first.current or first.buffers[0]
        self.switch_to(focused)

    async def _close_empty_pane(self, pane: Pane) -> None:
        await pane.remove()
        self.editor_area.remove_class("-vertical")
        for rest in self.panes:
            rest.remove_class("-second")
            rest.reset_size()

    def on_explorer_panel_changed(self, event: ExplorerPanel.Changed) -> None:
        # サイドバーで移動・切替したら、オーバーレイの次回の起点にも反映する
        panel = event.panel
        if panel.root != self.explorer_root:
            old = self.explorer_root
            if not self._set_root(panel.root):
                # 移れなかったら、ツリーも元の起点に戻す（起点と cwd をずらさない）
                panel.set_root(old)
        self.explorer_show_hidden = panel.show_hidden
        self.explorer_sort_desc = panel.sort_desc

    # ---- ディレクトリを開く ----

    def _set_root(self, path: Path) -> bool:
        """path を開く。ツリーの起点とカレントディレクトリをそろえて変える。

        サイドバーのツリーは呼ぶ側で合わせる。移れなければ False。
        """
        if path == self.explorer_root:
            return True
        try:
            os.chdir(path)
        except OSError as e:
            self.message(f"Cannot open {display_path(path)}: {e.strerror}")
            return False
        self.explorer_root = self.cwd = path
        # ステータスバーのパスは新しいカレントディレクトリからの相対パスになる
        self.refresh_bars()
        return True

    # ---- ツリーでのファイル操作（サイドバーのみ） ----

    def on_explorer_panel_file_op(self, event: ExplorerPanel.FileOp) -> None:
        event.stop()
        if event.kind == "rename":
            self._rename_path(event.panel, event.path)
        elif event.kind == "delete":
            self._trash_path(event.panel, event.path)
        elif event.kind == "mkdir":
            self._make_dir(event.panel, event.path)

    def _reveal(self, panel: ExplorerPanel, path: Path) -> None:
        self.run_worker(panel.tree.reveal(path))

    def _rename_path(self, panel: ExplorerPanel, path: Path | None) -> None:
        if path is None:
            return

        def on_name(text: str) -> None:
            name = text.strip()
            if not name or name == path.name:
                self.message("Rename cancelled")
                return
            if "/" in name or name in (".", ".."):
                self.message(f"Invalid name: {name}")
                return
            target = path.with_name(name)
            # 大文字小文字だけ変えるとき（macOS では同じファイル扱い）は通す
            if target.exists() and not _same_file(path, target):
                self.message(f"{name} already exists")
                return
            try:
                path.rename(target)
            except OSError as e:
                self.message(f"Error renaming: {e.strerror}")
                return
            self._move_buffers(path, target)
            self.message(f"Renamed {path.name} to {name}")
            self._reveal(panel, target)

        self.infobar.ask(
            "Rename: ",
            on_name,
            initial=path.name,
            on_cancel=lambda: self.message("Rename cancelled"),
            return_focus=panel.tree,
        )

    def _move_buffers(self, old: Path, new: Path) -> None:
        """名前を変えたファイル / ディレクトリを開いているバッファのパスを付け替える。"""
        for buf in self.buffers:
            if buf.path is None:
                continue
            if buf.path == old:
                buf.path = new
                # 拡張子が変わったかもしれないので、言語を決め直す
                buf.update_language()
            elif buf.path.is_relative_to(old):
                buf.path = new / buf.path.relative_to(old)
        self.refresh_bars()

    def _trash_path(self, panel: ExplorerPanel, path: Path | None) -> None:
        if path is None:
            return
        name = path.name + ("/" if path.is_dir() else "")

        def on_answer(answer: str) -> None:
            if answer != "y":
                self.message("Delete cancelled")
                return
            trash = shutil.which("trash")
            if trash is None:
                self.message("Cannot delete: 'trash' command not found")
                return
            try:
                out = subprocess.run(
                    [trash, str(path)], capture_output=True, timeout=30, check=False
                )
            except (OSError, subprocess.SubprocessError) as e:
                self.message(f"Error moving to trash: {e}")
                return
            if out.returncode != 0:
                err = out.stderr.decode("utf-8", errors="replace").strip()
                self.message(f"Error moving to trash: {err or out.returncode}")
                return
            # 開いているバッファは残す（ディスク上の変更の検知で deleted と知らせる）
            self.message(f"Moved {name} to trash")
            panel.tree.reload()

        self.infobar.ask(
            f"Move {name} to trash? (y,n,esc) ",
            on_answer,
            choices={"y", "n"},
            on_cancel=lambda: self.message("Delete cancelled"),
            return_focus=panel.tree,
        )

    def _make_dir(self, panel: ExplorerPanel, path: Path | None) -> None:
        # カーソルがディレクトリならその中、ファイルならその隣に作る
        if path is None:
            base = panel.root
        elif path.is_dir():
            base = path
        else:
            base = path.parent

        def on_name(text: str) -> None:
            name = text.strip()
            if not name:
                self.message("Cancelled")
                return
            target = (base / Path(name).expanduser()).resolve()
            if target.exists():
                self.message(f"{display_path(target)} already exists")
                return
            try:
                target.mkdir(parents=True)
            except OSError as e:
                self.message(f"Error creating {name}: {e.strerror}")
                return
            self.message(f"Created {display_path(target)}/")
            self._reveal(panel, target)

        where = truncate_left(display_path(base).rstrip("/") + "/", 30)
        self.infobar.ask(
            f"New dir ({where}): ",
            on_name,
            on_cancel=lambda: self.message("Cancelled"),
            return_focus=panel.tree,
        )

    async def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        event.stop()
        # サイドバーから開いたら、すぐ書けるよう開いたファイルへフォーカスを移す
        await self.open_path(event.path)

    def action_help(self) -> None:
        self.app.push_screen(HelpScreen(), lambda _: self.app.focus_editor())

    def action_find(self) -> None:
        self._after_pending_input(self._find)

    def _find(self) -> None:
        buf = self.current
        if buf is None:
            return
        origin = buf.selection

        def search(text: str) -> None:
            start = min(origin)
            if not text:
                buf.selection = origin
                self.message("")
            elif not buf.find(text, start):
                self.message(f"No matches for '{text}'")
            else:
                self.message("")

        def submit(text: str) -> None:
            if text:
                self.last_search = text
                if not buf.find(text, min(origin)):
                    self.message(f"No matches for '{text}'")

        def cancel() -> None:
            buf.selection = origin

        self.infobar.ask("Find: ", submit, on_change=search, on_cancel=cancel)

    def _find_again(self, forward: bool) -> None:
        buf = self.current
        if buf is None:
            return
        if self.infobar.active:
            # 検索プロンプト中ならその入力を使う
            from .prompt import PromptInput

            text = self.infobar.query_one(PromptInput).value
        else:
            text = self.last_search
        if not text:
            self.message("No previous search")
            return
        start, end = sorted(buf.selection)
        if not buf.find(text, end if forward else start, forward=forward):
            self.message(f"No matches for '{text}'")

    def action_find_next(self) -> None:
        self._after_pending_input(lambda: self._find_again(True))

    def action_find_prev(self) -> None:
        self._after_pending_input(lambda: self._find_again(False))

    def action_replace(self) -> None:
        self._after_pending_input(self._replace)

    def _replace(self) -> None:
        buf = self.current
        if buf is None:
            return

        def cancelled() -> None:
            self.message("Cancelled")

        def on_needle(needle: str) -> None:
            if not needle:
                cancelled()
                return
            self.last_search = needle
            self.infobar.ask(
                "Replace with: ",
                lambda text: self._replace_each(buf, needle, text),
                on_cancel=cancelled,
            )

        self.infobar.ask("Replace: ", on_needle, on_cancel=cancelled)

    def _replace_each(self, buf: Buffer, needle: str, text: str) -> None:
        """一致を1件ずつ選択して (y,n,a,esc) で聞きながら置き換える。

        選択中ならその中だけ、なければカーソルから末尾、先頭からカーソルの手前の順に見る。
        範囲は [探し始める位置, この位置より前から始まる一致だけ見る] の組で持つ。
        """
        n = len(needle)
        delta = len(text) - n
        start, end = sorted(buf.index_of(p) for p in buf.selection)
        if start != end:
            segments = [[start, end - n + 1]]
        else:
            segments = [[start, len(buf.text) + 1], [0, start]]
        found = False
        count = 0

        def next_match() -> int | None:
            while segments:
                pos, limit = segments[0]
                idx = buf.find_index(needle, pos, limit)
                if idx is not None:
                    return idx
                segments.pop(0)
            return None

        def ask_next() -> None:
            nonlocal found
            idx = next_match()
            if idx is None:
                finish()
                return
            found = True
            buf.select_index(idx, n)
            self.infobar.ask(
                "Replace? (y,n,a,esc) ",
                lambda answer: on_answer(idx, answer),
                choices={"y", "n", "a"},
                on_cancel=finish,
            )

        def on_answer(idx: int, answer: str) -> None:
            nonlocal count
            if answer == "a":
                replace_rest()
                finish()
                return
            if answer == "y":
                buf.replace_index(idx, n, text)
                count += 1
                # 置き換えた位置より後ろの範囲の端は、長さが変わったぶんずれる
                for seg in segments:
                    if seg[1] > idx:
                        seg[1] += delta
                segments[0][0] = idx + len(text)
            else:
                segments[0][0] = idx + n
            ask_next()

        def replace_rest() -> None:
            # 残りの一致をまとめて置き換え、1回の編集にする（1回の undo で戻る）
            nonlocal count
            matches: list[int] = []
            for pos, limit in segments:
                while (idx := buf.find_index(needle, pos, limit)) is not None:
                    matches.append(idx)
                    pos = idx + n
            matches.sort()
            kept: list[int] = []
            for idx in matches:
                # 折り返しの前後で重なった一致は前のほうだけ使う
                if not kept or idx >= kept[-1] + n:
                    kept.append(idx)
            if not kept:
                return
            first, last = kept[0], kept[-1] + n
            source = buf.text
            pieces: list[str] = []
            pos = first
            for idx in kept:
                pieces += [source[pos:idx], text]
                pos = idx + n
            replaced = "".join(pieces)
            buf.replace_index(first, last - first, replaced)
            buf.move_cursor(buf.location_of(first + len(replaced)))
            count += len(kept)

        def finish() -> None:
            buf.move_cursor(buf.selection.end)
            if not found:
                self.message(f"No matches for '{needle}'")
            else:
                self.message(f"Replaced {count} occurrence{'' if count == 1 else 's'}")

        ask_next()


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.samefile(b)
    except OSError:
        return False


def _make_theme() -> Theme:
    """ansi-dark のスクロールバーの色だけ白黒系に替えたテーマ。

    ansi-dark の既定（青）はタブバーなどと紛れやすいので、つまみはグレー、マウスを乗せたり
    つかんだりしている間は白、溝は端末の背景色にする。CSS ではなくテーマの変数で替えるのは、
    App.CSS に書くとユーザーの CSS より優先されて上書きできなくなるから。
    """
    base = BUILTIN_THEMES["ansi-dark"]
    return replace(
        base,
        name="tsumugi",
        variables={
            **base.variables,
            "scrollbar": "ansi_bright_black",
            "scrollbar-hover": "ansi_white",
            "scrollbar-active": "ansi_white",
            "scrollbar-background": "ansi_default",
            "scrollbar-background-hover": "ansi_default",
            "scrollbar-background-active": "ansi_default",
            "scrollbar-corner-color": "ansi_default",
        },
    )


class TsumugiApp(App[None], inherit_bindings=False):
    TITLE = "tsumugi"
    ENABLE_COMMAND_PALETTE = False
    # Textual 既定の Ctrl+Q（即終了）と Ctrl+C（終了ヘルプ）を外す
    # オーバーレイのツリーでも効くよう、EditorScreen ではなく App に置く
    BINDINGS = [
        Binding("ctrl+l", "copy_path", "Copy path", priority=True),
    ]
    # スクロールバーは幅1マス（つまみの描き方は scrollbar.py）
    CSS = """
    * {
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 1;
    }
    """

    def __init__(
        self,
        files: list[Path] | None = None,
        system_clipboard: bool = True,
        config: Config | None = None,
    ) -> None:
        install_scrollbar()
        config = config or Config()
        # ユーザーの CSS は各ウィジェットの DEFAULT_CSS より優先される
        super().__init__(css_path=config.css)
        self._files = files or []
        self.system_clipboard = system_clipboard
        self.config = config
        self.register_theme(_make_theme())
        self.theme = "tsumugi"

    def on_mount(self) -> None:
        self.push_screen(EditorScreen(self._files, self.config))

    def on_after_input(self, message: AfterInput) -> None:
        message.stop()
        result = message.callback()
        if inspect.isawaitable(result):
            # 非同期の処理（分割の切り替えなど）は worker で動かす
            self.editor.run_worker(result)

    @property
    def editor(self) -> EditorScreen:
        for screen in self.screen_stack:
            if isinstance(screen, EditorScreen):
                return screen
        raise LookupError("editor screen not mounted")

    def show_message(self, text: str) -> None:
        self.editor.message(text)

    def focus_editor(self) -> None:
        buf = self.editor.current
        if buf is not None:
            buf.focus()

    def action_copy_path(self) -> None:
        """ツリーにフォーカスがあればカーソル位置の、なければ今のタブのファイルの絶対パスをコピーする。"""
        editor = self.editor
        focused = self.focused
        if isinstance(focused, DirectoryTree):
            node = focused.cursor_node
            if node is None or node.data is None:
                return
            path: Path | None = node.data.path.expanduser().resolve()
        elif self.screen is editor and not editor.infobar.active:
            buf = editor.current
            path = buf.path if buf is not None else None
            if path is None:
                self.show_message("No file path to copy")
                return
        else:
            # 検索の入力中やヘルプなど、ツリー以外のモーダルでは何もしない
            return
        self.copy_to_clipboard(str(path))
        self.show_message(f"Copied {path}")

    # ---- クリップボード: macOS では pbcopy/pbpaste も使う ----

    def copy_to_clipboard(self, text: str) -> None:
        super().copy_to_clipboard(text)
        if self.system_clipboard and shutil.which("pbcopy"):
            try:
                subprocess.run(
                    ["pbcopy"], input=text.encode("utf-8"), timeout=2, check=False
                )
            except OSError, subprocess.SubprocessError:
                pass

    def read_clipboard(self) -> str:
        if self.system_clipboard and shutil.which("pbpaste"):
            try:
                out = subprocess.run(
                    ["pbpaste"], capture_output=True, timeout=2, check=False
                )
                if out.returncode == 0:
                    return out.stdout.decode("utf-8", errors="replace")
            except OSError, subprocess.SubprocessError:
                pass
        return self.clipboard


@contextmanager
def terminal_title(title: str, stream: TextIO) -> Iterator[None]:
    """ターミナルのタブ / ウィンドウのタイトルを title にし、抜けるときに元へ戻す。

    何もしないと iTerm2 などは前面のプロセス名（Python）をタイトルに出すため。
    元に戻すのは xterm のタイトルスタック（保存 CSI 22;0 t / 復元 CSI 23;0 t）に
    対応したターミナルだけで効く。tty でなければ何も書かない。
    """
    if not stream.isatty():
        yield
        return
    stream.write("\x1b[22;0t")  # 今のタイトルを保存
    stream.write(f"\x1b]0;{title}\x07")  # タブ名とウィンドウ名を設定
    stream.flush()
    try:
        yield
    finally:
        stream.write("\x1b[23;0t")  # 保存したタイトルに戻す
        stream.flush()


class UsageError(Exception):
    pass


def parse_args(args: list[str]) -> tuple[list[Path], Path | None]:
    """コマンドライン引数を、開くファイルと起点のディレクトリに分ける。

    ファイルは chdir の前に絶対パスにしておく（`tsumugi dir a.txt` の a.txt はシェルの
    カレントディレクトリから数える）。ディレクトリは1つまで。
    """
    files: list[Path] = []
    dirs: list[Path] = []
    for arg in args:
        path = Path(arg).expanduser().absolute()
        (dirs if path.is_dir() else files).append(path)
    if len(dirs) > 1:
        raise UsageError("only one directory can be given")
    return files, (dirs[0] if dirs else None)


def main() -> None:
    try:
        files, root = parse_args(sys.argv[1:])
        if root is not None:
            os.chdir(root)
    except (UsageError, OSError) as e:
        print(f"tsumugi: {e}", file=sys.stderr)
        sys.exit(2)
    with terminal_title("tsumugi", sys.__stdout__):
        TsumugiApp(files, config=load_config()).run()


if __name__ == "__main__":
    main()
