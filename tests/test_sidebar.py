import os
from pathlib import Path

from tsumugi.app import TsumugiApp
from tsumugi.config import Config
from tsumugi.editor import Buffer
from tsumugi.explorer import ExplorerScreen, FileTree
from tsumugi.tabs import TabBar


def make_app(root: Path, *files: Path) -> TsumugiApp:
    os.chdir(root)
    return TsumugiApp(list(files), system_clipboard=False, config=Config(sidebar=False))


def _tree(app: TsumugiApp) -> FileTree:
    return app.editor.sidebar.query_one(FileTree)


async def test_toggle_sidebar(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        assert not ed.sidebar_visible
        await pilot.press("ctrl+e")
        await pilot.pause()
        assert ed.sidebar_visible
        assert ed.sidebar.display
        assert app.focused is _tree(app)
        assert _tree(app).path == tmp_path
        await pilot.press("ctrl+e")
        await pilot.pause()
        assert not ed.sidebar_visible
        assert not ed.sidebar.display
        assert isinstance(app.focused, Buffer)


async def test_switch_pane(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+w")  # サイドバーが出てないときは何もしない
        assert isinstance(app.focused, Buffer)
        await pilot.press("ctrl+e")
        await pilot.pause()
        assert app.focused is _tree(app)
        await pilot.press("ctrl+w")
        assert isinstance(app.focused, Buffer)
        await pilot.press("ctrl+w")
        assert app.focused is _tree(app)


async def test_select_file_opens_tab_and_keeps_focus(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("aaa")
    (tmp_path / "b.txt").write_text("bee")
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.editor
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = _tree(app)
        tree.move_cursor(tree.root.children[0])
        await pilot.press("enter")
        await pilot.pause()
        # 空の無題バッファは置き換え
        assert len(ed.buffers) == 1
        assert ed.current.path == (tmp_path / "a.txt").resolve()
        assert app.focused is tree
        await pilot.press("down", "enter")
        await pilot.pause()
        assert len(ed.buffers) == 2
        assert ed.current.text == "bee"
        assert ed.query_one(TabBar).display
        assert app.focused is tree
        # 開いてるファイルをもう一度選ぶとそのタブへ
        await pilot.press("up", "enter")
        await pilot.pause()
        assert len(ed.buffers) == 2
        assert ed.current.path == (tmp_path / "a.txt").resolve()


async def test_sidebar_parent_updates_overlay_root(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    app = make_app(sub)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause()
        await pilot.press("backspace")
        await pilot.pause()
        assert _tree(app).path == tmp_path
        assert app.editor.explorer_root == tmp_path
        await pilot.press("ctrl+w", "ctrl+b")
        await pilot.pause()
        assert isinstance(app.screen, ExplorerScreen)
        assert app.screen.root == tmp_path


async def test_sidebar_follows_overlay_when_reshown(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    app = make_app(sub)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e", "ctrl+e")  # 一度出して隠す
        await pilot.press("ctrl+b")
        await pilot.pause()
        await pilot.press("backspace", "escape")
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause()
        assert _tree(app).path == tmp_path


async def test_sidebar_disabled_while_prompting(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+f", "ctrl+e")
        await pilot.pause()
        assert not app.editor.sidebar_visible


async def test_sidebar_open_at_startup_focuses_tree(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    app = TsumugiApp([], system_clipboard=False, config=Config(sidebar=True))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.editor.sidebar_visible
        assert app.focused is _tree(app)
        assert _tree(app).path == tmp_path


async def test_sidebar_open_at_startup_with_file_focuses_editor(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("a")
    os.chdir(tmp_path)
    app = TsumugiApp([f], system_clipboard=False, config=Config(sidebar=True))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.editor.sidebar_visible
        assert isinstance(app.focused, Buffer)
        assert app.editor.current.path == f.resolve()


async def test_sidebar_open_at_startup_by_default(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    app = TsumugiApp([], system_clipboard=False, config=Config())
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.editor.sidebar_visible
        assert app.focused is _tree(app)


async def test_sidebar_closed_at_startup_when_disabled(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    app = TsumugiApp([], system_clipboard=False, config=Config(sidebar=False))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert not app.editor.sidebar_visible
        assert isinstance(app.focused, Buffer)
