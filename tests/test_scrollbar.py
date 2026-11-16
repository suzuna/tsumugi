from pathlib import Path

import pytest
from textual.scrollbar import ScrollBar

from tsumugi.app import TsumugiApp
from tsumugi.config import Config
from tsumugi.explorer import FileTree
from tsumugi.scrollbar import SolidScrollBarRender

PARTIAL_GLYPHS = set("▁▂▃▄▅▆▇▉▊▋▌▍▎▏")


@pytest.mark.parametrize("vertical", [True, False])
@pytest.mark.parametrize("position", [0, 3.3, 17.6, 50, 80])
def test_thumb_has_no_partial_glyphs(vertical: bool, position: float) -> None:
    segments = SolidScrollBarRender.render_bar(
        size=20, virtual_size=100, window_size=20, position=position, thickness=1, vertical=vertical
    )
    segs = list(segments.segments)
    text = "".join(seg.text for seg in segs)
    assert not PARTIAL_GLYPHS & set(text)
    # つまみ（reverse で塗る部分）が少なくとも1マスある
    assert any(seg.style and seg.style.reverse for seg in segs)


async def test_scrollbars_are_one_cell_and_solid(tmp_path: Path) -> None:
    for i in range(100):
        (tmp_path / f"f{i:03}.txt").write_text("x")
    long = tmp_path / "long.txt"
    long.write_text("\n".join("line " * 40 for _ in range(200)))
    app = TsumugiApp([long], system_clipboard=False, config=Config(explorer_root=tmp_path))
    async with app.run_test(size=(80, 20)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        assert ScrollBar.renderer is SolidScrollBarRender
        buf = app.editor.current
        tree = app.editor.sidebar.query_one(FileTree)
        for widget in (buf, tree):
            assert widget.styles.scrollbar_size_vertical == 1
            assert widget.styles.scrollbar_size_horizontal == 1
        assert buf.show_vertical_scrollbar
        assert tree.show_vertical_scrollbar
