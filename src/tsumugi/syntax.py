"""シンタックスハイライトの言語を決める。

Textual が標準で持つ言語（textual[syntax]）はそのまま使い、それ以外の言語は
tree-sitter-language-pack から文法とハイライトのクエリを取ってくる。
language-pack の文法は、その言語を初めて使うときにネットからダウンロードされる。
"""

from __future__ import annotations

import threading
from pathlib import Path

import tree_sitter_language_pack as pack
from textual.widgets.text_area import BUILTIN_LANGUAGES
from tree_sitter import Language

# ファイル名で決めるもの。language-pack の判定では None や別の言語になるものだけ置く。
# 空文字はハイライトしない
_BY_NAME = {
    "makefile": "make",
    "gnumakefile": "make",
    "dockerfile": "dockerfile",
    ".bashrc": "bash",
    ".bash_profile": "bash",
    ".profile": "bash",
    ".zshrc": "zsh",
    ".zprofile": "zsh",
    "uv.lock": "toml",
    "cargo.lock": "toml",
    "cmakelists.txt": "cmake",
}

# 拡張子で決めるもの（language-pack の判定を上書きする）。空文字はハイライトしない
_BY_SUFFIX = {
    ".qmd": "markdown",
    ".rmd": "markdown",
    ".tcss": "css",
    ".jsonc": "json",
    ".svg": "xml",
    # language-pack は .txt を vimdoc にする
    ".txt": "",
}

# shebang のうち language-pack が判定できないもの
_BY_SHEBANG = {
    "uv run": "python",
}


def detect_language(path: Path | None, first_line: str = "") -> str | None:
    """パスと1行目から言語の名前を決める。わからなければ None。"""
    if path is not None:
        name = path.name.lower()
        if name in _BY_NAME:
            return _BY_NAME[name] or None
        suffix = path.suffix.lower()
        if suffix in _BY_SUFFIX:
            return _BY_SUFFIX[suffix] or None
        lang = pack.detect_language_from_path(path.name)
        if lang is not None:
            return lang
    if first_line.startswith("#!"):
        for key, lang in _BY_SHEBANG.items():
            if key in first_line:
                return lang
        return pack.detect_language_from_content(first_line + "\n")
    return None


def is_builtin(name: str) -> bool:
    """Textual が標準で持っている言語か（register_language しなくてよいか）。"""
    return name in BUILTIN_LANGUAGES


_cache: dict[str, tuple[Language, str] | None] = {}
_lock = threading.Lock()


def load_language(name: str) -> tuple[Language, str] | None:
    """language-pack から文法とハイライトのクエリを取る。取れなければ None。

    初めての言語はダウンロードするので時間がかかる。ワーカーのスレッドから呼ぶ。
    結果（失敗も）はプロセスの中で覚えておく。
    """
    with _lock:
        if name in _cache:
            return _cache[name]
        try:
            language = pack.get_language(name)
            query = pack.get_highlights_query(name)
        except Exception:
            # ネットにつながらない、言語がない、など。どれでもハイライトなしにする
            result = None
        else:
            result = (language, query) if query else None
        _cache[name] = result
        return result
