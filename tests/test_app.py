import os
from pathlib import Path

import pytest
from textual.widgets.text_area import Selection

from tsumugi.app import EditorScreen, TsumugiApp, UsageError, parse_args
from tsumugi.config import Config
from tsumugi.editor import Buffer
from tsumugi.explorer import ExplorerScreen, FileTree
from tsumugi.help import HelpScreen
from tsumugi.prompt import InfoBar
from tsumugi.tabs import TabBar


def make_app(*files: Path) -> TsumugiApp:
    return TsumugiApp(list(files), system_clipboard=False, config=Config(sidebar=False))


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


async def test_enter_keeps_indent() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = editor(app).current
        buf.text = "def hoge(x, y):\n  tmp = x + y"
        buf.move_cursor((1, len("  tmp = x + y")))
        await pilot.press("enter")
        assert buf.text == "def hoge(x, y):\n  tmp = x + y\n  "
        assert buf.cursor_location == (2, 2)
        # 空白だけの行で改行すると、その行の空白は消える
        await pilot.press("enter")
        assert buf.text == "def hoge(x, y):\n  tmp = x + y\n\n  "
        assert buf.cursor_location == (3, 2)


async def test_enter_keeps_tab_indent() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = editor(app).current
        buf.text = "\tfoo"
        buf.move_cursor((0, 4))
        await pilot.press("enter")
        assert buf.text == "\tfoo\n\t"


async def test_enter_inside_indent() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = editor(app).current
        buf.text = "  tmp"
        buf.move_cursor((0, 1))
        await pilot.press("enter")
        # カーソルより左の分だけ引き継ぐので、インデントは増えない
        assert buf.text == " \n  tmp"
        assert buf.cursor_location == (1, 1)


async def test_enter_replaces_selection_with_indent() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = editor(app).current
        buf.text = "  foo bar"
        buf.selection = Selection((0, 5), (0, 9))
        await pilot.press("enter")
        assert buf.text == "  foo\n  "
        assert buf.selection.is_empty
        assert buf.cursor_location == (1, 2)


async def test_enter_indent_undo_at_once() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = editor(app).current
        buf.text = "  a\n  "
        buf.move_cursor((1, 2))
        await pilot.press("enter")
        assert buf.text == "  a\n\n  "
        await pilot.press("ctrl+z")
        assert buf.text == "  a\n  "


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


async def test_explorer_root_is_cwd(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+b")
        await pilot.pause()
        assert app.screen.root == tmp_path.resolve()


def test_parse_args_without_args() -> None:
    assert parse_args([]) == ([], None)


def test_parse_args_files_become_absolute(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    (tmp_path / "a.txt").write_text("a")
    files, root = parse_args(["a.txt", "new.txt"])
    assert files == [tmp_path / "a.txt", tmp_path / "new.txt"]
    assert all(f.is_absolute() for f in files)
    assert root is None


def test_parse_args_directory_becomes_root(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    (tmp_path / "proj").mkdir()
    # ファイルはディレクトリではなく、シェルのカレントディレクトリから数える
    files, root = parse_args(["proj", "a.txt"])
    assert root == tmp_path / "proj"
    assert files == [tmp_path / "a.txt"]


def test_parse_args_rejects_two_directories(tmp_path: Path) -> None:
    (tmp_path / "d1").mkdir()
    (tmp_path / "d2").mkdir()
    with pytest.raises(UsageError):
        parse_args([str(tmp_path / "d1"), str(tmp_path / "d2")])


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
        await pilot.press("z", "ctrl+w")
        assert ed.infobar.active
        await pilot.press("escape")  # キャンセル
        assert len(ed.buffers) == 2
        await pilot.press("ctrl+w", "n")
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
        await pilot.press("q", "ctrl+w", "y")
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


async def test_tabbar_shown_for_single_buffer() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert editor(app).query_one(TabBar).display
        assert editor(app).query_one(InfoBar)


async def test_hide_single_tab_hides_tabbar_until_two_tabs() -> None:
    app = TsumugiApp(
        [], system_clipboard=False, config=Config(sidebar=False, hide_single_tab=True)
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert not editor(app).query_one(TabBar).display
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert editor(app).query_one(TabBar).display


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
    app = TsumugiApp(
        [f], system_clipboard=False, config=Config(sidebar=False, soft_wrap=True)
    )
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
    os.chdir(tmp_path)
    app = TsumugiApp([], system_clipboard=False, config=Config(sidebar=False, css=css))
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


async def test_active_tab_style_comes_from_css(tmp_path: Path) -> None:
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("a")
    b.write_text("b")
    css = tmp_path / "style.tcss"
    css.write_text(
        "TabBar { background: #ea7599; color: #ffffff; }\n"
        "TabBar > .tab-bar--active { text-style: underline; }\n"
    )
    app = TsumugiApp(
        [a, b], system_clipboard=False, config=Config(sidebar=False, css=css)
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        segments = {
            seg.text.strip(): seg.style
            for seg in editor(app).query_one(TabBar).render_line(0)
            if seg.text.strip()
        }
        # 選択中（最後に開いた b.txt）だけ CSS の指定が付き、バーの色は全体に効く
        assert segments["b.txt"].underline
        assert not segments["a.txt"].underline
        assert segments["a.txt"].bgcolor.triplet.hex == "#ea7599"


async def test_help_key_color_comes_from_css(tmp_path: Path) -> None:
    from tsumugi.help import HelpText

    css = tmp_path / "style.tcss"
    css.write_text("HelpText > .help--key { color: #ea7599; }\n")
    os.chdir(tmp_path)
    app = TsumugiApp([], system_clipboard=False, config=Config(sidebar=False, css=css))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+g")
        await pilot.pause()
        text = app.screen.query_one(HelpText).render()
        colors = {
            text.plain[span.start : span.end].strip(): span.style.color
            for span in text.spans
            if not isinstance(span.style, str) and span.style.color is not None
        }
        assert colors["Ctrl+S"].triplet.hex == "#ea7599"
        assert "Save" not in colors


async def _keys_at_once(pilot, app: TsumugiApp, *keys: tuple[str, str | None]) -> None:
    """ターミナルから1回の読み込みでまとめて届いたときのように、キーを一度に積む。"""
    from textual import events

    for key, char in keys:
        app.post_message(events.Key(key, char))
    await pilot.pause()
    await pilot.pause()


async def test_save_waits_for_keys_sent_together(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("one\n")
    app = make_app(f)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _keys_at_once(pilot, app, ("x", "x"), ("ctrl+s", None))
        assert f.read_text() == "xone\n"
        assert not editor(app).current.dirty


async def test_close_tab_waits_for_keys_sent_together(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("one\n")
    app = make_app(f)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _keys_at_once(pilot, app, ("x", "x"), ("ctrl+w", None))
        # x が入ってから閉じようとするので、保存するか聞かれる
        ed = editor(app)
        assert ed.infobar.active
        assert "Save changes" in str(ed.infobar.query_one("#prompt-label").render())


async def test_find_waits_for_keys_sent_together(tmp_path: Path) -> None:
    from tsumugi.prompt import PromptInput

    f = tmp_path / "a.txt"
    f.write_text("ab ab")
    app = make_app(f)
    async with app.run_test() as pilot:
        await pilot.pause()
        # → で1つ進んでから検索するので、先頭の ab ではなく次の ab が見つかる
        await _keys_at_once(pilot, app, ("right", None), ("ctrl+f", None))
        ed = editor(app)
        ed.infobar.query_one(PromptInput).value = "ab"
        await pilot.press("enter")
        await pilot.pause()
        assert ed.current.selection == Selection((0, 3), (0, 5))


async def test_save_waits_for_bound_keys_sent_together(tmp_path: Path) -> None:
    # Backspace のようにバインディングで動くキーは App まで上がってから実行される
    f = tmp_path / "a.txt"
    f.write_text("one")
    app = make_app(f)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _keys_at_once(
            pilot, app, ("end", None), ("backspace", None), ("ctrl+s", None)
        )
        assert f.read_text() == "on"
        assert not editor(app).current.dirty


async def test_copy_path_of_current_file(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("a")
    app = make_app(f)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+l")
        assert app.clipboard == str(f.resolve())


async def test_copy_path_of_untitled_does_nothing(tmp_path: Path) -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.copy_to_clipboard("before")
        await pilot.press("ctrl+l")
        assert app.clipboard == "before"


async def test_copy_path_ignored_while_prompting(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("a")
    app = make_app(f)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.copy_to_clipboard("before")
        await pilot.press("ctrl+f")
        await pilot.pause()
        await pilot.press("ctrl+l")
        assert app.clipboard == "before"


async def test_copy_path_in_sidebar_tree(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    os.chdir(tmp_path)
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = app.editor.sidebar.query_one(FileTree)
        assert app.focused is tree
        await pilot.press("ctrl+l")
        assert app.clipboard == str((tmp_path / "sub").resolve())


async def test_copy_path_in_explorer_overlay(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("b")
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        editor(app).explorer_root = tmp_path
        await pilot.press("ctrl+b")
        await pilot.pause(0.3)
        assert isinstance(app.screen, ExplorerScreen)
        await pilot.press("ctrl+l")
        assert app.clipboard == str((tmp_path / "b.txt").resolve())
        assert isinstance(app.screen, ExplorerScreen)  # 閉じない
