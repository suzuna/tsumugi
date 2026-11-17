"""エディタのペイン。タブバーと、そのペインのバッファを切り替えて見せる ContentSwitcher を持つ。

分割していないときはペインは1つ。分割すると2つになり、タブ（バッファ）はどちらか片方に属する。
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import ContentSwitcher

from .editor import Buffer
from .explorer import truncate_middle
from .resize import PANE_MIN_HEIGHT, PANE_MIN_WIDTH, EdgeDrag, clamp
from .tabs import TabBar

# タブに出すファイル名の最大の表示幅（未保存の印 " +" は含めない）
TAB_NAME_MAX = 20


class Pane(EdgeDrag, Vertical):
    DEFAULT_CSS = """
    Pane {
        width: 1fr;
        height: 1fr;
    }
    Pane > ContentSwitcher {
        height: 1fr;
    }
    """

    def __init__(self, hide_single_tab: bool = False) -> None:
        super().__init__()
        self._hide_single_tab = hide_single_tab
        # タブの並び順
        self.buffers: list[Buffer] = []

    def compose(self) -> ComposeResult:
        yield TabBar(self._hide_single_tab)
        yield ContentSwitcher()

    @property
    def tab_bar(self) -> TabBar:
        return self.query_one(TabBar)

    @property
    def switcher(self) -> ContentSwitcher:
        return self.query_one(ContentSwitcher)

    @property
    def current(self) -> Buffer | None:
        switcher = self.switcher
        if switcher.current is None:
            return None
        try:
            return switcher.get_child_by_id(switcher.current, Buffer)
        except NoMatches:
            # 表示中のバッファを外した直後（次に表示するものを選ぶ前）
            return None

    def show(self, buf: Buffer) -> None:
        self.switcher.current = buf.id

    async def insert(self, buf: Buffer, index: int | None = None) -> None:
        """バッファをタブに加える（表示は切り替えない）。index を省くと末尾に置く。"""
        if index is None:
            self.buffers.append(buf)
        else:
            self.buffers.insert(index, buf)
        await self.switcher.mount(buf)

    async def replace(self, old: Buffer, new: Buffer) -> None:
        """old のタブを同じ位置で new に置き換える（表示は切り替えない）。"""
        self.buffers[self.buffers.index(old)] = new
        await self.switcher.mount(new)
        await old.remove()

    async def remove_buffer(self, buf: Buffer) -> None:
        """バッファをタブから外す。表示中だったら、残ったうちの同じ位置のタブを表示する。"""
        index = self.buffers.index(buf)
        shown = self.current is buf
        self.buffers.remove(buf)
        await buf.remove()
        if shown and self.buffers:
            self.show(self.buffers[min(index, len(self.buffers) - 1)])

    def move_tab(self, buf: Buffer, index: int) -> None:
        """同じペインの中でタブの位置を変える。"""
        self.buffers.remove(buf)
        self.buffers.insert(min(index, len(self.buffers)), buf)

    # ---- 区切り線のドラッグ ----

    def _is_vertical_split(self) -> bool:
        parent = self.parent
        return isinstance(parent, Widget) and parent.has_class("-vertical")

    def is_edge(self, screen_x: int, screen_y: int) -> bool:
        # 区切り線は2つ目のペインの左 / 上の枠線
        if not self.has_class("-second"):
            return False
        region, content = self.region, self.content_region
        if self._is_vertical_split():
            return screen_y == region.y and content.y > region.y
        return screen_x == region.x and content.x > region.x

    def on_edge_drag(self, screen_x: int, screen_y: int) -> None:
        """区切り線を動かした位置で、2つのペインの大きさを分け直す。

        比（fr）で持つので、画面の大きさが変わっても割合は保たれる。
        """
        parent = self.parent
        if not isinstance(parent, Widget):
            return
        panes = [w for w in parent.children if isinstance(w, Pane)]
        if len(panes) != 2:
            return
        first, second = panes
        area = parent.content_region
        if self._is_vertical_split():
            total = area.height
            size = clamp(screen_y - area.y, PANE_MIN_HEIGHT, total - PANE_MIN_HEIGHT)
            first.styles.height = f"{size}fr"
            second.styles.height = f"{total - size}fr"
        else:
            total = area.width
            size = clamp(screen_x - area.x, PANE_MIN_WIDTH, total - PANE_MIN_WIDTH)
            first.styles.width = f"{size}fr"
            second.styles.width = f"{total - size}fr"

    def reset_size(self) -> None:
        """ドラッグで変えた大きさを捨てて、CSS の指定（1fr）に戻す。"""
        self.styles.width = None
        self.styles.height = None

    def refresh_tabs(self, active: bool) -> None:
        """タブバーを描き直す。active はこのペインが今操作しているペインか。"""
        cur = self.current
        labels = [
            truncate_middle(b.display_name, TAB_NAME_MAX) + (" +" if b.dirty else "")
            for b in self.buffers
        ]
        index = self.buffers.index(cur) if cur in self.buffers else 0
        self.tab_bar.set_tabs(labels, index, focused=active)
