import os
from pathlib import Path

import pytest

from tsumugi.app import TsumugiApp
from tsumugi.config import Config
from tsumugi.prompt import PromptInput


def make_app(
    tmp_path: Path, *files: Path, root: Path | None = None, **config
) -> TsumugiApp:
    # ツリーの起点（相対パスで保存するときの基準）は起動したディレクトリ
    os.chdir(root or tmp_path)
    config.setdefault("sidebar", False)
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
        assert "overwrite" in str(
            app.editor.infobar.query_one("#prompt-label").render()
        )
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


async def test_relative_name_saves_under_tree_root(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a", "ctrl+s")
        label = str(app.editor.infobar.query_one("#prompt-label").render())
        assert label.startswith("Filename (") and label.rstrip().endswith("/):")
        await type_filename(pilot, app, "note.md")
        assert (tmp_path / "note.md").read_text() == "a"


async def test_relative_name_follows_sidebar_root(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    app = make_app(tmp_path, root=sub)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause(0.3)
        await pilot.press("backspace")  # ツリーの起点を tmp_path に上げる
        await pilot.pause()
        await pilot.press("ctrl+w", "b", "ctrl+s")
        await type_filename(pilot, app, "up.md")
        assert (tmp_path / "up.md").read_text() == "b"
        assert not (sub / "up.md").exists()


async def test_absolute_and_tilde_names_are_kept(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    other = tmp_path / "elsewhere"
    other.mkdir()
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a", "ctrl+s")
        await type_filename(pilot, app, str(other / "abs.md"))
        assert (other / "abs.md").read_text() == "a"
        await pilot.press("ctrl+t")
        await pilot.pause()
        await pilot.press("b", "ctrl+s")
        await type_filename(pilot, app, "~/tilde.md")
        assert (home / "tilde.md").read_text() == "b"


async def test_relative_name_with_new_dir_and_mkparents(tmp_path: Path) -> None:
    app = make_app(tmp_path, mkparents=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c", "ctrl+s")
        await type_filename(pilot, app, "20261117-test/index.qmd")
        assert (tmp_path / "20261117-test" / "index.qmd").read_text() == "c"


def _rewrite(path: Path, text: str) -> None:
    """外のプロセスが書き換えたことにする。mtime の粒度に頼らないよう時刻も進める。"""
    import os

    st = path.stat()
    path.write_text(text)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))


async def test_unedited_buffer_reloads_when_changed_on_disk(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("one\ntwo\n")
    app = make_app(tmp_path, f)
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = app.editor.current
        buf.move_cursor((1, 2))
        _rewrite(f, "one\nTWO!\nthree\n")
        app.editor._check_disk()
        await pilot.pause()
        assert buf.text == "one\nTWO!\nthree\n"
        assert not buf.dirty
        assert buf.cursor_location == (1, 2)
        assert message(app) == "Reloaded a.txt"


async def test_dirty_buffer_is_not_reloaded_and_notified_once(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("one")
    app = make_app(tmp_path, f)
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = app.editor.current
        await pilot.press("x")
        _rewrite(f, "from llm")
        app.editor._check_disk()
        assert buf.text == "xone"
        assert message(app) == "a.txt changed on disk"
        # 同じ変更は2回知らせない
        app.editor.message("")
        app.editor._check_disk()
        assert message(app) == ""


async def test_save_asks_before_overwriting_changed_file(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("one")
    app = make_app(tmp_path, f)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("x")
        _rewrite(f, "from llm")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.editor.infobar.active
        assert "changed on disk" in str(
            app.editor.infobar.query_one("#prompt-label").render()
        )
        await pilot.press("n")
        await pilot.pause()
        assert f.read_text() == "from llm"
        assert "cancelled" in message(app)
        assert app.editor.current.dirty

        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert f.read_text() == "xone"
        assert not app.editor.current.dirty
        # 保存したあとは、もう聞かない
        await pilot.press("y", "ctrl+s")
        await pilot.pause()
        assert not app.editor.infobar.active
        assert f.read_text() == "xyone"


async def test_save_without_external_change_does_not_ask(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("one")
    app = make_app(tmp_path, f)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("x", "ctrl+s")
        await pilot.pause()
        assert not app.editor.infobar.active
        assert f.read_text() == "xone"


async def test_deleted_file_is_notified_and_can_be_saved_again(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("one")
    app = make_app(tmp_path, f)
    async with app.run_test() as pilot:
        await pilot.pause()
        f.unlink()
        app.editor._check_disk()
        assert message(app) == "a.txt was deleted on disk"
        assert app.editor.current.text == "one"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert not app.editor.infobar.active
        assert f.read_text() == "one"


@pytest.mark.parametrize("nl", ["\r\n", "\r", "\n"])
async def test_save_keeps_newline_style(tmp_path: Path, nl: str) -> None:
    f = tmp_path / "a.txt"
    f.write_bytes(f"one{nl}two{nl}".encode())
    app = make_app(tmp_path, f)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert not app.editor.current.dirty
        await pilot.press("x", "ctrl+s")
        await pilot.pause()
        assert f.read_bytes() == f"xone{nl}two{nl}".encode()


async def test_mixed_newlines_are_not_dirty_on_open(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_bytes(b"one\r\ntwo\nthree\r\n")
    app = make_app(tmp_path, f)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert not app.editor.current.dirty


async def test_reload_keeps_crlf(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_bytes(b"one\r\n")
    app = make_app(tmp_path, f)
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = app.editor.current
        _rewrite_bytes(f, b"one\r\ntwo\r\n")
        app.editor._check_disk()
        await pilot.pause()
        assert buf.document.newline == "\r\n"
        await pilot.press("x", "ctrl+s")
        await pilot.pause()
        assert f.read_bytes() == b"xone\r\ntwo\r\n"


async def test_reload_follows_changed_newline_style(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_bytes(b"one\n")
    app = make_app(tmp_path, f)
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = app.editor.current
        _rewrite_bytes(f, b"one\r\ntwo\r\n")
        app.editor._check_disk()
        await pilot.pause()
        assert buf.document.newline == "\r\n"
        assert not buf.dirty
        await pilot.press("x", "ctrl+s")
        await pilot.pause()
        assert f.read_bytes() == b"xone\r\ntwo\r\n"


def _rewrite_bytes(path: Path, data: bytes) -> None:
    import os

    st = path.stat()
    path.write_bytes(data)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
