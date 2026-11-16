from pathlib import Path

from textual.widgets.text_area import Selection

from tsumugi.app import EditorScreen, TsumugiApp
from tsumugi.editor import Buffer
from tsumugi.explorer import ExplorerScreen, FileTree
from tsumugi.help import HelpScreen
from tsumugi.prompt import InfoBar
from tsumugi.tabs import TabBar


def make_app(*files: Path) -> TsumugiApp:
    return TsumugiApp(list(files), system_clipboard=False)


def editor(app: TsumugiApp) -> EditorScreen:
    return app.editor


async def test_open_edit_save(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("hello\n")
    app = make_app(f)
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = editor(app).current
        assert buf is not None and buf.path == f
        await pilot.press("end", "x", "y")
        assert buf.dirty
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert f.read_text() == "helloxy\n"
        assert not buf.dirty


async def test_save_untitled_asks_filename(tmp_path: Path) -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a", "b", "ctrl+s")
        assert editor(app).infobar.active
        target = tmp_path / "new.txt"
        for ch in str(target):
            await pilot.press(ch if ch.isalnum() else _key(ch))
        await pilot.press("enter")
        await pilot.pause()
        assert target.read_text() == "ab"


def _key(ch: str) -> str:
    return {"/": "slash", ".": "full_stop", "_": "underscore", "-": "minus"}[ch]


async def test_copy_cut_paste_line() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = editor(app).current
        buf.text = "one\ntwo\n"
        buf.move_cursor((0, 0))
        await pilot.press("ctrl+k")
        assert buf.text == "two\n"
        assert app.clipboard == "one\n"
        await pilot.press("ctrl+v")
        assert buf.text == "one\ntwo\n"
        buf.move_cursor((1, 0))
        await pilot.press("ctrl+c")
        assert app.clipboard == "two\n"
        await pilot.press("ctrl+d")
        assert buf.text == "one\ntwo\ntwo\n"
        await pilot.press("ctrl+z")
        assert buf.text == "one\ntwo\n"


async def test_select_all() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = editor(app).current
        buf.text = "abc\ndef"
        await pilot.press("ctrl+a")
        assert buf.selected_text == "abc\ndef"


async def test_find() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = editor(app).current
        buf.text = "foo\nbar\nfoo bar\n"
        buf.move_cursor((0, 0))
        await pilot.press("ctrl+f", "b", "a", "r")
        assert buf.selection == Selection((1, 0), (1, 3))
        await pilot.press("enter")
        assert not editor(app).infobar.active
        assert buf.has_focus
        await pilot.press("ctrl+n")
        assert buf.selection == Selection((2, 4), (2, 7))
        await pilot.press("ctrl+n")  # 折り返して先頭側へ
        assert buf.selection == Selection((1, 0), (1, 3))
        await pilot.press("ctrl+p")
        assert buf.selection == Selection((2, 4), (2, 7))


async def test_explorer_opens_file_in_new_tab(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("bee")
    first = tmp_path / "a.txt"
    first.write_text("aaa")
    app = make_app(first)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = editor(app)
        ed.explorer_root = tmp_path / "sub"
        await pilot.press("ctrl+b")
        await pilot.pause()
        assert isinstance(app.screen, ExplorerScreen)
        tree = app.screen.query_one(FileTree)
        await pilot.pause(0.3)
        # 先頭の子ノード（b.txt）を選択
        tree.move_cursor(tree.root.children[0])
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen is ed
        assert len(ed.buffers) == 2
        assert ed.current.path == (tmp_path / "sub" / "b.txt").resolve()
        assert ed.current.text == "bee"
        assert ed.query_one(TabBar).display


async def test_explorer_parent_and_close(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = editor(app)
        ed.explorer_root = tmp_path / "sub"
        await pilot.press("ctrl+b")
        await pilot.pause()
        await pilot.press("backspace")
        assert app.screen.root == tmp_path
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is ed
        assert ed.explorer_root == tmp_path  # 次回は前回の場所から


async def test_explorer_default_root_is_home() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+b")
        await pilot.pause()
        assert app.screen.root == Path.home()


async def test_open_replaces_empty_untitled(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x")
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = editor(app)
        await ed.open_path(f)
        await pilot.pause()
        assert len(ed.buffers) == 1
        await ed.open_path(f)  # 2回開いても増えない
        assert len(ed.buffers) == 1


async def test_tabs_cycle_and_close_with_confirm(tmp_path: Path) -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = editor(app)
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert len(ed.buffers) == 2
        second = ed.current
        await pilot.press("ctrl+pageup")
        assert ed.current is ed.buffers[0]
        await pilot.press("ctrl+pagedown")
        assert ed.current is second
        await pilot.press("z", "ctrl+q")
        assert ed.infobar.active
        await pilot.press("escape")  # キャンセル
        assert len(ed.buffers) == 2
        await pilot.press("ctrl+q", "n")
        await pilot.pause()
        assert len(ed.buffers) == 1
        await pilot.press("ctrl+q")
        await pilot.pause()
    assert app.return_code == 0


async def test_close_dirty_and_save(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("")
    app = make_app(f)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("q", "ctrl+q", "y")
        await pilot.pause()
    assert f.read_text() == "q"


async def test_help() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+g")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, EditorScreen)
        assert isinstance(app.focused, Buffer)


async def test_status_bar_hides_tabbar_for_single_buffer() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert not editor(app).query_one(TabBar).display
        assert editor(app).query_one(InfoBar)


async def test_line_numbers_have_left_space(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("hello\nworld\n")
    app = make_app(f)
    async with app.run_test(size=(40, 10)) as pilot:
        await pilot.pause()
        buf = editor(app).current
        assert buf.styles.padding.left == 1
        # 行番号を含む中身は、ウィジェットの左端から1マス右から始まる
        assert buf.content_region.x - buf.region.x == 1
        # 中身の1行目は行番号から始まる
        text = "".join(seg.text for seg in buf.render_line(0))
        assert text.startswith("1 ")
        # クリックした位置がずれない（padding を考慮）
        await pilot.click(buf, offset=(1 + buf.gutter_width + 3, 0))
        assert buf.cursor_location == (0, 3)
