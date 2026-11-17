import os
from pathlib import Path

from tsumugi.app import TsumugiApp
from tsumugi.config import Config
from tsumugi.resize import (
    EDITOR_MIN_WIDTH,
    PANE_MIN_HEIGHT,
    PANE_MIN_WIDTH,
    SIDEBAR_MIN_WIDTH,
)

SIZE = (100, 30)


def make_app(root: Path, *names: str, sidebar: bool = False) -> TsumugiApp:
    os.chdir(root)
    paths = []
    for name in names:
        p = root / name
        p.write_text(f"{name}\n")
        paths.append(p)
    return TsumugiApp(paths, system_clipboard=False, config=Config(sidebar=sidebar))


async def settle(pilot) -> None:
    # 分割の切り替えは worker で動くので、終わるまで待つ
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


async def drag(pilot, start: tuple[int, int], end: tuple[int, int]) -> None:
    """画面上の start で押して end まで動かして離す。"""
    await pilot.mouse_down(None, start)
    await pilot.hover(None, end)
    await pilot.mouse_up(None, end)
    await pilot.pause()


async def test_drag_sidebar_border_changes_width(tmp_path: Path) -> None:
    app = make_app(tmp_path, "a.txt", sidebar=True)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(0.3)
        sidebar = app.editor.sidebar
        border = sidebar.region.right - 1
        await drag(pilot, (border, 5), (45, 5))
        # 区切り線がマウスの位置に来る
        assert sidebar.region.right - 1 == 45
        assert sidebar.region.width == 46
        # エディタ側も詰まる
        assert app.editor.editor_area.region.x == 46


async def test_drag_sidebar_stops_at_min_and_max(tmp_path: Path) -> None:
    app = make_app(tmp_path, "a.txt", sidebar=True)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(0.3)
        sidebar = app.editor.sidebar
        await drag(pilot, (sidebar.region.right - 1, 5), (0, 5))
        assert sidebar.region.width == SIDEBAR_MIN_WIDTH
        await drag(pilot, (sidebar.region.right - 1, 5), (SIZE[0] - 1, 5))
        assert sidebar.region.width == SIZE[0] - EDITOR_MIN_WIDTH
        assert app.editor.editor_area.region.width == EDITOR_MIN_WIDTH


async def test_click_inside_sidebar_does_not_resize(tmp_path: Path) -> None:
    app = make_app(tmp_path, "a.txt", sidebar=True)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(0.3)
        sidebar = app.editor.sidebar
        width = sidebar.region.width
        await drag(pilot, (width - 2, 5), (50, 5))
        assert sidebar.region.width == width


async def test_drag_horizontal_split_border(tmp_path: Path) -> None:
    app = make_app(tmp_path, "a.txt", "b.txt")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        left, right = ed.panes
        await drag(pilot, (right.region.x, 10), (30, 10))
        assert left.region.width == 30
        assert right.region.x == 30
        assert right.region.right == SIZE[0]
        # 端まで動かしても最小の幅は残る
        await drag(pilot, (right.region.x, 10), (0, 10))
        assert left.region.width == PANE_MIN_WIDTH
        await drag(pilot, (right.region.x, 10), (SIZE[0] - 1, 10))
        assert right.region.width == PANE_MIN_WIDTH


async def test_drag_vertical_split_border(tmp_path: Path) -> None:
    app = make_app(tmp_path, "a.txt", "b.txt")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        top, bottom = ed.panes
        await drag(pilot, (50, bottom.region.y), (50, 8))
        assert top.region.height == 8
        assert bottom.region.y == 8
        await drag(pilot, (50, bottom.region.y), (50, 0))
        assert top.region.height == PANE_MIN_HEIGHT


async def test_split_size_resets_on_toggle(tmp_path: Path) -> None:
    app = make_app(tmp_path, "a.txt", "b.txt")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        left, right = ed.panes
        await drag(pilot, (right.region.x, 10), (30, 10))
        assert left.region.width == 30
        # 上下にすると半分ずつに戻る
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        top, bottom = ed.panes
        assert top.region.width == bottom.region.width == SIZE[0]
        assert abs(top.region.height - bottom.region.height) <= 1
        # 分割をやめると、残ったペインが全体に広がる
        await drag(pilot, (50, bottom.region.y), (50, 8))
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        (only,) = ed.panes
        assert only.region.width == SIZE[0]
        assert only.region.height == ed.editor_area.region.height
        # もう一度分割したら半分ずつ
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        left, right = ed.panes
        assert abs(left.region.width - right.region.width) <= 1


async def test_click_on_first_pane_column_does_not_resize(tmp_path: Path) -> None:
    app = make_app(tmp_path, "a.txt", "b.txt")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        left, right = ed.panes
        width = left.region.width
        # 1つ目のペインの左端には区切り線がない
        await drag(pilot, (0, 10), (30, 10))
        assert left.region.width == width
        # 2つ目のペインの区切り線以外も
        await drag(pilot, (right.region.x + 3, 10), (30, 10))
        assert left.region.width == width
