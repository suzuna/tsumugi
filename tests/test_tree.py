import os
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
    os.chdir(root)
    app = TsumugiApp([], system_clipboard=False, config=Config())
    return app


def _labels(tree: FileTree) -> list[str]:
    return [
        tree.render_label(line.node, tree.rich_style, tree.rich_style).plain
        for line in tree._tree_lines
    ]


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
    os.chdir(deep)
    app = TsumugiApp([], system_clipboard=False, config=Config())
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
        assert _labels(tree) == [
            "+ dir1/",
            "+ dir2/",
            "  2021-a.md",
            "  2022-b.md",
            "  2023-c.md",
        ]
        await pilot.press("s")
        await pilot.pause(0.3)
        assert _labels(tree) == [
            "+ dir2/",
            "+ dir1/",
            "  2023-c.md",
            "  2022-b.md",
            "  2021-a.md",
        ]
        assert app.editor.explorer_sort_desc
        # カーソルは並べ替え前と同じ dir1 についていく（2行目に移っている）
        assert tree.cursor_node.data.path == sortable / "dir1"
        assert tree.cursor_line == 1
        # 開いたサブディレクトリの中も降順
        await pilot.press("up", "right")
        await pilot.pause(0.3)
        assert _labels(tree)[:3] == [
            "- dir2/",
            "  2.md",
            "  1.md",
        ]  # 字下げは Tree 側で付く
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
    os.chdir(sortable)
    app = TsumugiApp(
        [],
        system_clipboard=False,
        config=Config(tree_sort="desc"),
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = app.editor.sidebar.query_one(FileTree)
        assert _labels(tree) == [
            "+ dir2/",
            "+ dir1/",
            "  2023-c.md",
            "  2022-b.md",
            "  2021-a.md",
        ]
        await pilot.press("ctrl+w", "ctrl+b")
        await pilot.pause(0.3)
        assert _labels(app.screen.query_one(FileTree))[0] == "+ dir2/"
        await pilot.press("escape", "ctrl+w", "s")
        await pilot.pause(0.3)
        assert _labels(tree)[0] == "+ dir1/"


async def test_directory_names_are_not_bold(root: Path) -> None:
    app = await _open_sidebar(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = app.editor.sidebar.query_one(FileTree)
        # アプリは ANSI テーマなので、:ansi 側の指定も打ち消せていること
        assert tree.app.ansi_color or tree.app.current_theme.ansi
        folder = tree.get_component_rich_style("directory-tree--folder", partial=True)
        assert not folder.bold
        dir_node = next(n for n in tree.root.children if n.allow_expand)
        label = tree.render_label(dir_node, tree.rich_style, tree.rich_style)
        assert label.plain == "+ sub/"
        assert not any(
            span.style and getattr(span.style, "bold", False) for span in label.spans
        )
        # 拡張子の斜体はそのまま
        assert tree.get_component_rich_style(
            "directory-tree--extension", partial=True
        ).italic


async def _wait_for(pilot, cond, timeout: float = 3.0) -> bool:
    for _ in range(int(timeout / 0.1)):
        if cond():
            return True
        await pilot.pause(0.1)
    return cond()


async def test_tree_picks_up_files_changed_on_disk(root: Path) -> None:
    app = await _open_sidebar(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = app.editor.sidebar.query_one(FileTree)
        await pilot.press("right")  # sub を展開
        await pilot.pause(0.3)
        await pilot.press("down", "down")
        assert tree.cursor_node.data.path.name == "a.txt"

        (root / "sub" / "new.txt").write_text("n")
        (root / "b.txt").write_text("b")
        expected = ["- sub/", "  inner.txt", "  new.txt", "  a.txt", "  b.txt"]
        assert await _wait_for(pilot, lambda: _labels(tree) == expected)
        # 展開とカーソルはそのまま
        assert tree.cursor_node.data.path.name == "a.txt"

        (root / "sub" / "inner.txt").unlink()
        expected = ["- sub/", "  new.txt", "  a.txt", "  b.txt"]
        assert await _wait_for(pilot, lambda: _labels(tree) == expected)


async def test_tree_does_not_reload_without_changes(root: Path) -> None:
    app = await _open_sidebar(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = app.editor.sidebar.query_one(FileTree)
        calls = []
        original = tree.reload
        tree.reload = lambda: calls.append(1) or original()
        await pilot.pause(1.2)
        assert calls == []


async def test_hidden_sidebar_tree_is_not_polled(root: Path) -> None:
    app = await _open_sidebar(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        tree = app.editor.sidebar.query_one(FileTree)
        await pilot.press("ctrl+e")  # 隠す
        await pilot.pause()
        (root / "b.txt").write_text("b")
        await pilot.pause(1.2)
        assert "  b.txt" not in _labels(tree)
        await pilot.press("ctrl+e")  # また出すと反映される
        assert await _wait_for(pilot, lambda: "  b.txt" in _labels(tree))


async def _sidebar_tree(pilot, app) -> FileTree:
    await pilot.pause()
    await pilot.press("ctrl+e")
    await pilot.pause(0.3)
    return app.editor.sidebar.query_one(FileTree)


async def _answer(pilot, app, text: str) -> None:
    from tsumugi.prompt import PromptInput

    assert app.editor.infobar.active
    app.editor.infobar.query_one(PromptInput).value = text
    await pilot.press("enter")
    await pilot.pause(0.3)


def _message(app) -> str:
    return str(app.editor.infobar.query_one("#message").render())


async def test_rename_file_updates_open_buffer(root: Path) -> None:
    f = root / "a.txt"
    os.chdir(root)
    app = TsumugiApp([f], system_clipboard=False, config=Config())
    async with app.run_test() as pilot:
        tree = await _sidebar_tree(pilot, app)
        tree.select_path(f)
        await pilot.press("r")
        await pilot.pause()
        assert "Rename" in str(app.editor.infobar.query_one("#prompt-label").render())
        await _answer(pilot, app, "b.txt")
        assert not f.exists()
        assert (root / "b.txt").read_text() == "a"
        assert app.editor.buffers[0].path == root / "b.txt"
        assert tree.cursor_node.data.path == root / "b.txt"
        assert tree.has_focus


async def test_rename_dir_moves_buffers_inside(root: Path) -> None:
    inner = root / "sub" / "inner.txt"
    os.chdir(root)
    app = TsumugiApp([inner], system_clipboard=False, config=Config())
    async with app.run_test() as pilot:
        tree = await _sidebar_tree(pilot, app)
        tree.select_path(root / "sub")
        await pilot.press("f2")
        await pilot.pause()
        await _answer(pilot, app, "renamed")
        assert app.editor.buffers[0].path == root / "renamed" / "inner.txt"


async def test_rename_refuses_existing_name(root: Path) -> None:
    (root / "b.txt").write_text("b")
    app = await _open_sidebar(root)
    async with app.run_test() as pilot:
        tree = await _sidebar_tree(pilot, app)
        tree.select_path(root / "a.txt")
        await pilot.press("r")
        await pilot.pause()
        await _answer(pilot, app, "b.txt")
        assert (root / "a.txt").read_text() == "a"
        assert (root / "b.txt").read_text() == "b"
        assert _message(app) == "b.txt already exists"


async def test_mkdir_nested_inside_cursor_dir(root: Path) -> None:
    app = await _open_sidebar(root)
    async with app.run_test() as pilot:
        tree = await _sidebar_tree(pilot, app)
        tree.select_path(root / "sub")
        await pilot.press("m")
        await pilot.pause()
        await _answer(pilot, app, "x/y")
        assert (root / "sub" / "x" / "y").is_dir()
        await pilot.pause(0.3)
        assert tree.cursor_node.data.path == root / "sub" / "x" / "y"
        assert tree.has_focus


async def test_mkdir_next_to_cursor_file(root: Path) -> None:
    app = await _open_sidebar(root)
    async with app.run_test() as pilot:
        tree = await _sidebar_tree(pilot, app)
        tree.select_path(root / "a.txt")
        await pilot.press("m")
        await pilot.pause()
        await _answer(pilot, app, "new")
        assert (root / "new").is_dir()


async def test_delete_moves_to_trash(root: Path, monkeypatch) -> None:
    import subprocess

    from tsumugi import app as app_module

    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        Path(args[1]).unlink()
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(app_module.shutil, "which", lambda name: "/usr/bin/trash")
    monkeypatch.setattr(app_module.subprocess, "run", fake_run)
    app = await _open_sidebar(root)
    async with app.run_test() as pilot:
        tree = await _sidebar_tree(pilot, app)
        tree.select_path(root / "a.txt")
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert calls == []
        assert _message(app) == "Delete cancelled"
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause(0.3)
        assert calls == [["/usr/bin/trash", str(root / "a.txt")]]
        assert _message(app) == "Moved a.txt to trash"
        assert "  a.txt" not in _labels(tree)
        assert tree.has_focus


async def test_file_ops_disabled_in_overlay(root: Path) -> None:
    app = await _open_sidebar(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+b")
        await pilot.pause(0.3)
        await pilot.press("m")
        await pilot.pause()
        assert not app.editor.infobar.active
