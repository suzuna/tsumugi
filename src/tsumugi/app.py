"""tsumugi のアプリ本体。"""

from __future__ import annotations

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
from textual.screen import Screen
from textual.widgets import ContentSwitcher, DirectoryTree, TextArea

from .config import Config, load_config
from .editor import Buffer
from .explorer import ExplorerPanel, ExplorerScreen, display_path, truncate_left
from .help import HelpScreen
from .prompt import InfoBar
from .scrollbar import install as install_scrollbar
from .statusbar import StatusBar
from .tabs import TabBar

# プロンプト入力中でも有効なアクション
_ALLOWED_WHILE_PROMPTING = {"find_next", "find_prev"}


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
        self.explorer_root = config.explorer_root
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
                buf.display_name, buf.dirty, row, col, buf.document.newline
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
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8")
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

    def action_save(self, then=None) -> None:
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

    def _do_save(self, buf: Buffer, path: Path | None, then=None) -> None:
        target = path if path is not None else buf.path
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

    def action_close_tab(self) -> None:
        buf = self.current
        if buf is None:
            self.app.exit()
            return
        if not buf.dirty:
            self.run_worker(self.close_buffer(buf))
            return

        def on_answer(answer: str) -> None:
            if answer == "y":
                self.action_save(then=lambda: self.close_buffer(buf))
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

    async def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        event.stop()
        await self.open_path(event.path, focus=False)

    def action_help(self) -> None:
        self.app.push_screen(HelpScreen(), lambda _: self.app.focus_editor())

    def action_find(self) -> None:
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
        self._find_again(True)

    def action_find_prev(self) -> None:
        self._find_again(False)


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


def main() -> None:
    files = [Path(arg) for arg in sys.argv[1:]]
    with terminal_title("tsumugi", sys.__stdout__):
        TsumugiApp(files, config=load_config()).run()


if __name__ == "__main__":
    main()
