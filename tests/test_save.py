from pathlib import Path

from tsumugi.app import TsumugiApp
from tsumugi.config import Config
from tsumugi.prompt import PromptInput


def make_app(tmp_path: Path, *files: Path, **config) -> TsumugiApp:
    config.setdefault("explorer_root", tmp_path)
    return TsumugiApp(list(files), system_clipboard=False, config=Config(**config))


def message(app: TsumugiApp) -> str:
    return str(app.editor.infobar.query_one("#message").render())


async def type_filename(pilot, app: TsumugiApp, name: str) -> None:
    """Ctrl+S のあとの Filename プロンプトに名前を入れて Enter。"""
    assert app.editor.infobar.active
    app.editor.infobar.query_one(PromptInput).value = name
    await pilot.press("enter")
    await pilot.pause()


async def test_mkparents_creates_missing_dirs(tmp_path: Path) -> None:
    target = tmp_path / "new-post" / "deep" / "index.qmd"
    app = make_app(tmp_path, mkparents=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("h", "i", "ctrl+s")
        await type_filename(pilot, app, str(target))
        assert target.read_text() == "hi"
        assert "created parent dirs" in message(app)
        assert not app.editor.current.dirty


async def test_without_mkparents_does_not_save(tmp_path: Path) -> None:
    target = tmp_path / "new-post" / "index.qmd"
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("h", "i", "ctrl+s")
        await type_filename(pilot, app, str(target))
        assert not target.exists()
        assert not target.parent.exists()
        assert "mkparents" in message(app)
        assert app.editor.current.dirty


async def test_mkparents_for_file_given_on_command_line(tmp_path: Path) -> None:
    target = tmp_path / "from-cli" / "index.qmd"
    app = make_app(tmp_path, target, mkparents=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("x", "ctrl+s")
        await pilot.pause()
        assert target.read_text() == "x"
