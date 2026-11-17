"""ディレクトリを開く（オーバーレイの g、ツリーの o / Backspace）。起点とカレントディレクトリがそろって変わる。"""

import os
from pathlib import Path

import pytest

from tsumugi.app import TsumugiApp
from tsumugi.config import Config
from tsumugi.explorer import ExplorerScreen, FileTree, GoToBar, GoToInput
from tsumugi.statusbar import StatusBar


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "proj" / "src").mkdir(parents=True)
    (tmp_path / "proj" / "a.md").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    return tmp_path


def make_app(root: Path, *files: Path) -> TsumugiApp:
    os.chdir(root)
    return TsumugiApp(list(files), system_clipboard=False, config=Config(sidebar=False))


def _sidebar_tree(app: TsumugiApp) -> FileTree:
    return app.editor.sidebar.query_one(FileTree)


async def test_overlay_g_keeps_hidden_sidebar_hidden(root: Path) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e", "ctrl+e")  # 一度出して隠す
        await pilot.pause()
        await _go_to(pilot, app, "proj")
        assert not app.editor.sidebar_visible
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        assert _sidebar_tree(app).path == root / "proj"


async def test_status_bar_path_follows_opened_directory(root: Path) -> None:
    app = make_app(root, root / "proj" / "a.md")
    async with app.run_test(size=(80, 10)) as pilot:
        await pilot.pause()
        bar = app.editor.query_one(StatusBar)
        assert bar.render().plain.startswith(" proj/a.md ")
        await _go_to(pilot, app, "proj")
        assert bar.render().plain.startswith(" a.md ")


async def test_sidebar_o_opens_directory_under_cursor(root: Path) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = _sidebar_tree(app)
        assert tree.select_path(root / "proj")
        await pilot.press("o")
        await pilot.pause(0.3)
        assert tree.path == root / "proj"
        assert app.editor.explorer_root == root / "proj"
        assert Path.cwd() == root / "proj"


async def test_sidebar_o_on_file_does_nothing(root: Path) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = _sidebar_tree(app)
        assert tree.select_path(root / "b.txt")
        await pilot.press("o")
        await pilot.pause()
        assert tree.path == root
        assert Path.cwd() == root


async def test_sidebar_backspace_changes_cwd(root: Path) -> None:
    app = make_app(root / "proj")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        await pilot.press("backspace")
        await pilot.pause()
        assert app.editor.explorer_root == root
        assert Path.cwd() == root


async def test_overlay_o_opens_directory_under_cursor(root: Path) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+b")
        await pilot.pause(0.3)
        assert isinstance(app.screen, ExplorerScreen)
        assert app.screen.query_one(FileTree).select_path(root / "proj")
        await pilot.press("o")
        await pilot.pause()
        # o だけで閉じて、メイン画面がそのディレクトリになる
        assert not isinstance(app.screen, ExplorerScreen)
        assert app.editor.explorer_root == root / "proj"
        assert Path.cwd() == root / "proj"


async def test_overlay_o_on_file_keeps_overlay(root: Path) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+b")
        await pilot.pause(0.3)
        assert app.screen.query_one(FileTree).select_path(root / "b.txt")
        await pilot.press("o")
        await pilot.pause()
        assert isinstance(app.screen, ExplorerScreen)
        assert app.screen.root == root
        assert Path.cwd() == root


async def test_overlay_backspace_changes_cwd(root: Path) -> None:
    app = make_app(root / "proj")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+b")
        await pilot.pause()
        await pilot.press("backspace", "escape")
        await pilot.pause()
        assert Path.cwd() == root


async def test_overlay_backspace_moves_sidebar_root(root: Path) -> None:
    app = make_app(root / "proj")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = _sidebar_tree(app)
        assert tree.path == root / "proj"
        await pilot.press("ctrl+b")
        await pilot.pause(0.3)
        assert isinstance(app.screen, ExplorerScreen)
        await pilot.press("backspace", "escape")
        await pilot.pause(0.3)
        assert Path.cwd() == root
        assert tree.path == root


async def test_opening_file_keeps_root(root: Path) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+b")
        await pilot.pause(0.3)
        tree = app.screen.query_one(FileTree)
        tree.select_path(root / "b.txt")
        await pilot.press("enter")
        await pilot.pause()
        assert app.editor.current.path == root / "b.txt"
        assert app.editor.explorer_root == root
        assert Path.cwd() == root


# ---- オーバーレイの g（パスを入れてディレクトリを開く） ----


def _goto_bar(app: TsumugiApp) -> GoToBar:
    return app.screen.query_one(GoToBar)


async def _open_goto(pilot, app: TsumugiApp) -> None:
    await pilot.press("ctrl+b")
    await pilot.pause(0.3)
    assert isinstance(app.screen, ExplorerScreen)
    await pilot.press("g")
    await pilot.pause()
    assert _goto_bar(app).visible


async def _go_to(pilot, app: TsumugiApp, text: str) -> None:
    await _open_goto(pilot, app)
    app.screen.query_one(GoToInput).value = text
    await pilot.press("enter")
    await pilot.pause(0.3)


async def test_overlay_g_starts_with_current_root(root: Path) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_goto(pilot, app)
        inp = app.screen.query_one(GoToInput)
        assert app.focused is inp
        assert Path(inp.value).expanduser() == root
        assert inp.value.endswith("/")


async def test_overlay_g_opens_absolute_directory(root: Path) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _go_to(pilot, app, str(root / "proj"))
        # Enter で確定したら閉じて、メイン画面がそのディレクトリになる
        assert not isinstance(app.screen, ExplorerScreen)
        assert app.editor.explorer_root == root / "proj"
        assert Path.cwd() == root / "proj"


async def test_overlay_g_relative_path_is_from_overlay_root(root: Path) -> None:
    app = make_app(root / "proj")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+b")
        await pilot.pause(0.3)
        # オーバーレイの中で親へ上がってから入れると、上がった先から数える
        await pilot.press("backspace", "g")
        await pilot.pause()
        app.screen.query_one(GoToInput).value = "proj/src"
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert Path.cwd() == root / "proj" / "src"


async def test_overlay_g_expands_tilde(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(root))
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _go_to(pilot, app, "~/proj")
        assert Path.cwd() == root / "proj"


@pytest.mark.parametrize("name", ["b.txt", "nope"])
async def test_overlay_g_rejects_non_directory(root: Path, name: str) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _go_to(pilot, app, name)
        # エラーを出して、オーバーレイも入力欄も開いたまま
        assert isinstance(app.screen, ExplorerScreen)
        assert _goto_bar(app).visible
        error = str(app.screen.query_one("#goto-error").render())
        assert "is not a directory" in error
        assert app.screen.root == root
        assert Path.cwd() == root


async def test_overlay_g_switches_sidebar(root: Path) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        await _go_to(pilot, app, "proj")
        assert app.editor.sidebar_visible
        assert _sidebar_tree(app).path == root / "proj"


async def test_overlay_g_escape_closes_bar_then_overlay(root: Path) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_goto(pilot, app)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ExplorerScreen)
        assert not _goto_bar(app).visible
        assert app.focused is app.screen.query_one(FileTree)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ExplorerScreen)
        assert Path.cwd() == root


async def test_overlay_g_tree_keys_do_not_fire_while_typing(root: Path) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_goto(pilot, app)
        screen = app.screen
        assert isinstance(screen, ExplorerScreen)
        inp = screen.query_one(GoToInput)
        inp.value = ""
        await pilot.press("o", "s", "full_stop", "g", "backspace")
        await pilot.pause()
        assert inp.value == "os."
        assert screen.root == root
        assert not screen.sort_desc
        assert not screen.show_hidden
