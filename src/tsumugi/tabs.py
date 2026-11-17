"""micro 風のタブバー。既定ではタブが1つでも表示し、hide_single なら2つ以上のときだけ表示する。"""

from __future__ import annotations

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
        text-style: reverse bold;
    }
    TabBar > .tab-bar--unfocused {
        text-style: bold underline;
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
        self._spans: list[tuple[int, int]] = []
        # ドラッグ中のタブの番号
        self._dragging: int | None = None

    def set_tabs(self, labels: list[str], active: int, focused: bool = True) -> None:
        self._labels = labels
        self._active = active
        self._focused = focused
        self.display = len(labels) > (1 if self._hide_single else 0)
        self.refresh()

    def render(self) -> Text:
        text = Text(no_wrap=True, overflow="ellipsis")
        self._spans = []
        active_style = self.get_component_rich_style(
            "tab-bar--active" if self._focused else "tab-bar--unfocused"
        )
        for i, label in enumerate(self._labels):
            chunk = f" {label} "
            start = len(text)
            if i == self._active:
                text.append(chunk, style=active_style)
            else:
                text.append(chunk)
            self._spans.append((start, len(text)))
            text.append(" ")
        return text

    # ---- クリックとドラッグ & ドロップ ----

    def tab_at(self, x: int) -> int | None:
        """x の位置にあるタブの番号。タブの上でなければ None。"""
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
