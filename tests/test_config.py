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


def test_missing_file_uses_defaults(xdg: Path) -> None:
    config = load_config()
    assert config == Config()
    assert config.warnings == []


def test_broken_toml_warns(xdg: Path) -> None:
    xdg.write_text("sidebar = \n")
    config = load_config()
    assert config.sidebar is False
    assert config.warnings


def test_old_explorer_root_is_ignored(xdg: Path) -> None:
    # 起点は起動したディレクトリになったので、古い設定が残っていても黙って無視する
    xdg.write_text('explorer_root = "~/repos"\nsidebar = true\n')
    config = load_config()
    assert config.sidebar is True
    assert config.warnings == []


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


def test_sidebar_read_even_if_other_key_invalid(xdg: Path) -> None:
    xdg.write_text('tree_sort = "random"\nsidebar = true\n')
    config = load_config()
    assert config.tree_sort == "asc"
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


def test_soft_wrap(xdg: Path) -> None:
    xdg.write_text("soft_wrap = true\n")
    config = load_config()
    assert config.soft_wrap is True
    assert config.warnings == []


def test_soft_wrap_defaults_to_false(xdg: Path) -> None:
    xdg.write_text("# empty\n")
    assert load_config().soft_wrap is False


def test_soft_wrap_invalid_warns(xdg: Path) -> None:
    xdg.write_text('soft_wrap = "yes"\n')
    config = load_config()
    assert config.soft_wrap is False
    assert config.warnings


def test_css_relative_to_config_dir(xdg: Path) -> None:
    css = xdg.parent / "style.tcss"
    css.write_text("StatusBar { color: red; }\n")
    xdg.write_text('css = "style.tcss"\n')
    config = load_config()
    assert config.css == css.resolve()
    assert config.warnings == []


def test_css_absolute_and_tilde(
    xdg: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "my.tcss").write_text("")
    monkeypatch.setenv("HOME", str(home))
    xdg.write_text('css = "~/my.tcss"\n')
    assert load_config().css == (home / "my.tcss").resolve()


def test_css_missing_file_warns(xdg: Path) -> None:
    xdg.write_text('css = "nope.tcss"\n')
    config = load_config()
    assert config.css is None
    assert config.warnings


def test_css_not_string_warns(xdg: Path) -> None:
    xdg.write_text("css = 1\n")
    config = load_config()
    assert config.css is None
    assert config.warnings


def test_mkparents(xdg: Path) -> None:
    xdg.write_text("mkparents = true\n")
    config = load_config()
    assert config.mkparents is True
    assert config.warnings == []


def test_mkparents_defaults_to_false(xdg: Path) -> None:
    xdg.write_text("# empty\n")
    assert load_config().mkparents is False


def test_mkparents_invalid_warns(xdg: Path) -> None:
    xdg.write_text('mkparents = "yes"\n')
    config = load_config()
    assert config.mkparents is False
    assert config.warnings
