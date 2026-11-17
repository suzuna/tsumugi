"""ファイルエクスプローラ。オーバーレイ（Ctrl+B）とサイドバー（Ctrl+E）で共通のパネルを使う。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import DirectoryTree
from textual.widgets.directory_tree import DirEntry
from textual.widgets.tree import TreeNode
from textual.worker import get_current_worker

# Textual の Tree と同じ。この meta が付いた部分をクリックすると開閉する
TOGGLE_STYLE = Style.from_meta({"toggle": True})

# ツリーとディスクの食い違いを確かめる間隔（秒）
TREE_POLL_INTERVAL = 0.5

# 展開済みのディレクトリごとの、ツリーに出ている子のパス
Snapshot = dict[Path, set[Path]]


def sort_paths(
    paths: list[Path], desc: bool, is_dir: Callable[[Path], bool]
) -> list[Path]:
    """ディレクトリを先にして、それぞれの中を名前（大文字小文字を無視）で並べる。"""
    paths = sorted(paths, key=lambda p: p.name.lower(), reverse=desc)
    return sorted(
        paths, key=lambda p: not is_dir(p)
    )  # 安定ソートなので名前順は保たれる


class FileTree(DirectoryTree):
    """micro の filemanager 風のツリー。

    ディレクトリは `+ name/`（閉）/ `- name/`（開）、ファイルは `  name`。
    罫線とルートノードは出さず、階層ごとに空白2つで字下げする。
    """

    # DirectoryTree はディレクトリ名を太字にする（ANSI テーマ用の指定も別にある）ので、両方打ち消す
    DEFAULT_CSS = """
    FileTree > .directory-tree--folder {
        text-style: none;
    }
    FileTree:ansi > .directory-tree--folder {
        text-style: none;
    }
    """

    BINDINGS = [
        Binding("right", "expand_node", "Expand", show=False),
        Binding("left", "collapse_or_parent", "Collapse", show=False),
    ]

    def __init__(
        self, path: Path, show_hidden: bool = False, sort_desc: bool = False
    ) -> None:
        super().__init__(path, classes="file-tree")
        self.show_hidden = show_hidden
        self.sort_desc = sort_desc
        self.show_root = False
        self.show_guides = False
        self.guide_depth = 2

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        if self.show_hidden:
            return paths
        return [p for p in paths if not p.name.startswith(".")]

    @work(thread=True, exit_on_error=False)
    def _load_directory(self, node: TreeNode[DirEntry]) -> list[Path]:
        # DirectoryTree._load_directory と同じく「ディレクトリが先」で、
        # それぞれの中の名前順を sort_desc で昇順 / 降順に切り替える
        assert node.data is not None
        path = node.data.path.expanduser().resolve()
        paths = list(
            self.filter_paths(self._directory_content(path, get_current_worker()))
        )
        return sort_paths(paths, self.sort_desc, self._safe_is_dir)

    def _populate_node(self, node: TreeNode[DirEntry], content: Iterable[Path]) -> None:
        super()._populate_node(node, content)
        # ルートを隠すと最初はカーソルがどの行にもない。ルートの読み込み後に先頭行へ置く
        if node is self.root and self.cursor_line < 0:
            self.call_after_refresh(self._cursor_to_first_line)

    def find_node(self, path: Path) -> TreeNode[DirEntry] | None:
        """読み込み済みのノードから path のものを探す。"""
        stack = list(self.root.children)
        while stack:
            node = stack.pop()
            if node.data is not None and node.data.path == path:
                return node
            stack.extend(node.children)
        return None

    def select_path(self, path: Path) -> bool:
        """読み込み済みのノードから path を探してカーソルを移す。見つからなければ False。"""
        node = self.find_node(path)
        if node is None:
            return False
        self.move_cursor(node)
        return True

    async def reveal(self, path: Path) -> bool:
        """読み直してから、path までの親を展開してカーソルを合わせる。"""
        await self.reload()
        for ancestor in reversed(path.parents):
            node = self.find_node(ancestor)
            if node is None or not node.allow_expand or node.is_expanded:
                continue
            node.expand()
            await self._add_to_load_queue(node)
        return self.select_path(path)

    @property
    def is_busy(self) -> bool:
        """ディレクトリの読み込み中（中身がまだツリーに入っていないかもしれない）。"""
        return self.lock.is_locked or not self._load_queue.empty()

    def snapshot(self) -> Snapshot:
        """展開して読み込み済みのディレクトリと、その子としてツリーに出ているパス。"""
        out: Snapshot = {}
        stack = [self.root]
        while stack:
            node = stack.pop()
            data = node.data
            if data is None or not data.loaded:
                continue
            if node is not self.root and not node.is_expanded:
                continue
            out[data.path] = {c.data.path for c in node.children if c.data is not None}
            stack.extend(c for c in node.children if c.allow_expand)
        return out

    def differs_from_disk(self, snapshot: Snapshot) -> bool:
        """snapshot のどれかのディレクトリで、ディスク上の中身が違うか。スレッドから呼ぶ。"""
        for path, shown in snapshot.items():
            location = path.expanduser().resolve()
            try:
                on_disk = set(self.filter_paths(location.iterdir()))
            except OSError:
                # 消えたディレクトリは、親の一覧の食い違いとして拾う
                continue
            if on_disk != shown:
                return True
        return False

    def _cursor_to_first_line(self) -> None:
        if self.cursor_line < 0 and self.last_line >= 0:
            self.cursor_line = 0

    def render_label(
        self, node: TreeNode[DirEntry], base_style: Style, style: Style
    ) -> Text:
        # DirectoryTree.render_label と同じスタイル付けで、絵文字の代わりに +/- を使う
        label = node._label.copy()
        label.stylize(style)
        if not self.is_mounted:
            return label

        if node._allow_expand:
            prefix = ("- " if node.is_expanded else "+ ", base_style + TOGGLE_STYLE)
            label.append("/")
            label.stylize_before(
                self.get_component_rich_style("directory-tree--folder", partial=True)
            )
        else:
            prefix = ("  ", base_style)
            label.stylize_before(
                self.get_component_rich_style("directory-tree--file", partial=True)
            )
            label.highlight_regex(
                r"\..+$",
                self.get_component_rich_style(
                    "directory-tree--extension", partial=True
                ),
            )

        if label.plain.startswith("."):
            label.stylize_before(
                self.get_component_rich_style("directory-tree--hidden", partial=True)
            )
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


def display_path(root: Path) -> str:
    try:
        rel = root.relative_to(Path.home())
    except ValueError:
        return str(root)
    return "~" if str(rel) == "." else f"~/{rel}"


ELLIPSIS = "…"


def truncate_left(text: str, width: int) -> str:
    """表示幅 width に収まるよう前を削り、先頭に … を付ける。収まればそのまま。"""
    if cell_len(text) <= width:
        return text
    if width <= 0:
        return ""
    if width == 1:
        return ELLIPSIS
    budget = width - cell_len(ELLIPSIS)
    kept: list[str] = []
    used = 0
    for ch in reversed(text):
        w = cell_len(ch)
        if used + w > budget:
            break
        kept.append(ch)
        used += w
    return ELLIPSIS + "".join(reversed(kept))


class RootPath(Widget):
    """ツリーの起点のパス。幅に収まらなければ前を省略して1行で出す。"""

    DEFAULT_CSS = """
    RootPath {
        height: 1;
        width: 1fr;
    }
    """

    def __init__(self, text: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._text = text

    @property
    def text(self) -> str:
        return self._text

    def set_path(self, text: str) -> None:
        self._text = text
        self.refresh()

    def render(self) -> Text:
        return Text(truncate_left(self._text, self.size.width), no_wrap=True)


class ExplorerPanel(Vertical):
    """ルートのパス表示とディレクトリツリー。Backspace で親へ、. で隠しファイル切替。"""

    DEFAULT_CSS = """
    ExplorerPanel > RootPath {
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
        Binding("o", "enter_dir", "Open directory", show=False),
        Binding("full_stop", "toggle_hidden", "Hidden files", show=False),
        Binding("s", "toggle_sort", "Sort order", show=False),
        Binding("r,f2", "file_op('rename')", "Rename", show=False),
        Binding("d", "file_op('delete')", "Delete", show=False),
        Binding("m", "file_op('mkdir')", "New directory", show=False),
    ]

    class Changed(Message):
        """ルート・隠しファイル表示・並び順が変わった。"""

        def __init__(self, panel: ExplorerPanel) -> None:
            super().__init__()
            self.panel = panel

    class FileOp(Message):
        """ツリーでのファイル操作（rename / delete / mkdir）の依頼。

        名前の入力は画面下のインフォバーを使うので、EditorScreen が受け取って処理する。
        path はカーソルのパス（ツリーが空なら None）。
        """

        def __init__(self, panel: ExplorerPanel, kind: str, path: Path | None) -> None:
            super().__init__()
            self.panel = panel
            self.kind = kind
            self.path = path

    def __init__(
        self, root: Path, show_hidden: bool = False, sort_desc: bool = False, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.root = root
        self.show_hidden = show_hidden
        self.sort_desc = sort_desc

    def compose(self) -> ComposeResult:
        yield RootPath(display_path(self.root))
        yield FileTree(self.root, self.show_hidden, self.sort_desc)

    def on_mount(self) -> None:
        # ほかのプロセス（LLM やシェル）が足したり消したりしたファイルをツリーに反映する
        self.set_interval(TREE_POLL_INTERVAL, self._poll)

    def _poll(self) -> None:
        tree = self.tree
        # 見えていないとき（隠したサイドバー、オーバーレイの下）や読み込み中は何もしない
        if self.app.screen is not self.screen or tree.region.area == 0:
            return
        if tree.is_busy:
            return
        self._check_disk(tree.snapshot())

    @work(thread=True, exclusive=True, group="tree-poll", exit_on_error=False)
    def _check_disk(self, snapshot: Snapshot) -> None:
        if self.tree.differs_from_disk(snapshot):
            self.app.call_from_thread(self._reload_if_unchanged, snapshot)

    async def _reload_if_unchanged(self, snapshot: Snapshot) -> None:
        tree = self.tree
        # 一覧を取っている間に展開や読み込みがあったら、次の回に任せる
        if tree.is_busy or tree.snapshot() != snapshot:
            return
        # reload は展開状態とカーソル位置を保ったまま読み直す
        await tree.reload()

    @property
    def tree(self) -> FileTree:
        return self.query_one(FileTree)

    def set_root(self, root: Path) -> None:
        self.root = root
        self.tree.path = root
        self.query_one(RootPath).set_path(display_path(root))
        self.post_message(self.Changed(self))

    def action_parent(self) -> None:
        parent = self.root.parent
        if parent != self.root:
            self.set_root(parent)

    def action_enter_dir(self) -> None:
        """カーソルのディレクトリを起点にする（Backspace の逆）。ファイルの上では何もしない。

        オーバーレイではそのまま閉じて、メイン画面をそのディレクトリで開く。
        """
        node = self.tree.cursor_node
        if node is None or node.data is None or not node.allow_expand:
            return
        self.set_root(node.data.path)
        if isinstance(self.screen, ExplorerScreen):
            self.screen.dismiss(None)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        # オーバーレイにはインフォバーがないので、ファイル操作はサイドバーだけ
        if action == "file_op" and isinstance(self.screen, ExplorerScreen):
            return False
        return True

    def action_file_op(self, kind: str) -> None:
        node = self.tree.cursor_node
        path = node.data.path if node is not None and node.data is not None else None
        self.post_message(self.FileOp(self, kind, path))

    def action_toggle_hidden(self) -> None:
        tree = self.tree
        tree.show_hidden = self.show_hidden = not self.show_hidden
        tree.reload()
        self.post_message(self.Changed(self))

    async def action_toggle_sort(self) -> None:
        tree = self.tree
        node = tree.cursor_node
        current = node.data.path if node is not None and node.data is not None else None
        tree.sort_desc = self.sort_desc = not self.sort_desc
        await tree.reload()
        # 並びが変わっても、カーソルは同じファイル / ディレクトリについていく
        if current is not None:
            tree.select_path(current)
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
        Binding("escape,ctrl+b", "close", "Close", show=False),
    ]

    def __init__(
        self, root: Path, show_hidden: bool = False, sort_desc: bool = False
    ) -> None:
        super().__init__()
        self._initial_root = root
        self._initial_show_hidden = show_hidden
        self._initial_sort_desc = sort_desc

    def compose(self) -> ComposeResult:
        panel = ExplorerPanel(
            self._initial_root, self._initial_show_hidden, self._initial_sort_desc
        )
        panel.border_title = "Explorer"
        panel.border_subtitle = (
            "Enter: open/expand  o: cd  BS: parent  .: hidden  s: sort  Esc: close"
        )
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

    @property
    def sort_desc(self) -> bool:
        return self.panel.sort_desc

    def action_close(self) -> None:
        self.dismiss(None)

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        event.stop()
        self.dismiss(event.path)
