from pathlib import Path

import pytest

from tsumugi.app import TsumugiApp
from tsumugi.config import Config
from tsumugi.explorer import FileTree


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "inner.txt").write_text("i")
    (tmp_path / "a.txt").write_text("a")
    return tmp_path


async def _open_sidebar(root: Path):
    app = TsumugiApp([], system_clipboard=False, config=Config(explorer_root=root))
    return app


def _labels(tree: FileTree) -> list[str]:
    return [tree.render_label(line.node, tree.rich_style, tree.rich_style).plain for line in tree._tree_lines]


async def test_labels_use_micro_notation(root: Path) -> None:
    app = await _open_sidebar(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = app.editor.sidebar.query_one(FileTree)
        assert _labels(tree) == ["+ sub/", "  a.txt"]
        tree.cursor_node.expand()
        await pilot.pause(0.3)
        assert _labels(tree) == ["- sub/", "  inner.txt", "  a.txt"]


async def test_cursor_starts_on_first_line(root: Path) -> None:
    app = await _open_sidebar(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = app.editor.sidebar.query_one(FileTree)
        assert tree.cursor_node.data.path == root / "sub"


async def test_overlay_uses_same_tree(root: Path) -> None:
    app = await _open_sidebar(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+b")
        await pilot.pause(0.3)
        tree = app.screen.query_one(FileTree)
        assert _labels(tree) == ["+ sub/", "  a.txt"]
