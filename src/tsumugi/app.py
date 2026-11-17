"""tsumugi のアプリ本体。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import ContentSwitcher, DirectoryTree, TextArea

from .config import Config, load_config
from .editor import Buffer, file_sig
from .explorer import ExplorerPanel, ExplorerScreen, display_path, truncate_left
from .help import HelpScreen
from .prompt import InfoBar
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
    EditorScreen #editor-area {
        width: 1fr;
        height: 1fr;
    }
    EditorScreen ContentSwitcher {
        height: 1fr;
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
        Binding("ctrl+q", "close_tab", "Quit", priority=True),
        Binding("ctrl+b", "explorer", "Explorer", priority=True),
        Binding("ctrl+t", "new_tab", "New tab", priority=True),
        Binding("alt+comma,ctrl+pageup", "prev_tab", "Previous tab", priority=True),
        Binding("alt+full_stop,ctrl+pagedown", "next_tab", "Next tab", priority=True),
        Binding("ctrl+f", "find", "Find", priority=True),
        Binding("ctrl+n", "find_next", "Find next", priority=True),
        Binding("ctrl+p", "find_prev", "Find previous", priority=True),
        Binding("ctrl+g", "help", "Help", priority=True),
        Binding("ctrl+e", "toggle_sidebar", "Sidebar", priority=True),
        Binding("ctrl+w", "switch_pane", "Switch pane", priority=True),
    ]

    def __init__(self, files: list[Path], config: Config) -> None:
        super().__init__()
        self._initial_files = files
        self._config = config
        self.buffers: list[Buffer] = []
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
            yield Vertical(id="sidebar")
            with Vertical(id="editor-area"):
                yield TabBar()
                yield ContentSwitcher()
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
    def current(self) -> Buffer | None:
        switcher = self.query_one(ContentSwitcher)
        if switcher.current is None:
            return None
        return switcher.get_child_by_id(switcher.current, Buffer)

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
        return Buffer(text, path, soft_wrap=self._config.soft_wrap)

    async def add_buffer(self, buf: Buffer, focus: bool = True) -> None:
        self.buffers.append(buf)
        await self.query_one(ContentSwitcher).mount(buf)
        self.switch_to(buf, focus)

    def switch_to(self, buf: Buffer, focus: bool = True) -> None:
        self.query_one(ContentSwitcher).current = buf.id
        if focus:
            buf.focus()
        self.refresh_bars()

    def refresh_bars(self) -> None:
        buf = self.current
        labels = [b.display_name + (" +" if b.dirty else "") for b in self.buffers]
        active = self.buffers.index(buf) if buf in self.buffers else 0
        self.query_one(TabBar).set_tabs(labels, active)
        if buf is not None:
            row, col = buf.cursor_location
            self.query_one(StatusBar).update_status(
                status_path(buf.path, self.cwd),
                buf.dirty,
                row,
                col,
                buf.document.newline,
            )

    async def open_path(self, path: Path, focus: bool = True) -> None:
        """ファイルを開く。focus=False ならフォーカスを動かさない（サイドバーから開くとき）。"""
        path = path.expanduser().resolve()
        for buf in self.buffers:
            if buf.path == path:
                self.switch_to(buf, focus)
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

        cur = self.current
        new = self._new_buffer(text, path)
        new.disk_sig = sig
        if cur is not None and cur.is_pristine_empty:
            # 空の無題バッファは置き換える
            index = self.buffers.index(cur)
            self.buffers[index] = new
            await self.query_one(ContentSwitcher).mount(new)
            await cur.remove()
            self.switch_to(new, focus)
        else:
            await self.add_buffer(new, focus)
        if not path.exists():
            self.message(f"New file: {path}")

    async def close_buffer(self, buf: Buffer) -> None:
        index = self.buffers.index(buf)
        self.buffers.remove(buf)
        await buf.remove()
        if not self.buffers:
            self.app.exit()
            return
        self.switch_to(self.buffers[min(index, len(self.buffers) - 1)])

    def on_tab_bar_clicked(self, event: TabBar.Clicked) -> None:
        if 0 <= event.index < len(self.buffers):
            self.switch_to(self.buffers[event.index])

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
            callback()
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
        try:
            saved = buf.save(path)
        except OSError as e:
            self.message(f"Error saving: {e.strerror}")
            return
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
            self.app.exit()
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

    async def action_new_tab(self) -> None:
        await self.add_buffer(self._new_buffer())

    def _cycle(self, step: int) -> None:
        buf = self.current
        if buf is None or len(self.buffers) < 2:
            return
        index = (self.buffers.index(buf) + step) % len(self.buffers)
        self.switch_to(self.buffers[index])

    def action_prev_tab(self) -> None:
        self._cycle(-1)

    def action_next_tab(self) -> None:
        self._cycle(1)

    def action_explorer(self) -> None:
        screen = ExplorerScreen(
            self.explorer_root, self.explorer_show_hidden, self.explorer_sort_desc
        )

        async def on_close(path: Path | None) -> None:
            self.explorer_root = screen.root
            self.explorer_show_hidden = screen.show_hidden
            self.explorer_sort_desc = screen.sort_desc
            if path is not None:
                await self.open_path(path)
            else:
                self.app.focus_editor()

        self.app.push_screen(screen, on_close)

    # ---- サイドバー ----

    @property
    def sidebar(self) -> Vertical:
        return self.query_one("#sidebar", Vertical)

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

    def action_switch_pane(self) -> None:
        if not self.sidebar_visible:
            return
        panel = self._sidebar_panel()
        if panel is None:
            return
        if panel.tree.has_focus:
            self.app.focus_editor()
        else:
            panel.tree.focus()

    def on_explorer_panel_changed(self, event: ExplorerPanel.Changed) -> None:
        # サイドバーで移動・切替したら、オーバーレイの次回の起点にも反映する
        self.explorer_root = event.panel.root
        self.explorer_show_hidden = event.panel.show_hidden
        self.explorer_sort_desc = event.panel.sort_desc

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
        await self.open_path(event.path, focus=False)

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


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.samefile(b)
    except OSError:
        return False


class TsumugiApp(App[None], inherit_bindings=False):
    TITLE = "tsumugi"
    ENABLE_COMMAND_PALETTE = False
    # Textual 既定の Ctrl+Q（即終了）と Ctrl+C（終了ヘルプ）を外す
    BINDINGS = []
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
        self.theme = "ansi-dark"

    def on_mount(self) -> None:
        self.push_screen(EditorScreen(self._files, self.config))

    def on_after_input(self, message: AfterInput) -> None:
        message.stop()
        message.callback()

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
