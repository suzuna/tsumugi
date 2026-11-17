from pathlib import Path

import pytest

from tsumugi.app import TsumugiApp
from tsumugi.config import Config
from tsumugi.statusbar import StatusBar, status_path


def test_status_path_under_cwd(tmp_path: Path) -> None:
    assert status_path(tmp_path / "a" / "b.md", tmp_path) == "a/b.md"


def test_status_path_outside_cwd(tmp_path: Path) -> None:
    home = Path.home()
    assert status_path(home / "x.md", tmp_path) == "~/x.md"
    assert status_path(Path("/etc/hosts"), tmp_path) == "/etc/hosts"


def test_status_path_untitled(tmp_path: Path) -> None:
    assert status_path(None, tmp_path) == "No name"


def _bar_text(app: TsumugiApp) -> str:
    return app.editor.query_one(StatusBar).render().plain


async def test_status_bar_shows_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "content" / "posts" / "a.md"
    f.parent.mkdir(parents=True)
    f.write_text("x")
    monkeypatch.chdir(tmp_path)
    app = TsumugiApp([f], system_clipboard=False, config=Config(explorer_root=tmp_path))
    async with app.run_test(size=(80, 10)) as pilot:
        await pilot.pause()
        text = _bar_text(app)
        # パスは左、行と列・改行コード・文字コードは右端
        assert text.startswith(" content/posts/a.md ")
        assert text.endswith("  (1,1) | unix | utf-8 ")
        assert len(text) == 80


async def test_long_path_is_truncated_from_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / ("d" * 60) / "a.md"
    f.parent.mkdir()
    f.write_text("x")
    monkeypatch.chdir(tmp_path)
    app = TsumugiApp([f], system_clipboard=False, config=Config(explorer_root=tmp_path))
    async with app.run_test(size=(60, 10)) as pilot:
        await pilot.pause()
        text = _bar_text(app)
        # 幅いっぱいまでパスに使い、頭が … になり、ファイル名と右側は残る
        assert len(text) == 60
        assert text.startswith(" …")
        assert text.endswith("/a.md (1,1) | unix | utf-8 ")


async def test_dirty_mark_is_kept_when_path_is_truncated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / ("d" * 60) / "a.md"
    f.parent.mkdir()
    f.write_text("x")
    monkeypatch.chdir(tmp_path)
    app = TsumugiApp([f], system_clipboard=False, config=Config(explorer_root=tmp_path))
    async with app.run_test(size=(60, 10)) as pilot:
        await pilot.pause()
        await pilot.press("y")
        text = _bar_text(app)
        assert len(text) == 60
        assert text.startswith(" …")
        assert text.endswith("/a.md + (1,2) | unix | utf-8 ")


async def test_status_bar_has_no_help_hint(tmp_path: Path) -> None:
    app = TsumugiApp([], system_clipboard=False, config=Config(explorer_root=tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "Ctrl-g" not in _bar_text(app)
