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


def _row_text(buf: Buffer, y: int) -> str:
    return "".join(seg.text for seg in buf.render_line(y))


async def test_soft_wrap_numbers_only_first_row(tmp_path: Path) -> None:
    from tsumugi.config import Config

    f = tmp_path / "long.txt"
    f.write_text("x" * 100 + "\nshort\n")
    app = TsumugiApp([f], system_clipboard=False, config=Config(soft_wrap=True))
    async with app.run_test(size=(40, 12)) as pilot:
        await pilot.pause()
        buf = editor(app).current
        assert buf.soft_wrap
        # 論理行は3行（最後の空行を含む）、表示行はそれより多い
        assert buf.document.line_count == 3
        assert buf.wrapped_document.height > 3
        sections = len(buf.wrapped_document.get_sections(0))
        assert sections >= 3
        gutter = buf.gutter_width
        # 1行目の最初の表示行だけに番号、続きの行は空欄
        assert _row_text(buf, 0)[:gutter].strip() == "1"
        for y in range(1, sections):
            assert _row_text(buf, y)[:gutter].strip() == ""
        # 次の論理行には 2
        assert _row_text(buf, sections)[:gutter].strip() == "2"
        assert _row_text(buf, sections)[gutter:].startswith("short")
        # 折り返すので横スクロールバーは出ない
        assert not buf.show_horizontal_scrollbar
        # 新しいタブも折り返す
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert editor(app).current.soft_wrap


async def test_no_soft_wrap_by_default(tmp_path: Path) -> None:
    f = tmp_path / "long.txt"
    f.write_text("x" * 100 + "\n")
    app = make_app(f)
    async with app.run_test(size=(40, 12)) as pilot:
        await pilot.pause()
        buf = editor(app).current
        assert not buf.soft_wrap
        assert buf.wrapped_document.height == buf.document.line_count
        assert buf.show_horizontal_scrollbar


async def test_custom_css_is_applied(tmp_path: Path) -> None:
    from textual.color import Color

    from tsumugi.config import Config
    from tsumugi.statusbar import StatusBar

    css = tmp_path / "style.tcss"
    css.write_text(
        "StatusBar { text-style: none; background: #ea7599; color: #ffffff; }\n"
        "EditorScreen #sidebar { border-right: vkey #ea7599; }\n"
        "EditorScreen Buffer { background: #180b33; }\n"
    )
    app = TsumugiApp(
        [], system_clipboard=False, config=Config(explorer_root=tmp_path, css=css)
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        bar = editor(app).query_one(StatusBar)
        assert bar.styles.background == Color.parse("#ea7599")
        assert bar.styles.color == Color.parse("#ffffff")
        assert not bar.styles.text_style.reverse
        edge, color = editor(app).sidebar.styles.border_right
        assert edge == "vkey" and color == Color.parse("#ea7599")
        assert editor(app).current.styles.background == Color.parse("#180b33")


async def test_status_bar_is_reversed_by_default() -> None:
    from tsumugi.statusbar import StatusBar

    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        bar = editor(app).query_one(StatusBar)
        assert bar.styles.text_style.reverse
        # 反転は CSS 側だけで、描画するテキスト自体には付けない
        assert not bar.render().style


async def test_selection_is_readable(tmp_path: Path) -> None:
    # 選択範囲が「反転 + 文字色 ANSI 黒」で描かれると、反転後に読めなくなる
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = editor(app).current
        assert buf is not None
        buf.load_text("abc\ndef")
        buf.selection = Selection((0, 1), (1, 2))
        await pilot.pause()
        selected = [
            seg
            for y in range(2)
            for seg in buf.render_line(y)
            if seg.text.strip() and seg.style and seg.style.reverse
        ]
        texts = "".join(seg.text for seg in selected)
        assert "bc" in texts and "de" in texts
        for seg in selected:
            if seg.text.strip() in ("bc", "de"):
                assert seg.style.color is None or seg.style.color.is_default
