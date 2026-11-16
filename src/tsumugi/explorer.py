"""Ctrl+B で開くオーバーレイのファイルエクスプローラ。"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DirectoryTree, Label


class FileTree(DirectoryTree):
    def __init__(self, path: Path, show_hidden: bool = False) -> None:
        super().__init__(path, id="file-tree")
        self.show_hidden = show_hidden

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        if self.show_hidden:
            return paths
        return [p for p in paths if not p.name.startswith(".")]


class ExplorerScreen(ModalScreen[Path | None]):
    """ツリーからファイルを選ぶと、そのパスを返して閉じる。"""

    DEFAULT_CSS = """
    ExplorerScreen {
        align: center middle;
    }
    ExplorerScreen > #explorer {
        width: 70%;
        max-width: 100;
        height: 80%;
        border: round $accent;
        border-title-align: left;
        border-subtitle-align: right;
        background: $surface;
        padding: 0 1;
    }
    ExplorerScreen #root-path {
        width: 1fr;
        color: $text-muted;
        text-style: bold;
    }
    ExplorerScreen #file-tree {
        height: 1fr;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("escape,ctrl+b,ctrl+q", "close", "Close", show=False),
        Binding("backspace", "parent", "Parent dir", show=False),
        Binding("full_stop", "toggle_hidden", "Hidden files", show=False),
    ]

    def __init__(self, root: Path, show_hidden: bool = False) -> None:
        super().__init__()
        self.root = root
        self.show_hidden = show_hidden

    def compose(self) -> ComposeResult:
        with Vertical(id="explorer") as box:
            box.border_title = "Explorer"
            box.border_subtitle = "Enter: open  BS: parent  .: hidden  Esc: close"
            yield Label(self._root_label(), id="root-path")
            yield FileTree(self.root, self.show_hidden)

    def on_mount(self) -> None:
        self.query_one(FileTree).focus()

    def _root_label(self) -> str:
        home = Path.home()
        try:
            rel = self.root.relative_to(home)
            return "~" if str(rel) == "." else f"~/{rel}"
        except ValueError:
            return str(self.root)

    def _set_root(self, root: Path) -> None:
        self.root = root
        self.query_one(FileTree).path = root
        self.query_one("#root-path", Label).update(self._root_label())

    def action_close(self) -> None:
        self.dismiss(None)

    def action_parent(self) -> None:
        parent = self.root.parent
        if parent != self.root:
            self._set_root(parent)

    def action_toggle_hidden(self) -> None:
        tree = self.query_one(FileTree)
        tree.show_hidden = self.show_hidden = not self.show_hidden
        tree.reload()

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        event.stop()
        self.dismiss(event.path)
