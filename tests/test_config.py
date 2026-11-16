from pathlib import Path

import pytest

from tsumugi.app import TsumugiApp
from tsumugi.config import Config, config_path, load_config


@pytest.fixture
def xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    d = tmp_path / "xdg" / "tsumugi"
    d.mkdir(parents=True)
    return d / "config.toml"


def test_config_path_uses_xdg(xdg: Path) -> None:
    assert config_path() == xdg


def test_load_explorer_root(xdg: Path, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    xdg.write_text(f'explorer_root = "{root}"\n')
    config = load_config()
    assert config.explorer_root == root.resolve()
    assert config.warnings == []


def test_missing_file_defaults_to_home(xdg: Path) -> None:
    config = load_config()
    assert config.explorer_root == Path.home()
    assert config.warnings == []


def test_missing_key_defaults_to_home(xdg: Path) -> None:
    xdg.write_text("# empty\n")
    assert load_config().explorer_root == Path.home()


def test_nonexistent_dir_warns(xdg: Path, tmp_path: Path) -> None:
    xdg.write_text(f'explorer_root = "{tmp_path / "nope"}"\n')
    config = load_config()
    assert config.explorer_root == Path.home()
    assert config.warnings


def test_broken_toml_warns(xdg: Path) -> None:
    xdg.write_text("explorer_root = \n")
    config = load_config()
    assert config.explorer_root == Path.home()
    assert config.warnings


def test_tilde_is_expanded(xdg: Path) -> None:
    xdg.write_text('explorer_root = "~"\n')
    assert load_config().explorer_root == Path.home().resolve()


async def test_explorer_starts_at_configured_root(tmp_path: Path) -> None:
    app = TsumugiApp([], system_clipboard=False, config=Config(explorer_root=tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+b")
        await pilot.pause()
        assert app.screen.root == tmp_path


async def test_config_warning_is_shown(tmp_path: Path) -> None:
    config = Config(warnings=["something wrong"])
    app = TsumugiApp([], system_clipboard=False, config=config)
    async with app.run_test() as pilot:
        await pilot.pause()
        msg = app.editor.infobar.query_one("#message")
        assert "something wrong" in str(msg.render())


def test_sidebar_true(xdg: Path) -> None:
    xdg.write_text("sidebar = true\n")
    config = load_config()
    assert config.sidebar is True
    assert config.warnings == []


def test_sidebar_defaults_to_false(xdg: Path) -> None:
    xdg.write_text("# empty\n")
    assert load_config().sidebar is False


def test_sidebar_not_bool_warns(xdg: Path) -> None:
    xdg.write_text('sidebar = "yes"\n')
    config = load_config()
    assert config.sidebar is False
    assert config.warnings


def test_sidebar_read_even_if_root_invalid(xdg: Path, tmp_path: Path) -> None:
    xdg.write_text(f'explorer_root = "{tmp_path / "nope"}"\nsidebar = true\n')
    config = load_config()
    assert config.explorer_root == Path.home()
    assert config.sidebar is True
    assert len(config.warnings) == 1


@pytest.mark.parametrize("order", ["asc", "desc"])
def test_tree_sort(xdg: Path, order: str) -> None:
    xdg.write_text(f'tree_sort = "{order}"\n')
    config = load_config()
    assert config.tree_sort == order
    assert config.warnings == []


def test_tree_sort_defaults_to_asc(xdg: Path) -> None:
    xdg.write_text("# empty\n")
    assert load_config().tree_sort == "asc"


@pytest.mark.parametrize("value", ['"descending"', "true", "1"])
def test_tree_sort_invalid_warns(xdg: Path, value: str) -> None:
    xdg.write_text(f"tree_sort = {value}\n")
    config = load_config()
    assert config.tree_sort == "asc"
    assert config.warnings
