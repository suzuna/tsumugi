"""設定ファイル（$XDG_CONFIG_HOME/tsumugi/config.toml）の読み込み。

例:
    explorer_root = "~/repos"   # ツリーの起点（既定は ~）
    sidebar = true              # 起動時にサイドバーを開く（既定は false）
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    explorer_root: Path = field(default_factory=Path.home)
    sidebar: bool = False
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
    _read_explorer_root(data, path, config)
    _read_sidebar(data, path, config)
    return config


def _read_explorer_root(data: dict, path: Path, config: Config) -> None:
    root = data.get("explorer_root")
    if root is None:
        return
    if not isinstance(root, str):
        config.warnings.append(f"{path}: explorer_root must be a string")
        return
    root_path = Path(root).expanduser()
    if not root_path.is_absolute():
        # 相対パスはホームディレクトリ基準で解決する
        root_path = Path.home() / root_path
    root_path = root_path.resolve()
    if not root_path.is_dir():
        config.warnings.append(f"{path}: explorer_root {root} is not a directory, using ~")
        return
    config.explorer_root = root_path


def _read_sidebar(data: dict, path: Path, config: Config) -> None:
    sidebar = data.get("sidebar")
    if sidebar is None:
        return
    if not isinstance(sidebar, bool):
        config.warnings.append(f"{path}: sidebar must be true or false")
        return
    config.sidebar = sidebar
