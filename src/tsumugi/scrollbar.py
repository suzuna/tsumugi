"""1マス単位で塗りつぶすだけのスクロールバー。

Textual 既定のスクロールバーは、つまみの端を ▁▂▃ のような部分ブロック文字で描いて
なめらかに見せる。ただ、ターミナルの行間やフォントによってはこの文字がマスを埋めず、
つまみがずれて重なったように見える。端の文字をすべて空白にすると Textual は端の描画を
飛ばすので、つまみはマス単位の塗りつぶしだけになる。
"""

from __future__ import annotations

from textual.scrollbar import ScrollBar, ScrollBarRender


class SolidScrollBarRender(ScrollBarRender):
    VERTICAL_BARS = [" "] * 8
    HORIZONTAL_BARS = [" "] * 8


def install() -> None:
    ScrollBar.renderer = SolidScrollBarRender
