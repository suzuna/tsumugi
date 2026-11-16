"""ファイルエクスプローラ。オーバーレイ（Ctrl+B）とサイドバー（Ctrl+E）で共通のパネルを使う。"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import DirectoryTree, Label
from textual.widgets.directory_tree import DirEntry
from textual.widgets.tree import TreeNode

# Textual の Tree と同じ。この meta が付いた部分をクリックすると開閉する
TOGGLE_STYLE = Style.from_meta({"toggle": True})


class FileTree(DirectoryTree):
    """micro の filemanager 風のツリー。

    ディレクトリは `+ name/`（閉）/ `- name/`（開）、ファイルは `  name`。
    罫線とルートノードは出さず、階層ごとに空白2つで字下げする。
    """

    BINDINGS = [
        Binding("right", "expand_node", "Expand", show=False),
        Binding("left", "collapse_or_parent", "Collapse", show=False),
    ]

    def __init__(self, path: Path, show_hidden: bool = False) -> None:
        super().__init__(path, classes="file-tree")
        self.show_hidden = show_hidden
        self.show_root = False
        self.show_guides = False
        self.guide_depth = 2

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        if self.show_hidden:
            return paths
        return [p for p in paths if not p.name.startswith(".")]

    def _populate_node(self, node: TreeNode[DirEntry], content: Iterable[Path]) -> None:
        super()._populate_node(node, content)
        # ルートを隠すと最初はカーソルがどの行にもない。ルートの読み込み後に先頭行へ置く
        if node is self.root and self.cursor_line < 0:
            self.call_after_refresh(self._cursor_to_first_line)

    def _cursor_to_first_line(self) -> None:
        if self.cursor_line < 0 and self.last_line >= 0:
            self.cursor_line = 0

    def render_label(self, node: TreeNode[DirEntry], base_style: Style, style: Style) -> Text:
        # DirectoryTree.render_label と同じスタイル付けで、絵文字の代わりに +/- を使う
        label = node._label.copy()
        label.stylize(style)
        if not self.is_mounted:
            return label

        if node._allow_expand:
            prefix = ("- " if node.is_expanded else "+ ", base_style + TOGGLE_STYLE)
            label.append("/")
            label.stylize_before(self.get_component_rich_style("directory-tree--folder", partial=True))
        else:
            prefix = ("  ", base_style)
            label.stylize_before(self.get_component_rich_style("directory-tree--file", partial=True))
            label.highlight_regex(
                r"\..+$",
                self.get_component_rich_style("directory-tree--extension", partial=True),
            )

        if label.plain.startswith("."):
            label.stylize_before(self.get_component_rich_style("directory-tree--hidden", partial=True))
        return Text.assemble(prefix, label)

    def action_expand_node(self) -> None:
        node = self.cursor_node
        if node is not None and node.allow_expand and not node.is_expanded:
            node.expand()

    def action_collapse_or_parent(self) -> None:
        node = self.cursor_node
        if node is None:
            return
        if node.allow_expand and node.is_expanded:
            node.collapse()
            return
        parent = node.parent
        if parent is not None and parent is not self.root:
            self.move_cursor(parent)


def _root_label(root: Path) -> str:
    try:
        rel = root.relative_to(Path.home())
    except ValueError:
        return str(root)
    return "~" if str(rel) == "." else f"~/{rel}"


class ExplorerPanel(Vertical):
    """ルートのパス表示とディレクトリツリー。Backspace で親へ、. で隠しファイル切替。"""

    DEFAULT_CSS = """
    ExplorerPanel > .root-path {
        width: 1fr;
        color: $text-muted;
        text-style: bold;
    }
    ExplorerPanel > FileTree {
        height: 1fr;
        background: transparent;
    }
    """

    BINDINGS = [
        Binding("backspace", "parent", "Parent dir", show=False),
        Binding("full_stop", "toggle_hidden", "Hidden files", show=False),
    ]

    class Changed(Message):
        """ルートや隠しファイル表示が変わった。"""

        def __init__(self, panel: ExplorerPanel) -> None:
            super().__init__()
            self.panel = panel

    def __init__(self, root: Path, show_hidden: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.root = root
        self.show_hidden = show_hidden

    def compose(self) -> ComposeResult:
        yield Label(_root_label(self.root), classes="root-path")
        yield FileTree(self.root, self.show_hidden)

    @property
    def tree(self) -> FileTree:
        return self.query_one(FileTree)

    def set_root(self, root: Path) -> None:
        self.root = root
        self.tree.path = root
        self.query_one(".root-path", Label).update(_root_label(root))
        self.post_message(self.Changed(self))

    def action_parent(self) -> None:
        parent = self.root.parent
        if parent != self.root:
            self.set_root(parent)

    def action_toggle_hidden(self) -> None:
        tree = self.tree
        tree.show_hidden = self.show_hidden = not self.show_hidden
        tree.reload()
        self.post_message(self.Changed(self))


class ExplorerScreen(ModalScreen[Path | None]):
    """オーバーレイ版。ツリーからファイルを選ぶと、そのパスを返して閉じる。"""

    DEFAULT_CSS = """
    ExplorerScreen {
        align: center middle;
    }
    ExplorerScreen > ExplorerPanel {
        width: 70%;
        max-width: 100;
        height: 80%;
        border: round $accent;
        border-title-align: left;
        border-subtitle-align: right;
        background: $surface;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape,ctrl+b,ctrl+q", "close", "Close", show=False),
    ]

    def __init__(self, root: Path, show_hidden: bool = False) -> None:
        super().__init__()
        self._initial_root = root
        self._initial_show_hidden = show_hidden

    def compose(self) -> ComposeResult:
        panel = ExplorerPanel(self._initial_root, self._initial_show_hidden)
        panel.border_title = "Explorer"
        panel.border_subtitle = "Enter: open  BS: parent  .: hidden  Esc: close"
        yield panel

    def on_mount(self) -> None:
        self.query_one(FileTree).focus()

    @property
    def panel(self) -> ExplorerPanel:
        return self.query_one(ExplorerPanel)

    @property
    def root(self) -> Path:
        return self.panel.root

    @property
    def show_hidden(self) -> bool:
        return self.panel.show_hidden

    def action_close(self) -> None:
        self.dismiss(None)

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        event.stop()
        self.dismiss(event.path)
