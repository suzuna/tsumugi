"""細いスクロールバー。つまみを背景色ではなく前景色の文字で描く。

Textual 既定のスクロールバーは、つまみを背景色で塗り、端を ▁▂▃ のような部分ブロック
文字でなめらかに見せる。ただ、ターミナルによっては右端の列の背景色をウィンドウの余白まで
伸ばして塗るので、右端のつまみだけ太く見えたり、端の文字とずれて重なったりする。

ここではつまみをマス単位で、縦は █、横は ▄（下半分）の前景色で描く。背景は溝の色だけなので
余白に伸びても太さは変わらず、横も半分の高さになって縦の1マス幅に近い細さになる。
"""

from __future__ import annotations

from rich.color import Color
from rich.segment import Segment, Segments
from rich.style import Style
from textual.scrollbar import ScrollBar, ScrollBarRender

VERTICAL_THUMB = "█"
HORIZONTAL_THUMB = "▄"


class ThinScrollBarRender(ScrollBarRender):
    @classmethod
    def render_bar(
        cls,
        size: int = 25,
        virtual_size: float = 50,
        window_size: float = 20,
        position: float = 0,
        thickness: int = 1,
        vertical: bool = True,
        back_color: Color = Color.parse("#555555"),
        bar_color: Color = Color.parse("bright_magenta"),
    ) -> Segments:
        size = int(size)
        width = thickness if vertical else 1
        blank = " " * width
        glyph = (VERTICAL_THUMB if vertical else HORIZONTAL_THUMB) * width

        upper = Segment(
            blank, Style(bgcolor=back_color, meta={"@mouse.down": "scroll_up"})
        )
        lower = Segment(
            blank, Style(bgcolor=back_color, meta={"@mouse.down": "scroll_down"})
        )
        thumb = Segment(
            glyph,
            Style(color=bar_color, bgcolor=back_color, meta={"@mouse.down": "grab"}),
        )

        if window_size and size and virtual_size and size != virtual_size:
            # 位置と長さの計算は Textual と同じで、マス単位に丸める
            thumb_size = max(1.0, window_size / (virtual_size / size))
            length = min(size, max(1, round(thumb_size)))
            scrollable = virtual_size - window_size
            ratio = position / scrollable if scrollable > 0 else 0.0
            ratio = min(1.0, max(0.0, ratio))
            start = min(size - length, round((size - thumb_size) * ratio))
            start = max(0, start)
            segments = (
                [upper] * start + [thumb] * length + [lower] * (size - start - length)
            )
        else:
            segments = [Segment(blank, Style(bgcolor=back_color))] * size

        if vertical:
            return Segments(segments, new_lines=True)
        return Segments((segments + [Segment.line()]) * thickness, new_lines=False)


def install() -> None:
    ScrollBar.renderer = ThinScrollBarRender
