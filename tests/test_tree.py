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


def test_truncate_left_keeps_short_text() -> None:
    from tsumugi.explorer import truncate_left

    assert truncate_left("~/repos", 30) == "~/repos"
    assert truncate_left("~/repos", 7) == "~/repos"


def test_truncate_left_keeps_tail() -> None:
    from rich.cells import cell_len

    from tsumugi.explorer import truncate_left

    path = "~/repos/blog-suzunano/content/posts"
    out = truncate_left(path, 20)
    assert out.startswith("…")
    assert out.endswith("content/posts")
    assert cell_len(out) == 20


def test_truncate_left_wide_chars() -> None:
    from rich.cells import cell_len

    from tsumugi.explorer import truncate_left

    path = "~/ドキュメント/ブログ/記事の下書き"
    for width in range(0, 40):
        out = truncate_left(path, width)
        assert cell_len(out) <= width
    assert truncate_left(path, 1) == "…"
    assert truncate_left(path, 0) == ""


async def test_sidebar_root_path_is_one_line(tmp_path: Path) -> None:
    from tsumugi.explorer import RootPath

    deep = tmp_path / "very-long-directory-name" / "another-long-directory" / "posts"
    deep.mkdir(parents=True)
    app = TsumugiApp([], system_clipboard=False, config=Config(explorer_root=deep))
    async with app.run_test(size=(100, 20)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        label = app.editor.sidebar.query_one(RootPath)
        assert label.size.height == 1
        shown = label.render().plain
        assert shown.startswith("…")
        assert shown.endswith("another-long-directory/posts")
        assert len(shown) <= label.size.width
        # Backspace で親に移ると表示も変わる
        await pilot.press("backspace")
        await pilot.pause()
        assert label.render().plain.endswith("another-long-directory")
