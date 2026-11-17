import os
from pathlib import Path

from tsumugi.app import EditorScreen, TsumugiApp
from tsumugi.config import Config
from tsumugi.editor import Buffer
from tsumugi.explorer import FileTree
from tsumugi.tabs import TabBar


def make_app(root: Path, *files: Path) -> TsumugiApp:
    os.chdir(root)
    return TsumugiApp(list(files), system_clipboard=False, config=Config(sidebar=False))


def files(tmp_path: Path, *names: str) -> list[Path]:
    paths = []
    for name in names:
        p = tmp_path / name
        p.write_text(f"{name}\n")
        paths.append(p.resolve())
    return paths


def names(pane) -> list[str]:
    return [b.display_name for b in pane.buffers]


async def settle(pilot) -> None:
    # 分割の切り替えは worker で動くので、終わるまで待つ
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


async def test_toggle_split_cycles(tmp_path: Path) -> None:
    a, b = files(tmp_path, "a.txt", "b.txt")
    app = make_app(tmp_path, a, b)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed: EditorScreen = app.editor
        assert ed.split is None
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        assert ed.split == "horizontal"
        left, right = ed.panes
        assert right.region.x > left.region.x
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        assert ed.split == "vertical"
        top, bottom = ed.panes
        assert bottom.region.y > top.region.y
        assert bottom.region.x == top.region.x
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        assert ed.split is None
        assert len(ed.panes) == 1


async def test_split_moves_current_tab(tmp_path: Path) -> None:
    a, b = files(tmp_path, "a.txt", "b.txt")
    app = make_app(tmp_path, a, b)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        left, right = ed.panes
        assert names(left) == ["a.txt"]
        assert names(right) == ["b.txt"]
        assert ed.active_pane is right
        assert app.focused is right.current
        assert ed.current.path == b


async def test_split_single_tab_opens_untitled(tmp_path: Path) -> None:
    (a,) = files(tmp_path, "a.txt")
    app = make_app(tmp_path, a)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        left, right = ed.panes
        assert names(right) == ["a.txt"]
        assert len(left.buffers) == 1
        assert left.buffers[0].is_pristine_empty
        assert left.current is left.buffers[0]


async def test_unsplit_merges_tabs_and_keeps_edits(tmp_path: Path) -> None:
    a, b, c = files(tmp_path, "a.txt", "b.txt", "c.txt")
    app = make_app(tmp_path, a, b, c)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        await pilot.press("x")
        await pilot.press("ctrl+backslash", "ctrl+backslash")
        await settle(pilot)
        assert ed.split is None
        (pane,) = ed.panes
        assert names(pane) == ["a.txt", "b.txt", "c.txt"]
        cur = ed.current
        assert cur.path == c
        assert cur.text == "xc.txt\n"
        assert cur.dirty
        assert app.focused is cur


async def test_unsplit_drops_untitled_tab(tmp_path: Path) -> None:
    (a,) = files(tmp_path, "a.txt")
    app = make_app(tmp_path, a)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+backslash", "ctrl+backslash", "ctrl+backslash")
        await settle(pilot)
        (pane,) = ed.panes
        assert names(pane) == ["a.txt"]


async def test_moved_tab_keeps_undo_and_state(tmp_path: Path) -> None:
    a, b = files(tmp_path, "a.txt", "b.txt")
    app = make_app(tmp_path, a, b)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        old = ed.current
        await pilot.press("end", "x", "y")
        sig = old.disk_sig
        loc = old.cursor_location
        await pilot.press("ctrl+right_square_bracket")
        await settle(pilot)
        new = ed.current
        assert new is not old
        assert new.path == b
        assert new.text == "b.txtxy\n"
        assert new.dirty
        assert new.disk_sig == sig
        assert new.cursor_location == loc
        assert app.focused is new
        await pilot.press("ctrl+z")
        await pilot.pause()
        assert new.text == "b.txt\n"
        assert not new.dirty


async def test_move_tab_between_panes(tmp_path: Path) -> None:
    a, b, c = files(tmp_path, "a.txt", "b.txt", "c.txt")
    app = make_app(tmp_path, a, b, c)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        # 分割していなければ分割して移す
        await pilot.press("ctrl+right_square_bracket")
        await settle(pilot)
        left, right = ed.panes
        assert names(left) == ["a.txt", "b.txt"]
        assert names(right) == ["c.txt"]
        await pilot.press("ctrl+u")  # 左のペインへ
        await pilot.pause()
        assert ed.active_pane is left
        assert ed.current.path == b
        await pilot.press("ctrl+right_square_bracket")
        await settle(pilot)
        assert names(left) == ["a.txt"]
        assert names(right) == ["c.txt", "b.txt"]
        assert ed.active_pane is right
        assert ed.current.path == b
        # 最後の1枚を移したら分割をやめる
        await pilot.press("ctrl+u")
        await pilot.press("ctrl+right_square_bracket")
        await settle(pilot)
        assert ed.split is None
        (pane,) = ed.panes
        assert names(pane) == ["c.txt", "b.txt", "a.txt"]
        assert not pane.has_class("-second")
        assert ed.current.path == a


async def test_open_file_in_other_pane_switches_there(tmp_path: Path) -> None:
    a, b = files(tmp_path, "a.txt", "b.txt")
    app = make_app(tmp_path, a, b)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        left, right = ed.panes
        await ed.open_path(a)
        await pilot.pause()
        assert ed.active_pane is left
        assert app.focused is left.current
        assert len(ed.buffers) == 2


async def test_new_tab_goes_to_active_pane(tmp_path: Path) -> None:
    a, b = files(tmp_path, "a.txt", "b.txt")
    app = make_app(tmp_path, a, b)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        left, right = ed.panes
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert names(right) == ["b.txt", "No name"]
        # タブの切り替えは今のペインの中だけ
        await pilot.press("ctrl+pageup")
        assert ed.current.path == b
        await pilot.press("ctrl+pageup")
        assert ed.current is right.buffers[1]


async def test_sidebar_opens_in_last_active_pane(tmp_path: Path) -> None:
    a, b = files(tmp_path, "a.txt", "b.txt")
    (tmp_path / "c.txt").write_text("cee")
    app = make_app(tmp_path, a, b)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        left, right = ed.panes
        await pilot.press("ctrl+u")  # 左のペインへ
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = ed.sidebar.query_one(FileTree)
        tree.move_cursor(tree.root.children[2])
        await pilot.press("enter")
        await pilot.pause()
        assert names(left) == ["a.txt", "c.txt"]
        assert names(right) == ["b.txt"]
        assert app.focused is left.current
        assert left.current.path.name == "c.txt"


async def test_switch_pane_skips_sidebar(tmp_path: Path) -> None:
    a, b = files(tmp_path, "a.txt", "b.txt")
    app = make_app(tmp_path, a, b)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        left, right = ed.panes
        assert app.focused is right.current
        await pilot.press("ctrl+u")
        assert app.focused is left.current
        await pilot.press("ctrl+u")
        assert app.focused is right.current
        # サイドバーが出ていても、Ctrl+U はペインの間だけを行き来する
        await pilot.press("ctrl+e")
        await pilot.pause()
        tree = ed.sidebar.query_one(FileTree)
        assert app.focused is tree
        await pilot.press("ctrl+j")
        assert app.focused is right.current
        await pilot.press("ctrl+u")
        assert app.focused is left.current
        await pilot.press("ctrl+u")
        assert app.focused is right.current


async def test_focus_tree_returns_to_last_pane(tmp_path: Path) -> None:
    a, b = files(tmp_path, "a.txt", "b.txt")
    app = make_app(tmp_path, a, b)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        left, right = ed.panes
        await pilot.press("ctrl+u", "ctrl+e")
        await pilot.pause()
        tree = ed.sidebar.query_one(FileTree)
        assert app.focused is tree
        # ツリーから戻ると、最後に操作していた左のペインへ
        await pilot.press("ctrl+j")
        assert app.focused is left.current
        await pilot.press("ctrl+j")
        assert app.focused is tree
        # ツリーから Ctrl+U を押すと、最後のペインではないほうへ
        await pilot.press("ctrl+u")
        assert app.focused is right.current


async def test_closing_last_tab_of_pane_unsplits(tmp_path: Path) -> None:
    a, b = files(tmp_path, "a.txt", "b.txt")
    app = make_app(tmp_path, a, b)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        await pilot.press("ctrl+w")
        await settle(pilot)
        assert ed.split is None
        assert names(ed.panes[0]) == ["a.txt"]
        assert isinstance(app.focused, Buffer)
        assert app.focused.path == a
        assert app.is_running


async def test_active_pane_tab_bar_has_background(tmp_path: Path) -> None:
    a, b = files(tmp_path, "a.txt", "b.txt")
    app = make_app(tmp_path, a, b)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        left, right = ed.panes

        def segments(pane):
            return list(pane.query_one(TabBar).render_line(0))

        def selected_style(pane):
            return next(s for s in segments(pane) if s.text.strip()).style

        def bar_bgcolor(pane):
            # タブより右の、何も描いていない部分の背景
            return segments(pane)[-1].style.bgcolor

        # 操作中のペインのバーだけ背景色が付く
        assert right.query_one(TabBar).has_class("-focused")
        assert not left.query_one(TabBar).has_class("-focused")
        assert not bar_bgcolor(right).is_default
        assert bar_bgcolor(left).is_default
        # 選択タブはどちらのペインでもエディタと同じ背景で、太字・下線・反転は付けない
        for pane in (left, right):
            style = selected_style(pane)
            assert style.bgcolor.is_default
            assert not style.bold
            assert not style.underline
            assert not style.reverse
        await pilot.press("ctrl+u")
        await pilot.pause()
        assert not bar_bgcolor(left).is_default
        assert bar_bgcolor(right).is_default


# ---- ドラッグ & ドロップ ----


def tab_x(pane, index: int) -> int:
    """pane のタブバーで index 番目のタブの中ほどの x（タブバーからの相対）。"""
    start, end = pane.tab_bar._spans[index]
    return (start + end) // 2


async def drag(pilot, src_widget, src_offset, dst_widget, dst_offset) -> None:
    await pilot.mouse_down(src_widget, offset=src_offset)
    await pilot.mouse_up(dst_widget, offset=dst_offset)
    await settle(pilot)


async def test_drag_tab_to_other_tab_bar(tmp_path: Path) -> None:
    a, b, c = files(tmp_path, "a.txt", "b.txt", "c.txt")
    app = make_app(tmp_path, a, b, c)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        left, right = ed.panes
        # 右の c.txt を左の先頭のタブの上へ
        await drag(
            pilot,
            right.tab_bar,
            (tab_x(right, 0), 0),
            left.tab_bar,
            (tab_x(left, 0), 0),
        )
        assert names(left) == ["c.txt", "a.txt", "b.txt"]
        assert ed.split is None  # 右が空になったので分割をやめる
        assert ed.current.path == c


async def test_drag_tab_to_other_editor(tmp_path: Path) -> None:
    a, b, c = files(tmp_path, "a.txt", "b.txt", "c.txt")
    app = make_app(tmp_path, a, b, c)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+backslash")
        await settle(pilot)
        left, right = ed.panes
        # 左の a.txt を右のエディタ部分へ（末尾に入る）
        await drag(pilot, left.tab_bar, (tab_x(left, 0), 0), right.current, (5, 3))
        assert names(left) == ["b.txt"]
        assert names(right) == ["c.txt", "a.txt"]
        assert ed.active_pane is right
        assert app.focused is right.current
        assert ed.current.path == a


async def test_drag_tab_reorders_in_same_bar(tmp_path: Path) -> None:
    a, b, c = files(tmp_path, "a.txt", "b.txt", "c.txt")
    app = make_app(tmp_path, a, b, c)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        (pane,) = ed.panes
        bar = pane.tab_bar
        await drag(pilot, bar, (tab_x(pane, 0), 0), bar, (tab_x(pane, 2), 0))
        assert names(pane) == ["b.txt", "c.txt", "a.txt"]
        assert ed.current.path == a
        # タブより右に落としたら末尾へ
        await drag(pilot, bar, (tab_x(pane, 0), 0), bar, (bar.size.width - 1, 0))
        assert names(pane) == ["c.txt", "a.txt", "b.txt"]


async def test_press_and_release_on_same_tab_is_click(tmp_path: Path) -> None:
    a, b = files(tmp_path, "a.txt", "b.txt")
    app = make_app(tmp_path, a, b)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        (pane,) = ed.panes
        assert ed.current.path == b
        await pilot.click(pane.tab_bar, offset=(tab_x(pane, 0), 0))
        await settle(pilot)
        assert ed.current.path == a
        assert names(pane) == ["a.txt", "b.txt"]


async def test_drop_on_own_editor_does_nothing(tmp_path: Path) -> None:
    a, b = files(tmp_path, "a.txt", "b.txt")
    app = make_app(tmp_path, a, b)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        (pane,) = ed.panes
        await drag(pilot, pane.tab_bar, (tab_x(pane, 0), 0), pane.current, (5, 3))
        assert ed.split is None
        assert names(pane) == ["a.txt", "b.txt"]
        assert ed.current.path == b
