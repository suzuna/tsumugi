"""あいまい検索でファイルを開くモーダル（Ctrl+O）。今の起点の下のファイルが対象。"""

from __future__ import annotations

import heapq
import os
import re
import subprocess
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList
from textual.widgets.option_list import Option

# 集めるファイルの上限。これを超えたら打ち切って知らせる
MAX_FILES = 50_000

# 一度に出す候補の数
MAX_RESULTS = 50

GIT_TIMEOUT = 10

# 一致した文字の見た目
MATCH_STYLE = "bold underline"


def list_files(root: Path, limit: int = MAX_FILES) -> tuple[list[str], bool]:
    """root の下のファイルを、root からの相対パス（/ 区切り）で返す。打ち切ったら True も返す。

    git の中なら git ls-files で .gitignore を効かせる（隠しファイルも出す）。
    git の外か git が使えなければ、.git だけ飛ばして全部たどる。
    """
    files = _git_files(root)
    if files is None:
        files = _walk_files(root, limit)
    if len(files) > limit:
        return files[:limit], True
    return files, False


def _git_files(root: Path) -> list[str] | None:
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            capture_output=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return None
    if out.returncode != 0:
        return None
    names = out.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    # 衝突中のファイルは --cached で段ごとに出るので重複を消す。
    # 消したのにコミットしていないファイルや submodule（ディレクトリ）は落とす
    return [
        name
        for name in dict.fromkeys(names)
        if name and os.path.isfile(os.path.join(root, name))
    ]


def _walk_files(root: Path, limit: int) -> list[str]:
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        rel = os.path.relpath(dirpath, root)
        for name in sorted(filenames):
            files.append(name if rel == "." else f"{rel}/{name}".replace(os.sep, "/"))
            if len(files) > limit:
                return files
    return files


# ---- 検索 ----

# (パス, 小文字にしたパス, ファイル名の開始位置)
Entry = tuple[str, str, int]


def make_entries(paths: list[str]) -> list[Entry]:
    return [(p, p.lower(), p.rfind("/") + 1) for p in paths]


def _subsequence_pattern(query: str) -> re.Pattern[str]:
    """query の文字がこの順に（間を空けてもよく）並んでいるところに一致する正規表現。

    `(a).*?(b)` だと一致しない文字列で後戻りが増えて遅いので、`(a)[^b]*(b)` と書く。
    どちらも次の文字の最初の出現に一致するので、見つかる位置は同じ。
    """
    parts = [f"({re.escape(query[0])})"]
    for c in query[1:]:
        esc = re.escape(c)
        parts.append(f"[^{esc}]*({esc})")
    return re.compile("".join(parts))


def _match(
    query: str, pattern: re.Pattern[str], entry: Entry
) -> tuple[tuple[int, int, int, int], list[int]] | None:
    """並べるためのキーと、一致した文字の位置を返す。一致しなければ None。

    キーは小さいほど上。ファイル名に続けて入っている > パスに続けて入っている >
    ファイル名に飛び飛びで入っている > パスに飛び飛びで入っている、の順で、
    同じなら一致した範囲が短い、始まりが前、パスが短い、の順。
    """
    path, lower, base = entry
    n = len(query)
    i = lower.find(query, base)
    if i >= 0:
        return (0, n, i - base, len(path)), list(range(i, i + n))
    i = lower.find(query)
    if i >= 0:
        return (1, n, i, len(path)), list(range(i, i + n))
    m = pattern.search(lower, base)
    if m is not None:
        return (2, m.end() - m.start(), m.start() - base, len(path)), [
            m.start(g) for g in range(1, n + 1)
        ]
    m = pattern.search(lower)
    if m is not None:
        return (3, m.end() - m.start(), m.start(), len(path)), [
            m.start(g) for g in range(1, n + 1)
        ]
    return None


def normalize_query(text: str) -> str:
    """空白は無視し、大文字小文字は区別しない。"""
    return "".join(text.split()).lower()


def search(
    query: str, entries: list[Entry], limit: int = MAX_RESULTS
) -> tuple[list[tuple[str, list[int]]], list[Entry]]:
    """上位 limit 件の (パス, 一致した位置) と、一致した全部の entry を返す。

    一致した全部の entry は、次に1文字足して検索するときの絞り込みに使う
    （query の後ろに足した query に一致するものは、必ず元の query にも一致する）。
    """
    if not query:
        return [], []
    pattern = _subsequence_pattern(query)
    matched: list[Entry] = []
    scored: list[tuple[tuple[int, int, int, int], str, list[int]]] = []
    for entry in entries:
        result = _match(query, pattern, entry)
        if result is None:
            continue
        matched.append(entry)
        key, positions = result
        scored.append((key, entry[0], positions))
    top = heapq.nsmallest(limit, scored, key=lambda s: (s[0], s[1]))
    return [(path, positions) for _, path, positions in top], matched


def highlight(path: str, positions: list[int]) -> Content:
    content = Content(path)
    for pos in positions:
        content = content.stylize(MATCH_STYLE, pos, pos + 1)
    return content


# ---- 画面 ----


class FinderList(OptionList, can_focus=False):
    """候補の一覧。フォーカスは入力欄に置いたままにする（クリックでは選べる）。"""


class FinderScreen(ModalScreen[Path | None]):
    """入力した文字であいまい検索して、選んだファイルのパスを返して閉じる。"""

    DEFAULT_CSS = """
    FinderScreen {
        align: center middle;
    }
    FinderScreen #finder-box {
        width: 70%;
        max-width: 100;
        height: 60%;
        border: round $accent;
        border-title-align: left;
        border-subtitle-align: right;
        background: $surface;
        padding: 0 1;
    }
    FinderScreen #finder-input {
        height: 1;
        border: none;
        padding: 0;
        background: transparent;
    }
    FinderScreen #finder-input:focus {
        border: none;
    }
    FinderScreen FinderList {
        height: 1fr;
        border: none;
        padding: 0;
        background: transparent;
    }
    /* 一覧はフォーカスを持たないので、フォーカス中と同じ色で選んでいる行を見せる */
    FinderScreen FinderList > .option-list--option-highlighted {
        color: $block-cursor-foreground;
        background: $block-cursor-background;
        text-style: $block-cursor-text-style;
    }
    """

    BINDINGS = [
        Binding("escape,ctrl+o", "close", show=False),
        Binding("down,ctrl+n", "cursor(1)", show=False),
        Binding("up,ctrl+p", "cursor(-1)", show=False),
    ]

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root
        self._entries: list[Entry] | None = None
        self._truncated = False
        self._results: list[str] = []
        # 前回の検索語と、それに一致した全部の entry（1文字足したときの絞り込み用）
        self._last_query = ""
        self._last_matched: list[Entry] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="finder-box") as box:
            box.border_title = "Open file"
            box.border_subtitle = "Indexing…"
            yield Input(id="finder-input", placeholder="Search files")
            yield FinderList()

    def on_mount(self) -> None:
        self.query_one(Input).focus()
        self._index()

    @work(thread=True, exclusive=True, exit_on_error=False)
    def _index(self) -> None:
        files, truncated = list_files(self.root)
        entries = make_entries(files)
        self.app.call_from_thread(self._indexed, entries, truncated)

    def _indexed(self, entries: list[Entry], truncated: bool) -> None:
        if not self.is_attached:
            return
        self._entries = entries
        self._truncated = truncated
        if truncated:
            self.app.show_message(
                f"Too many files: only the first {MAX_FILES} are searched"
            )
        # 集め終わる前に打っていた文字で検索する
        self._update(self.query_one(Input).value)

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self._update(event.value)

    def _update(self, text: str) -> None:
        if self._entries is None:
            return
        query = normalize_query(text)
        if self._last_query and query.startswith(self._last_query):
            pool = self._last_matched
        else:
            pool = self._entries
        results, matched = search(query, pool)
        self._last_query, self._last_matched = query, matched
        self._results = [path for path, _ in results]
        options = self.query_one(FinderList)
        options.clear_options()
        options.add_options(
            Option(highlight(path, positions)) for path, positions in results
        )
        if results:
            options.highlighted = 0
        total = f"{len(self._entries)} files" + (
            " (truncated)" if self._truncated else ""
        )
        self.query_one("#finder-box").border_subtitle = (
            f"{len(matched)} / {total}" if query else total
        )

    def action_cursor(self, step: int) -> None:
        options = self.query_one(FinderList)
        if not self._results:
            return
        current = options.highlighted or 0
        options.highlighted = max(0, min(len(self._results) - 1, current + step))

    def action_close(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        index = self.query_one(FinderList).highlighted
        if index is not None and index < len(self._results):
            self.dismiss(self.root / self._results[index])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if event.option_index < len(self._results):
            self.dismiss(self.root / self._results[event.option_index])
