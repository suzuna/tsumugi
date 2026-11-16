"""画面最下段のインフォバー。メッセージ表示と1行プロンプトを兼ねる（micro と同じ）。"""

from __future__ import annotations

from collections.abc import Callable

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Input, Label


class PromptInput(Input):
    BINDINGS = [
        Binding("escape", "cancel", show=False),
        Binding("ctrl+q", "cancel", show=False),
    ]

    def action_cancel(self) -> None:
        self.parent.cancel()  # type: ignore[union-attr]


class InfoBar(Horizontal):
    DEFAULT_CSS = """
    InfoBar {
        height: 1;
        width: 1fr;
    }
    InfoBar > Label {
        width: auto;
        height: 1;
    }
    InfoBar > #message {
        width: 1fr;
    }
    InfoBar > PromptInput {
        display: none;
        width: 1fr;
        height: 1;
        border: none;
        padding: 0;
        background: transparent;
    }
    InfoBar > PromptInput:focus {
        border: none;
    }
    InfoBar.prompting > PromptInput {
        display: block;
    }
    InfoBar.prompting > #message {
        display: none;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._on_submit: Callable[[str], None] | None = None
        self._on_change: Callable[[str], None] | None = None
        self._on_cancel: Callable[[], None] | None = None
        self._single_key: set[str] | None = None

    def compose(self) -> ComposeResult:
        yield Label("", id="prompt-label")
        yield Label("", id="message")
        yield PromptInput(id="prompt-input", select_on_focus=False)

    @property
    def active(self) -> bool:
        return self.has_class("prompting")

    def show_message(self, text: str) -> None:
        self.query_one("#message", Label).update(text)

    def ask(
        self,
        label: str,
        on_submit: Callable[[str], None],
        *,
        on_change: Callable[[str], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        initial: str = "",
        choices: set[str] | None = None,
    ) -> None:
        """プロンプトを出す。choices を渡すと、その1文字が入力された時点で確定する。"""
        self._on_submit = on_submit
        self._on_change = on_change
        self._on_cancel = on_cancel
        self._single_key = choices
        self.query_one("#prompt-label", Label).update(label)
        inp = self.query_one(PromptInput)
        with inp.prevent(Input.Changed):
            inp.value = initial
        inp.cursor_position = len(initial)
        self.add_class("prompting")
        inp.focus()

    def _finish(self) -> None:
        self.remove_class("prompting")
        self.query_one("#prompt-label", Label).update("")
        self._on_submit = self._on_change = self._on_cancel = None
        self._single_key = None
        self.app.focus_editor()

    def cancel(self) -> None:
        cb = self._on_cancel
        self._finish()
        if cb:
            cb()

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        value = event.value
        if self._single_key is not None:
            if value.lower() in self._single_key:
                cb = self._on_submit
                self._finish()
                if cb:
                    cb(value.lower())
            elif value:
                event.input.value = ""
            return
        if self._on_change:
            self._on_change(value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if self._single_key is not None:
            return
        cb = self._on_submit
        self._finish()
        if cb:
            cb(event.value)

    def on_descendant_blur(self, event: events.DescendantBlur) -> None:
        # マウスでエディタをクリックしたなどでフォーカスが外れたらキャンセル扱い
        if self.active and self.app.screen is self.screen:
            self.call_after_refresh(self._cancel_if_unfocused)

    def _cancel_if_unfocused(self) -> None:
        if self.active and not self.query_one(PromptInput).has_focus:
            self.cancel()
