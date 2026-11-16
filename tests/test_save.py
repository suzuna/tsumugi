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


async def test_overwrite_asks_and_n_keeps_file(tmp_path: Path) -> None:
    target = tmp_path / "exists.md"
    target.write_text("original")
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("n", "e", "w", "ctrl+s")
        await type_filename(pilot, app, str(target))
        # 確認のプロンプトが出たまま（名前のプロンプトを閉じた直後に勝手に閉じない）
        assert app.editor.infobar.active
        assert "overwrite" in str(app.editor.infobar.query_one("#prompt-label").render())
        await pilot.press("n")
        await pilot.pause()
        assert not app.editor.infobar.active
        assert target.read_text() == "original"
        assert "cancelled" in message(app)
        assert app.editor.current.path is None


async def test_overwrite_y_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "exists.md"
    target.write_text("original")
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("n", "e", "w", "ctrl+s")
        await type_filename(pilot, app, str(target))
        await pilot.press("y")
        await pilot.pause()
        assert target.read_text() == "new"
        assert app.editor.current.path == target.resolve()


async def test_overwrite_escape_cancels(tmp_path: Path) -> None:
    target = tmp_path / "exists.md"
    target.write_text("original")
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("n", "e", "w", "ctrl+s")
        await type_filename(pilot, app, str(target))
        await pilot.press("escape")
        await pilot.pause()
        assert target.read_text() == "original"
        assert "cancelled" in message(app)


async def test_new_file_saves_without_asking(tmp_path: Path) -> None:
    target = tmp_path / "fresh.md"
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a", "ctrl+s")
        await type_filename(pilot, app, str(target))
        assert not app.editor.infobar.active
        assert target.read_text() == "a"


async def test_close_save_overwrite_then_closes(tmp_path: Path) -> None:
    target = tmp_path / "exists.md"
    target.write_text("original")
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+t")  # 2つ目のタブ（閉じても終了しないように）
        await pilot.pause()
        await pilot.press("z", "ctrl+q", "y")
        await type_filename(pilot, app, str(target))
        await pilot.press("y")
        await pilot.pause()
        assert target.read_text() == "z"
        assert len(app.editor.buffers) == 1
