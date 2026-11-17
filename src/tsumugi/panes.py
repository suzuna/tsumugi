"""エディタのペイン。タブバーと、そのペインのバッファを切り替えて見せる ContentSwitcher を持つ。

分割していないときはペインは1つ。分割すると2つになり、タブ（バッファ）はどちらか片方に属する。
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widgets import ContentSwitcher

from .editor import Buffer
from .tabs import TabBar


class Pane(Vertical):
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

    def refresh_tabs(self, active: bool) -> None:
        """タブバーを描き直す。active はこのペインが今操作しているペインか。"""
        cur = self.current
        labels = [b.display_name + (" +" if b.dirty else "") for b in self.buffers]
        index = self.buffers.index(cur) if cur in self.buffers else 0
        self.tab_bar.set_tabs(labels, index, focused=active)
