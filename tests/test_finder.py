"""あいまい検索でファイルを開く（Ctrl+O）。"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tsumugi.app import TsumugiApp
from tsumugi.config import Config
from tsumugi.finder import (
    FinderList,
    FinderScreen,
    list_files,
    make_entries,
    normalize_query,
    search,
)

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not found")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def make_app(root: Path, *files: Path) -> TsumugiApp:
    os.chdir(root)
    return TsumugiApp(list(files), system_clipboard=False, config=Config(sidebar=False))


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "src" / "tsumugi").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "tsumugi" / "app.py").write_text("app")
    (tmp_path / "src" / "tsumugi" / "prompt.py").write_text("prompt")
    (tmp_path / "tests" / "test_app.py").write_text("test")
    (tmp_path / "README.md").write_text("readme")
    return tmp_path


# ---- ファイル一覧 ----


@needs_git
def test_list_files_respects_gitignore(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text(".env\n.venv/\n")
    (tmp_path / ".env").write_text("SECRET=1")
    (tmp_path / ".venv" / "lib").mkdir(parents=True)
    (tmp_path / ".venv" / "lib" / "x.py").write_text("")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "ci.yml").write_text("")
    (tmp_path / "tracked.txt").write_text("")
    _git(tmp_path, "add", "tracked.txt", ".gitignore")
    (tmp_path / "untracked.txt").write_text("")
    files, truncated = list_files(tmp_path)
    # 隠しファイルは出す。gitignore されたものは出さない。追跡していないものも出す
    assert sorted(files) == [
        ".github/ci.yml",
        ".gitignore",
        "tracked.txt",
        "untracked.txt",
    ]
    assert not truncated


@needs_git
def test_list_files_in_git_subdirectory(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.txt").write_text("")
    (tmp_path / "b.txt").write_text("")
    files, _ = list_files(tmp_path / "sub")
    # サブディレクトリが起点なら、その下だけを起点からの相対パスで出す
    assert files == ["a.txt"]


@needs_git
def test_list_files_drops_deleted_tracked_files(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / "gone.txt").write_text("")
    (tmp_path / "kept.txt").write_text("")
    _git(tmp_path, "add", ".")
    (tmp_path / "gone.txt").unlink()
    files, _ = list_files(tmp_path)
    assert files == ["kept.txt"]


def test_list_files_outside_git_skips_only_dot_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 上のディレクトリが git でも拾わないよう、git が無い扱いにする
    monkeypatch.setenv("PATH", "")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("")
    (tmp_path / ".env").write_text("")
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "i.js").write_text("")
    (tmp_path / "a.txt").write_text("")
    files, truncated = list_files(tmp_path)
    assert sorted(files) == [".env", "a.txt", "node_modules/x/i.js"]
    assert not truncated


def test_list_files_truncates_at_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")
    for i in range(5):
        (tmp_path / f"f{i}.txt").write_text("")
    files, truncated = list_files(tmp_path, limit=3)
    assert len(files) == 3
    assert truncated


# ---- 検索 ----


def _paths(query: str, paths: list[str]) -> list[str]:
    results, _ = search(normalize_query(query), make_entries(paths))
    return [path for path, _ in results]


def test_search_empty_query_returns_nothing() -> None:
    assert _paths("", ["a.txt"]) == []
    assert _paths("   ", ["a.txt"]) == []


def test_search_ranks_file_name_matches_first() -> None:
    paths = [
        "tests/test_app.py",
        "src/tsumugi/app.py",
        "app/other.txt",
        "src/tsumugi/prompt.py",
    ]
    # ファイル名に飛び飛びで入っている app.py / test_app.py が、ディレクトリ名にしか
    # 入っていない app/other.txt より上。ファイル名の先頭から一致する app.py が一番上
    assert _paths("appy", paths)[:2] == ["src/tsumugi/app.py", "tests/test_app.py"]
    assert "src/tsumugi/prompt.py" not in _paths("appy", paths)


def test_search_prefers_substring_over_scattered() -> None:
    paths = ["a_b_c_d.txt", "xabcd.txt"]
    assert _paths("abcd", paths) == ["xabcd.txt", "a_b_c_d.txt"]


def test_search_ignores_case_and_spaces() -> None:
    assert _paths("Read Me", ["README.md", "x.txt"]) == ["README.md"]


def test_search_matches_across_directories() -> None:
    assert _paths("srcapp", ["src/tsumugi/app.py", "tests/test_app.py"]) == [
        "src/tsumugi/app.py"
    ]


def test_search_positions_point_at_matched_chars() -> None:
    results, _ = search("ap", make_entries(["src/app.py"]))
    path, positions = results[0]
    assert [path[i] for i in positions] == ["a", "p"]


def test_search_handles_regex_special_chars() -> None:
    paths = ["a[1].txt", "a-b^c].txt", r"back\slash.txt"]
    assert _paths("[1]", paths) == ["a[1].txt"]
    assert _paths("b^]", paths) == ["a-b^c].txt"]
    assert _paths("\\s", paths) == [r"back\slash.txt"]


# ---- 画面 ----


async def _open_finder(pilot, app: TsumugiApp) -> FinderScreen:
    await pilot.press("ctrl+o")
    # 一覧はスレッドで集めるので、終わるまで待つ
    for _ in range(50):
        await pilot.pause(0.05)
        screen = app.screen
        if isinstance(screen, FinderScreen) and screen._entries is not None:
            return screen
    raise AssertionError("finder did not finish indexing")


def _shown(screen: FinderScreen) -> list[str]:
    options = screen.query_one(FinderList)
    return [
        str(options.get_option_at_index(i).prompt) for i in range(options.option_count)
    ]


async def test_ctrl_o_shows_nothing_for_empty_query(proj: Path) -> None:
    app = make_app(proj)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open_finder(pilot, app)
        assert _shown(screen) == []


async def test_ctrl_o_typing_lists_candidates(proj: Path) -> None:
    app = make_app(proj)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open_finder(pilot, app)
        await pilot.press(*"appy")
        await pilot.pause()
        assert _shown(screen) == ["src/tsumugi/app.py", "tests/test_app.py"]
        # 文字を消すと候補が増える（絞り込みの使い回しで減ったままにならない）
        await pilot.press("backspace", "backspace", "backspace")
        await pilot.pause()
        assert sorted(_shown(screen)) == [
            "README.md",
            "src/tsumugi/app.py",
            "tests/test_app.py",
        ]


async def test_ctrl_o_enter_opens_top_candidate(proj: Path) -> None:
    app = make_app(proj)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_finder(pilot, app)
        await pilot.press(*"appy", "enter")
        await pilot.pause()
        assert not isinstance(app.screen, FinderScreen)
        assert app.editor.current.path == proj / "src" / "tsumugi" / "app.py"
        assert app.focused is app.editor.current


@pytest.mark.parametrize("key", ["down", "ctrl+n"])
async def test_ctrl_o_down_then_enter_opens_second(proj: Path, key: str) -> None:
    app = make_app(proj)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_finder(pilot, app)
        await pilot.press(*"appy", key, "enter")
        await pilot.pause()
        assert app.editor.current.path == proj / "tests" / "test_app.py"


async def test_ctrl_o_up_stays_at_top(proj: Path) -> None:
    app = make_app(proj)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_finder(pilot, app)
        await pilot.press(*"appy", "down", "ctrl+p", "up", "enter")
        await pilot.pause()
        assert app.editor.current.path == proj / "src" / "tsumugi" / "app.py"


async def test_ctrl_o_enter_without_candidates_does_nothing(proj: Path) -> None:
    app = make_app(proj)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_finder(pilot, app)
        await pilot.press(*"zzz", "enter")
        await pilot.pause()
        assert isinstance(app.screen, FinderScreen)


@pytest.mark.parametrize("key", ["escape", "ctrl+o"])
async def test_ctrl_o_close(proj: Path, key: str) -> None:
    app = make_app(proj)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_finder(pilot, app)
        await pilot.press(key)
        await pilot.pause()
        assert not isinstance(app.screen, FinderScreen)
        assert app.editor.current.path is None
        assert app.focused is app.editor.current


async def test_ctrl_o_click_opens_candidate(proj: Path) -> None:
    app = make_app(proj)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open_finder(pilot, app)
        await pilot.press(*"appy")
        await pilot.pause()
        options = screen.query_one(FinderList)
        await pilot.click(options, offset=(2, 1))
        await pilot.pause()
        assert app.editor.current.path == proj / "tests" / "test_app.py"


async def test_ctrl_o_switches_to_already_open_tab(proj: Path) -> None:
    readme = proj / "README.md"
    app = make_app(proj, readme, proj / "tests" / "test_app.py")
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_finder(pilot, app)
        await pilot.press(*"readme", "enter")
        await pilot.pause()
        assert len(app.editor.buffers) == 2
        assert app.editor.current.path == readme


async def test_ctrl_o_file_name_with_brackets(proj: Path) -> None:
    (proj / "[draft] note.md").write_text("x")
    app = make_app(proj)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open_finder(pilot, app)
        await pilot.press(*"draft")
        await pilot.pause()
        assert _shown(screen) == ["[draft] note.md"]
        await pilot.press("enter")
        await pilot.pause()
        assert app.editor.current.path == proj / "[draft] note.md"


async def test_ctrl_o_uses_current_root(proj: Path) -> None:
    app = make_app(proj / "tests")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open_finder(pilot, app)
        assert screen.root == proj / "tests"
        await pilot.press(*"app")
        await pilot.pause()
        assert _shown(screen) == ["test_app.py"]


async def test_ctrl_o_highlighted_candidate_is_visible(proj: Path) -> None:
    app = make_app(proj)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open_finder(pilot, app)
        await pilot.press(*"appy")
        await pilot.pause()
        options = screen.query_one(FinderList)
        # 一覧はフォーカスを持たないが、選んでいる行はフォーカス中と同じ色にする
        assert not options.has_focus
        style = options.get_component_rich_style("option-list--option-highlighted")
        normal = options.get_component_rich_style("option-list--option")
        assert style.bgcolor is not None
        assert style != normal
        await pilot.press("down")
        await pilot.pause()
        assert options.highlighted == 1
