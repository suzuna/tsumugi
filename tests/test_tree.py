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
        await pilot.press("right")
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


async def test_right_expands_left_collapses(root: Path) -> None:
    app = await _open_sidebar(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = app.editor.sidebar.query_one(FileTree)
        sub = tree.cursor_node
        assert sub.data.path == root / "sub"
        await pilot.press("right")
        await pilot.pause(0.3)
        assert sub.is_expanded
        assert [c.data.path.name for c in sub.children] == ["inner.txt"]
        await pilot.press("right")  # 開いてるディレクトリで → は何もしない
        assert sub.is_expanded
        assert tree.cursor_node is sub
        await pilot.press("left")
        assert not sub.is_expanded


async def test_left_on_child_moves_to_parent(root: Path) -> None:
    app = await _open_sidebar(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = app.editor.sidebar.query_one(FileTree)
        sub = tree.cursor_node
        await pilot.press("right")
        await pilot.pause(0.3)
        await pilot.press("down")
        assert tree.cursor_node.data.path.name == "inner.txt"
        await pilot.press("left")
        assert tree.cursor_node is sub
        assert sub.is_expanded  # 移動するだけで閉じない


async def test_left_at_top_level_does_nothing(root: Path) -> None:
    app = await _open_sidebar(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = app.editor.sidebar.query_one(FileTree)
        await pilot.press("down")
        node = tree.cursor_node
        assert node.data.path.name == "a.txt"
        await pilot.press("left")
        assert tree.cursor_node is node
        await pilot.press("up", "left")  # 閉じた最上位ディレクトリでも同じ
        assert tree.cursor_node.data.path.name == "sub"


async def test_overlay_uses_same_tree(root: Path) -> None:
    app = await _open_sidebar(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+b")
        await pilot.pause(0.3)
        tree = app.screen.query_one(FileTree)
        assert _labels(tree) == ["+ sub/", "  a.txt"]
        await pilot.press("right")
        await pilot.pause(0.3)
        assert tree.cursor_node.is_expanded
