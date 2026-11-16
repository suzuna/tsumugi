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


def test_sort_paths_dirs_first_and_desc(tmp_path: Path) -> None:
    from tsumugi.explorer import sort_paths

    names = ["b.txt", "A.txt", "c.txt"]
    dirs = ["y", "X"]
    paths = [tmp_path / n for n in names + dirs]
    is_dir = lambda p: p.name in dirs  # noqa: E731
    asc = [p.name for p in sort_paths(paths, False, is_dir)]
    desc = [p.name for p in sort_paths(paths, True, is_dir)]
    assert asc == ["X", "y", "A.txt", "b.txt", "c.txt"]
    assert desc == ["y", "X", "c.txt", "b.txt", "A.txt"]


@pytest.fixture
def sortable(tmp_path: Path) -> Path:
    for name in ["2021-a.md", "2023-c.md", "2022-b.md"]:
        (tmp_path / name).write_text("x")
    (tmp_path / "dir1").mkdir()
    (tmp_path / "dir2").mkdir()
    (tmp_path / "dir2" / "1.md").write_text("x")
    (tmp_path / "dir2" / "2.md").write_text("x")
    return tmp_path


async def test_toggle_sort_in_sidebar(sortable: Path) -> None:
    app = await _open_sidebar(sortable)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = app.editor.sidebar.query_one(FileTree)
        assert _labels(tree) == ["+ dir1/", "+ dir2/", "  2021-a.md", "  2022-b.md", "  2023-c.md"]
        await pilot.press("s")
        await pilot.pause(0.3)
        assert _labels(tree) == ["+ dir2/", "+ dir1/", "  2023-c.md", "  2022-b.md", "  2021-a.md"]
        assert app.editor.explorer_sort_desc
        # カーソルは並べ替え前と同じ dir1 についていく（2行目に移っている）
        assert tree.cursor_node.data.path == sortable / "dir1"
        assert tree.cursor_line == 1
        # 開いたサブディレクトリの中も降順
        await pilot.press("up", "right")
        await pilot.pause(0.3)
        assert _labels(tree)[:3] == ["- dir2/", "  2.md", "  1.md"]  # 字下げは Tree 側で付く
        await pilot.press("s")
        await pilot.pause(0.3)
        assert _labels(tree)[0] == "+ dir1/"
        assert not app.editor.explorer_sort_desc


async def test_sort_order_shared_with_overlay(sortable: Path) -> None:
    app = await _open_sidebar(sortable)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        await pilot.press("s", "ctrl+w", "ctrl+b")
        await pilot.pause(0.3)
        tree = app.screen.query_one(FileTree)
        assert _labels(tree)[0] == "+ dir2/"
        # オーバーレイで戻したら、サイドバーを出し直したときにも反映
        await pilot.press("s")
        await pilot.pause(0.3)
        await pilot.press("escape", "ctrl+e", "ctrl+e")
        await pilot.pause(0.3)
        side = app.editor.sidebar.query_one(FileTree)
        assert _labels(side)[0] == "+ dir1/"


async def test_tree_sort_desc_at_startup(sortable: Path) -> None:
    app = TsumugiApp([], system_clipboard=False, config=Config(explorer_root=sortable, tree_sort="desc"))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = app.editor.sidebar.query_one(FileTree)
        assert _labels(tree) == ["+ dir2/", "+ dir1/", "  2023-c.md", "  2022-b.md", "  2021-a.md"]
        await pilot.press("ctrl+w", "ctrl+b")
        await pilot.pause(0.3)
        assert _labels(app.screen.query_one(FileTree))[0] == "+ dir2/"
        await pilot.press("escape", "ctrl+w", "s")
        await pilot.pause(0.3)
        assert _labels(tree)[0] == "+ dir1/"
