import os
import threading
from pathlib import Path

import pytest
import tree_sitter_python
from tree_sitter import Language

from tsumugi import editor
from tsumugi.app import TsumugiApp
from tsumugi.config import Config
from tsumugi.prompt import PromptInput
from tsumugi.syntax import detect_language

# ---- 言語の判定 ----


@pytest.mark.parametrize(
    ("name", "lang"),
    [
        ("a.py", "python"),
        ("A.PY", "python"),
        ("a.rs", "rust"),
        ("a.R", "r"),
        ("a.r", "r"),
        ("model.stan", "stan"),
        ("a.ts", "typescript"),
        ("a.qmd", "markdown"),
        ("a.Rmd", "markdown"),
        ("style.tcss", "css"),
        ("Makefile", "make"),
        ("Dockerfile", "dockerfile"),
        (".bashrc", "bash"),
        ("uv.lock", "toml"),
        ("CMakeLists.txt", "cmake"),
        ("notes.txt", None),
        ("a.unknownext", None),
        ("README", None),
    ],
)
def test_detect_by_name(name: str, lang: str | None) -> None:
    assert detect_language(Path("/x") / name) == lang


@pytest.mark.parametrize(
    ("first_line", "lang"),
    [
        ("#!/usr/bin/env python3", "python"),
        ("#!/bin/bash", "bash"),
        ("#!/usr/bin/env Rscript", "r"),
        ("#!/usr/bin/env -S uv run --script", "python"),
        ("print('no shebang')", None),
    ],
)
def test_detect_by_shebang(first_line: str, lang: str | None) -> None:
    assert detect_language(Path("/x/script"), first_line) == lang


def test_extension_wins_over_shebang() -> None:
    assert detect_language(Path("/x/a.py"), "#!/bin/bash") == "python"


def test_no_path_uses_shebang() -> None:
    assert detect_language(None, "#!/bin/bash") == "bash"
    assert detect_language(None, "") is None


# ---- バッファに当てる ----


def make_app(tmp_path: Path, *files: Path, **config) -> TsumugiApp:
    os.chdir(tmp_path)
    config.setdefault("sidebar", False)
    return TsumugiApp(list(files), system_clipboard=False, config=Config(**config))


def message(app: TsumugiApp) -> str:
    return str(app.editor.infobar.query_one("#message").render())


def lines(n: int) -> str:
    return "x = 1\n" * (n - 1) + "x = 1"


async def test_python_file_is_highlighted(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("def f():\n    return 1\n")
    app = make_app(tmp_path, f)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.editor.current.language == "python"


async def test_unknown_file_is_not_highlighted(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("hello\n")
    app = make_app(tmp_path, f)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.editor.current.language is None


async def test_file_at_limit_is_highlighted(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text(lines(10))
    app = make_app(tmp_path, f, highlight_max_lines=10)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.editor.current.language == "python"


async def test_file_over_limit_is_not_highlighted(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text(lines(11))
    app = make_app(tmp_path, f, highlight_max_lines=10)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.editor.current.language is None


async def test_zero_limit_disables_highlight(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    app = make_app(tmp_path, f, highlight_max_lines=0)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.editor.current.language is None


async def test_editing_over_limit_keeps_highlight(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text(lines(3))
    app = make_app(tmp_path, f, highlight_max_lines=3)
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = app.editor.current
        await pilot.press("enter", "enter")
        assert buf.document.line_count > 3
        assert buf.language == "python"


async def test_reload_over_limit_turns_off_and_keeps_cursor(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text(lines(3))
    app = make_app(tmp_path, f, highlight_max_lines=5)
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = app.editor.current
        buf.move_cursor((1, 2))
        f.write_text(lines(6))
        st = f.stat()
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
        app.editor._check_disk()
        await pilot.pause()
        assert buf.document.line_count == 6
        assert buf.language is None
        assert buf.cursor_location == (1, 2)


async def test_save_as_sets_language(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = app.editor.current
        await pilot.press("x", "ctrl+s")
        assert buf.language is None
        app.editor.infobar.query_one(PromptInput).value = "a.py"
        await pilot.press("enter")
        await pilot.pause()
        assert buf.path == tmp_path / "a.py"
        assert buf.language == "python"
        # 言語を変えてもカーソルは先頭に戻らない
        assert buf.cursor_location == (0, 1)


async def test_rename_changes_language(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x = 1\n")
    app = make_app(tmp_path, f)
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = app.editor.current
        assert buf.language is None
        f.rename(tmp_path / "a.py")
        app.editor._move_buffers(f, tmp_path / "a.py")
        assert buf.language == "python"


async def test_split_copy_keeps_language(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    app = make_app(tmp_path, f, highlight_max_lines=100)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+backslash")
        await pilot.pause()
        buf = app.editor.current
        assert buf.max_lines == 100
        assert buf.language == "python"


# ---- language-pack の言語 ----
# ネットにつながないよう、load_language を Python の文法で差し替える

FAKE = (Language(tree_sitter_python.language()), "(identifier) @variable")


async def test_pack_language_loads_in_background(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(editor, "load_language", lambda name: FAKE)
    f = tmp_path / "a.R"
    f.write_text("x <- 1\n")
    app = make_app(tmp_path, f)
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.editor.current.language == "r"


async def test_pack_language_failure_is_notified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(editor, "load_language", lambda name: None)
    f = tmp_path / "a.R"
    f.write_text("x <- 1\n")
    app = make_app(tmp_path, f)
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.editor.current.language is None
        assert "Cannot load syntax for r" in message(app)


async def test_stale_pack_result_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = threading.Event()

    def slow_load(name: str):
        release.wait(5)
        return FAKE

    monkeypatch.setattr(editor, "load_language", slow_load)
    f = tmp_path / "a.R"
    f.write_text("x <- 1\n")
    app = make_app(tmp_path, f)
    async with app.run_test() as pilot:
        await pilot.pause()
        buf = app.editor.current
        # 取っている間に .py へリネームする
        f.rename(tmp_path / "a.py")
        app.editor._move_buffers(f, tmp_path / "a.py")
        assert buf.language == "python"
        release.set()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert buf.language == "python"
