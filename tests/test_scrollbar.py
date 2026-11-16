from pathlib import Path

import pytest
from rich.color import Color
from textual.scrollbar import ScrollBar

from tsumugi.app import TsumugiApp
from tsumugi.config import Config
from tsumugi.explorer import FileTree
from tsumugi.scrollbar import HORIZONTAL_THUMB, VERTICAL_THUMB, ThinScrollBarRender

BAR = Color.parse("blue")
BACK = Color.parse("black")


def _cells(vertical: bool, **kwargs) -> list:
    segments = ThinScrollBarRender.render_bar(
        thickness=1, vertical=vertical, back_color=BACK, bar_color=BAR, **kwargs
    )
    # 改行のセグメントを除いた、1マス分ずつのセグメント
    return [seg for seg in segments.segments if seg.text != "\n"]


@pytest.mark.parametrize("vertical", [True, False])
@pytest.mark.parametrize("position", [0, 3.3, 17.6, 50, 80, 200])
def test_thumb_is_drawn_with_foreground_glyph(vertical: bool, position: float) -> None:
    cells = _cells(
        vertical, size=20, virtual_size=100, window_size=20, position=position
    )
    assert len(cells) == 20
    glyph = VERTICAL_THUMB if vertical else HORIZONTAL_THUMB
    thumb = [c for c in cells if c.text == glyph]
    assert 1 <= len(thumb) <= 20
    # つまみは連続した1本
    first = cells.index(thumb[0])
    assert cells[first : first + len(thumb)] == thumb
    for c in thumb:
        # 背景色で塗らず（reverse なし）、前景色で描く
        assert not c.style.reverse
        assert c.style.color == BAR
        assert c.style.bgcolor == BACK
    # つまみ以外は溝（空白）
    assert all(c.text == " " for c in cells if c.text != glyph)


@pytest.mark.parametrize("vertical", [True, False])
def test_thumb_position_follows_scroll(vertical: bool) -> None:
    glyph = VERTICAL_THUMB if vertical else HORIZONTAL_THUMB
    top = _cells(vertical, size=20, virtual_size=100, window_size=20, position=0)
    bottom = _cells(vertical, size=20, virtual_size=100, window_size=20, position=80)
    assert top[0].text == glyph
    assert bottom[-1].text == glyph


def test_tiny_thumb_is_at_least_one_cell() -> None:
    cells = _cells(True, size=10, virtual_size=100000, window_size=10, position=500)
    assert sum(c.text == VERTICAL_THUMB for c in cells) == 1


def test_no_thumb_when_not_scrollable() -> None:
    cells = _cells(True, size=20, virtual_size=20, window_size=0, position=0)
    assert all(c.text == " " for c in cells)


async def test_scrollbars_are_one_cell_and_thin(tmp_path: Path) -> None:
    for i in range(100):
        (tmp_path / f"f{i:03}.txt").write_text("x")
    long = tmp_path / "long.txt"
    long.write_text("\n".join("line " * 40 for _ in range(200)))
    app = TsumugiApp(
        [long], system_clipboard=False, config=Config(explorer_root=tmp_path)
    )
    async with app.run_test(size=(80, 20)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        assert ScrollBar.renderer is ThinScrollBarRender
        buf = app.editor.current
        tree = app.editor.sidebar.query_one(FileTree)
        for widget in (buf, tree):
            assert widget.styles.scrollbar_size_vertical == 1
            assert widget.styles.scrollbar_size_horizontal == 1
        assert buf.show_vertical_scrollbar
        assert buf.show_horizontal_scrollbar
        assert tree.show_vertical_scrollbar
