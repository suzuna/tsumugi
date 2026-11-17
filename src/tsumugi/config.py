"""設定ファイル（$XDG_CONFIG_HOME/tsumugi/config.toml）の読み込み。

例:
    sidebar = false             # 起動時にサイドバーを開かない（既定は true）
    tree_sort = "desc"          # ツリーの名前順 asc / desc（既定は asc）
    soft_wrap = true            # 長い行を右端で折り返す（既定は false）
    css = "style.tcss"          # 見た目のカスタム CSS（相対パスは設定ファイルのディレクトリ基準）
    mkparents = true            # 保存先のフォルダがなければ作る（既定は false、micro と同じ）
    hide_single_tab = true      # タブが1枚のときはタブバーを隠す（既定は false）
    highlight_max_lines = 5000  # これより長いファイルはハイライトしない。0 でオフ（既定は 3000）
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    sidebar: bool = True
    tree_sort: str = "asc"
    soft_wrap: bool = False
    css: Path | None = None
    mkparents: bool = False
    hide_single_tab: bool = False
    highlight_max_lines: int = 3000
    warnings: list[str] = field(default_factory=list)


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base).expanduser() / "tsumugi" / "config.toml"


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    config = Config()
    if not path.exists():
        return config
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        config.warnings.append(f"Cannot read {path}: {e}")
        return config

    # 項目ごとに独立して読む（ある項目が不正でも、ほかの項目は効く）
    _read_sidebar(data, path, config)
    _read_tree_sort(data, path, config)
    _read_soft_wrap(data, path, config)
    _read_css(data, path, config)
    _read_mkparents(data, path, config)
    _read_hide_single_tab(data, path, config)
    _read_highlight_max_lines(data, path, config)
    return config


def _read_sidebar(data: dict, path: Path, config: Config) -> None:
    sidebar = data.get("sidebar")
    if sidebar is None:
        return
    if not isinstance(sidebar, bool):
        config.warnings.append(f"{path}: sidebar must be true or false")
        return
    config.sidebar = sidebar


def _read_tree_sort(data: dict, path: Path, config: Config) -> None:
    order = data.get("tree_sort")
    if order is None:
        return
    if order not in ("asc", "desc"):
        config.warnings.append(f'{path}: tree_sort must be "asc" or "desc"')
        return
    config.tree_sort = order


def _read_soft_wrap(data: dict, path: Path, config: Config) -> None:
    wrap = data.get("soft_wrap")
    if wrap is None:
        return
    if not isinstance(wrap, bool):
        config.warnings.append(f"{path}: soft_wrap must be true or false")
        return
    config.soft_wrap = wrap


def _read_css(data: dict, path: Path, config: Config) -> None:
    css = data.get("css")
    if css is None:
        return
    if not isinstance(css, str):
        config.warnings.append(f"{path}: css must be a string")
        return
    css_path = Path(css).expanduser()
    if not css_path.is_absolute():
        # 相対パスは設定ファイルと同じディレクトリから探す
        css_path = path.parent / css_path
    css_path = css_path.resolve()
    if not css_path.is_file():
        config.warnings.append(f"{path}: css {css} is not a file, ignored")
        return
    config.css = css_path


def _read_mkparents(data: dict, path: Path, config: Config) -> None:
    value = data.get("mkparents")
    if value is None:
        return
    if not isinstance(value, bool):
        config.warnings.append(f"{path}: mkparents must be true or false")
        return
    config.mkparents = value


def _read_hide_single_tab(data: dict, path: Path, config: Config) -> None:
    value = data.get("hide_single_tab")
    if value is None:
        return
    if not isinstance(value, bool):
        config.warnings.append(f"{path}: hide_single_tab must be true or false")
        return
    config.hide_single_tab = value


def _read_highlight_max_lines(data: dict, path: Path, config: Config) -> None:
    value = data.get("highlight_max_lines")
    if value is None:
        return
    # bool は int の仲間なので、true / false は別にはじく
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        config.warnings.append(f"{path}: highlight_max_lines must be an integer >= 0")
        return
    config.highlight_max_lines = value
