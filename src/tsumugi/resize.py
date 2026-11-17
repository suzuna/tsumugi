"""区切り線（枠線）をマウスでドラッグして、サイドバーやペインの大きさを変える。

区切り線は CSS の border で描いているので、そのマスはウィジェット自身の領域に入る。
border のマスで押されたらマウスをつかみ、動くたびに on_edge_drag で大きさを変える。
"""

from __future__ import annotations

from textual import events
from textual.widget import Widget

# ドラッグで狭めるときの最小の大きさ（マス）
SIDEBAR_MIN_WIDTH = 10
# サイドバーを広げても、エディタ側にこれだけは残す
EDITOR_MIN_WIDTH = 20
PANE_MIN_WIDTH = 10
# タブバーと本文2行
PANE_MIN_HEIGHT = 3


class EdgeDrag(Widget):
    """区切り線のマスをつかんでドラッグできるウィジェットの土台。

    is_edge と on_edge_drag を実装する。どちらも画面上の座標で受け取る。
    """

    _edge_dragging = False

    def is_edge(self, screen_x: int, screen_y: int) -> bool:
        """画面上の (screen_x, screen_y) が、つかめる区切り線のマスか。"""
        return False

    def on_edge_drag(self, screen_x: int, screen_y: int) -> None:
        """区切り線を (screen_x, screen_y) まで動かした。"""

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button != 1 or not self.is_edge(event.screen_x, event.screen_y):
            return
        event.stop()
        self._edge_dragging = True
        self.capture_mouse()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if not self._edge_dragging:
            return
        event.stop()
        self.on_edge_drag(event.screen_x, event.screen_y)

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if not self._edge_dragging:
            return
        event.stop()
        self._edge_dragging = False
        self.capture_mouse(False)

    def on_mouse_release(self, event: events.MouseRelease) -> None:
        # ほかの理由でキャプチャが外れたら、ドラッグもやめる
        self._edge_dragging = False


def clamp(value: int, low: int, high: int) -> int:
    """value を low 以上 high 以下にする。high < low なら low。"""
    return max(low, min(value, high))
