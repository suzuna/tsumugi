"""ディレクトリを開く（Ctrl+O、ツリーの o / Backspace）。起点とカレントディレクトリがそろって変わる。"""

import os
from pathlib import Path

import pytest

from tsumugi.app import TsumugiApp
from tsumugi.config import Config
from tsumugi.explorer import ExplorerScreen, FileTree
from tsumugi.prompt import PromptInput
from tsumugi.statusbar import StatusBar


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "proj" / "src").mkdir(parents=True)
    (tmp_path / "proj" / "a.md").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    return tmp_path


def make_app(root: Path, *files: Path) -> TsumugiApp:
    os.chdir(root)
    return TsumugiApp(list(files), system_clipboard=False, config=Config())


def _message(app: TsumugiApp) -> str:
    return str(app.editor.infobar.query_one("#message").render())


def _prompt_label(app: TsumugiApp) -> str:
    return str(app.editor.infobar.query_one("#prompt-label").render())


def _sidebar_tree(app: TsumugiApp) -> FileTree:
    return app.editor.sidebar.query_one(FileTree)


async def _open_dir(pilot, app: TsumugiApp, text: str) -> None:
    await pilot.press("ctrl+o")
    await pilot.pause()
    assert _prompt_label(app) == "Open directory: "
    app.editor.infobar.query_one(PromptInput).value = text
    await pilot.press("enter")
    await pilot.pause()


async def test_ctrl_o_prompt_starts_with_current_root(root: Path) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+o")
        await pilot.pause()
        value = app.editor.infobar.query_one(PromptInput).value
        assert Path(value).expanduser() == root
        assert value.endswith("/")


async def test_ctrl_o_opens_absolute_directory(root: Path) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_dir(pilot, app, str(root / "proj"))
        assert app.editor.explorer_root == root / "proj"
        assert app.editor.cwd == root / "proj"
        assert Path.cwd() == root / "proj"


async def test_ctrl_o_relative_path_is_from_current_root(root: Path) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_dir(pilot, app, "proj/src")
        assert Path.cwd() == root / "proj" / "src"
        await _open_dir(pilot, app, "..")
        assert Path.cwd() == root / "proj"


async def test_ctrl_o_expands_tilde(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(root))
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_dir(pilot, app, "~/proj")
        assert Path.cwd() == root / "proj"


@pytest.mark.parametrize("name", ["b.txt", "nope"])
async def test_ctrl_o_rejects_non_directory(root: Path, name: str) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_dir(pilot, app, name)
        assert "is not a directory" in _message(app)
        assert app.editor.explorer_root == root
        assert Path.cwd() == root


async def test_ctrl_o_empty_cancels(root: Path) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_dir(pilot, app, "  ")
        assert _message(app) == "Cancelled"
        assert Path.cwd() == root


async def test_ctrl_o_switches_visible_sidebar(root: Path) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        await _open_dir(pilot, app, "proj")
        assert app.editor.sidebar_visible
        assert _sidebar_tree(app).path == root / "proj"
        # ツリーから開いたので、フォーカスはツリーに戻る
        assert app.focused is _sidebar_tree(app)


async def test_ctrl_o_keeps_hidden_sidebar_hidden(root: Path) -> None:
    app = make_app(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e", "ctrl+e")  # 一度出して隠す
        await pilot.pause()
        await _open_dir(pilot, app, "proj")
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
        await _open_dir(pilot, app, "proj")
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
        assert app.screen.root == root / "proj"
        await pilot.press("escape")
        await pilot.pause()
        assert app.editor.explorer_root == root / "proj"
        assert Path.cwd() == root / "proj"


async def test_overlay_backspace_changes_cwd(root: Path) -> None:
    app = make_app(root / "proj")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+b")
        await pilot.pause()
        await pilot.press("backspace", "escape")
        await pilot.pause()
        assert Path.cwd() == root


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
