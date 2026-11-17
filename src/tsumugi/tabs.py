"""micro 風のタブバー。既定ではタブが1つでも表示し、hide_single なら2つ以上のときだけ表示する。"""

from __future__ import annotations

from rich.text import Text
from textual import events
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

    def __init__(self, hide_single: bool = False) -> None:
        super().__init__()
        self._hide_single = hide_single
        self._labels: list[str] = []
        self._active = 0
        self._focused = True
        self._spans: list[tuple[int, int]] = []

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

    def on_click(self, event: events.Click) -> None:
        for i, (start, end) in enumerate(self._spans):
            if start <= event.x < end:
                self.post_message(self.Clicked(self, i))
                return
