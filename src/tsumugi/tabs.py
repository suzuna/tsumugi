"""micro 風のタブバー。タブが2つ以上のときだけ表示する。"""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.message import Message
from textual.widget import Widget


class TabBar(Widget):
    # 選択中のタブの見た目は component class で付ける（カスタム CSS で変えられるように）
    COMPONENT_CLASSES = {"tab-bar--active"}

    DEFAULT_CSS = """
    TabBar {
        height: 1;
        width: 1fr;
    }
    TabBar > .tab-bar--active {
        text-style: reverse bold;
    }
    """

    class Clicked(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    def __init__(self) -> None:
        super().__init__()
        self._labels: list[str] = []
        self._active = 0
        self._spans: list[tuple[int, int]] = []

    def set_tabs(self, labels: list[str], active: int) -> None:
        self._labels = labels
        self._active = active
        self.display = len(labels) > 1
        self.refresh()

    def render(self) -> Text:
        text = Text(no_wrap=True, overflow="ellipsis")
        self._spans = []
        active_style = self.get_component_rich_style("tab-bar--active")
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
                self.post_message(self.Clicked(i))
                return
