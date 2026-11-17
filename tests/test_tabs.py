import os
from pathlib import Path

from rich.cells import cell_len

from tsumugi.app import TsumugiApp
from tsumugi.config import Config
from tsumugi.explorer import truncate_middle
from tsumugi.panes import TAB_NAME_MAX


def make_app(root: Path, *files: Path) -> TsumugiApp:
    os.chdir(root)
    return TsumugiApp(list(files), system_clipboard=False, config=Config(sidebar=False))


def files(tmp_path: Path, *names: str) -> list[Path]:
    paths = []
    for name in names:
        p = tmp_path / name
        p.write_text(f"{name}\n")
        paths.append(p.resolve())
    return paths


# ---- truncate_middle ----


def test_truncate_middle_fits() -> None:
    assert truncate_middle("abc.py", 6) == "abc.py"
    assert truncate_middle("abc.py", 10) == "abc.py"


def test_truncate_middle_keeps_extension() -> None:
    # … の分を引いた 9 マスを前 4・後ろ 5 に分ける
    assert truncate_middle("very_long_name.txt", 10) == "very…e.txt"


def test_truncate_middle_wide_chars() -> None:
    # 2マス文字が境目をまたぐなら手前で止める
    s = truncate_middle("あいうえおかきくけこ.md", 10)
    assert cell_len(s) <= 10
    assert s.startswith("あい…")
    assert s.endswith(".md")


def test_truncate_middle_tiny_width() -> None:
    assert truncate_middle("abcdef", 1) == "…"
    assert truncate_middle("abcdef", 0) == ""


# ---- タブのラベル ----


async def test_long_name_is_truncated_to_max(tmp_path: Path) -> None:
    name = "a_really_long_file_name_for_tab.py"
    (f,) = files(tmp_path, name)
    app = make_app(tmp_path, f)
    async with app.run_test(size=(80, 10)) as pilot:
        await pilot.pause()
        (pane,) = app.editor.panes
        label = pane.tab_bar._labels[0]
        assert cell_len(label) == TAB_NAME_MAX
        assert label.endswith(".py")
        await pilot.press("x")
        await pilot.pause()
        # 未保存の印は上限の外に付ける
        assert pane.tab_bar._labels[0] == label + " +"
