"""micro 風のタブバー。既定ではタブが1つでも表示し、hide_single なら2つ以上のときだけ表示する。"""

from __future__ import annotations

from rich.cells import cell_len
from rich.text import Text
from textual import events
from textual.errors import NoWidget
from textual.message import Message
from textual.widget import Widget


class TabBar(Widget):
    # 選択中のタブの見た目は component class で付ける（カスタム CSS で変えられるように）。
    # 分割しているとき、操作していないほうのペインの選択中のタブは tab-bar--unfocused
    COMPONENT_CLASSES = {"tab-bar--active", "tab-bar--unfocused"}

    DEFAULT_CSS = """
    TabBar {
        height: 1;
        width: 1fr;
    }
    TabBar > .tab-bar--active {
        text-style: bold underline;
    }
    TabBar > .tab-bar--unfocused {
        text-style: bold;
    }
    """

    class Clicked(Message):
        def __init__(self, bar: TabBar, index: int) -> None:
            super().__init__()
            self.bar = bar
            self.index = index

        @property
        def control(self) -> TabBar:
            return self.bar

    class Dropped(Message):
        """bar の index 番目のタブを target の上へドラッグ & ドロップした。

        target がタブバーなら target_index はそこへ入れる位置、それ以外なら None。
        """

        def __init__(
            self,
            bar: TabBar,
            index: int,
            target: Widget,
            target_index: int | None,
        ) -> None:
            super().__init__()
            self.bar = bar
            self.index = index
            self.target = target
            self.target_index = target_index

        @property
        def control(self) -> TabBar:
            return self.bar

    def __init__(self, hide_single: bool = False) -> None:
        super().__init__()
        self._hide_single = hide_single
        self._labels: list[str] = []
        self._active = 0
        self._focused = True
        # 横にずらしたとき、左端に出す最初のタブの番号
        self._first = 0
        self._spans: list[tuple[int, int]] = []
        # ドラッグ中のタブの番号
        self._dragging: int | None = None

    def set_tabs(self, labels: list[str], active: int, focused: bool = True) -> None:
        self._labels = labels
        self._active = active
        self._focused = focused
        self._first = min(self._first, max(len(labels) - 1, 0))
        self.display = len(labels) > (1 if self._hide_single else 0)
        self.refresh()

    def _scroll_first(self, widths: list[int], width: int) -> int:
        """左端に出す最初のタブの番号。選択中のタブが見えるよう、タブ1枚単位でずらす。"""
        n = len(widths)
        active = min(max(self._active, 0), n - 1)
        first = min(self._first, n - 1)
        if active < first:
            first = active

        def end_of(i: int) -> int:
            # first から i 番目のタブの右端まで（タブの間の空白1マスを含む）
            return sum(widths[first : i + 1]) + (i - first)

        # 選択中のタブが右にはみ出すなら、収まるまで左のタブを隠す
        while first < active and end_of(active) > width:
            first += 1
        # 右が余っているなら、隠れている左のタブを余りの分だけ戻す
        used = end_of(n - 1)
        while first > 0 and used + 1 + widths[first - 1] <= width:
            first -= 1
            used += 1 + widths[first]
        return first

    def render(self) -> Text:
        text = Text(no_wrap=True, overflow="ellipsis")
        self._spans = []
        if not self._labels:
            return text
        active_style = self.get_component_rich_style(
            "tab-bar--active" if self._focused else "tab-bar--unfocused"
        )
        chunks = [f" {label} " for label in self._labels]
        widths = [cell_len(chunk) for chunk in chunks]
        self._first = self._scroll_first(widths, self.size.width)
        # _spans は全部のタブについて、表示幅で数えたタブバー上の位置を持つ（左に隠れたタブは負）
        x = -(sum(widths[: self._first]) + self._first)
        for i, (chunk, w) in enumerate(zip(chunks, widths)):
            self._spans.append((x, x + w))
            x += w + 1
            if i < self._first:
                continue
            if i == self._active:
                text.append(chunk, style=active_style)
            else:
                text.append(chunk)
            text.append(" ")
        return text

    # ---- クリックとドラッグ & ドロップ ----

    def tab_at(self, x: int) -> int | None:
        """x の位置にあるタブの番号。タブの上でなければ None。"""
        if not 0 <= x < self.size.width:
            return None
        for i, (start, end) in enumerate(self._spans):
            if start <= x < end:
                return i
        return None

    def insert_index_at(self, x: int) -> int:
        """x の位置にタブを落としたときに入れる位置。タブより右なら末尾。"""
        for i, (_, end) in enumerate(self._spans):
            if x < end:
                return i
        return len(self._spans)

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button != 1:
            return
        index = self.tab_at(event.x)
        if index is None:
            return
        self._dragging = index
        self.capture_mouse()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        index = self._dragging
        if index is None:
            return
        self._dragging = None
        self.capture_mouse(False)
        if self.tab_at(event.x) == index and self.region.contains(
            event.screen_x, event.screen_y
        ):
            # 押したタブの上で離したらクリック
            self.post_message(self.Clicked(self, index))
            return
        try:
            target, _ = self.screen.get_widget_at(event.screen_x, event.screen_y)
        except NoWidget:
            # 画面の外で離した
            return
        target_index = None
        if isinstance(target, TabBar):
            target_index = target.insert_index_at(event.screen_x - target.region.x)
        self.post_message(self.Dropped(self, index, target, target_index))

    def on_mouse_release(self, event: events.MouseRelease) -> None:
        # ほかの理由でキャプチャが外れたら、ドラッグもやめる
        self._dragging = None
