from textual.pilot import Pilot
from textual.widgets.text_area import Selection

from tsumugi.app import TsumugiApp
from tsumugi.config import Config
from tsumugi.editor import Buffer
from tsumugi.prompt import PromptInput


def make_app() -> TsumugiApp:
    return TsumugiApp([], system_clipboard=False, config=Config(sidebar=False))


def _buffer(app: TsumugiApp, text: str, cursor=(0, 0)) -> Buffer:
    buf = app.editor.current
    buf.text = text
    buf.move_cursor(cursor)
    return buf


async def _enter(pilot: Pilot, app: TsumugiApp, value: str) -> None:
    app.editor.infobar.query_one(PromptInput).value = value
    await pilot.press("enter")
    await pilot.pause()


async def _start(pilot: Pilot, app: TsumugiApp, needle: str, text: str) -> None:
    await pilot.press("ctrl+r")
    await pilot.pause()
    await _enter(pilot, app, needle)
    await _enter(pilot, app, text)


def _message(app: TsumugiApp) -> str:
    return str(app.editor.infobar.query_one("#message").render())


async def test_replace_yes_and_no() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = _buffer(app, "foo foo\nfoo\n")
        await _start(pilot, app, "foo", "bar")
        assert buf.selection == Selection((0, 0), (0, 3))
        await pilot.press("y")
        assert buf.selection == Selection((0, 4), (0, 7))
        await pilot.press("n")
        assert buf.selection == Selection((1, 0), (1, 3))
        await pilot.press("y")
        await pilot.pause()
        assert buf.text == "bar foo\nbar\n"
        assert not app.editor.infobar.active
        assert "Replaced 2 occurrences" in _message(app)
        # y で置き換えたぶんは1件ずつ戻る
        buf.undo()
        assert buf.text == "bar foo\nfoo\n"


async def test_replace_all_is_one_undo() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = _buffer(app, "a x a\nx\na a\n")
        await _start(pilot, app, "a", "bb")
        await pilot.press("n", "a")
        await pilot.pause()
        assert buf.text == "a x bb\nx\nbb bb\n"
        assert "Replaced 3 occurrences" in _message(app)
        buf.undo()
        assert buf.text == "a x a\nx\na a\n"


async def test_replace_esc_keeps_done_ones() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = _buffer(app, "a a a")
        await _start(pilot, app, "a", "b")
        await pilot.press("y", "escape")
        await pilot.pause()
        assert buf.text == "b a a"
        assert not app.editor.infobar.active
        assert "Replaced 1 occurrence" in _message(app)


async def test_replace_only_inside_selection() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = _buffer(app, "aa aa aa")
        buf.selection = Selection((0, 3), (0, 7))  # "aa a"
        await _start(pilot, app, "aa", "b")
        await pilot.press("a")
        await pilot.pause()
        assert buf.text == "aa b aa"


async def test_replace_wraps_from_cursor() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = _buffer(app, "x1\nx2\nx3", cursor=(1, 0))
        await _start(pilot, app, "x", "y")
        assert buf.selection == Selection((1, 0), (1, 1))
        await pilot.press("y", "y")
        assert buf.selection == Selection((0, 0), (0, 1))
        await pilot.press("y")
        await pilot.pause()
        assert buf.text == "y1\ny2\ny3"
        assert not app.editor.infobar.active


async def test_replace_with_text_containing_needle_stops() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = _buffer(app, "aa aa")
        await _start(pilot, app, "aa", "aaa")
        await pilot.press("y", "y")
        await pilot.pause()
        assert buf.text == "aaa aaa"
        assert not app.editor.infobar.active


async def test_replace_all_with_text_containing_needle() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = _buffer(app, "aa aa")
        await _start(pilot, app, "aa", "aaa")
        await pilot.press("a")
        await pilot.pause()
        assert buf.text == "aaa aaa"


async def test_replace_no_matches() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = _buffer(app, "abc")
        await _start(pilot, app, "z", "y")
        assert buf.text == "abc"
        assert not app.editor.infobar.active
        assert "No matches for 'z'" in _message(app)


async def test_replace_with_empty_deletes() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = _buffer(app, "a-b-c")
        await _start(pilot, app, "-", "")
        await pilot.press("a")
        await pilot.pause()
        assert buf.text == "abc"


async def test_replace_empty_needle_cancels() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = _buffer(app, "abc")
        await pilot.press("ctrl+r")
        await pilot.pause()
        await _enter(pilot, app, "")
        assert not app.editor.infobar.active
        assert buf.text == "abc"
        assert "Cancelled" in _message(app)


async def test_find_next_after_replace() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = _buffer(app, "ab ab ab")
        await _start(pilot, app, "ab", "ab")
        await pilot.press("escape")
        await pilot.pause()
        buf.move_cursor((0, 0))
        await pilot.press("ctrl+n")
        assert buf.selection == Selection((0, 0), (0, 2))
        await pilot.press("ctrl+n")
        assert buf.selection == Selection((0, 3), (0, 5))


async def test_replace_keeps_crlf() -> None:
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = _buffer(app, "a\r\nb a\r\na")
        await _start(pilot, app, "a", "c")
        await pilot.press("y", "a")
        await pilot.pause()
        assert buf.text == "c\r\nb c\r\nc"
