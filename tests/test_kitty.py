import os
import subprocess
import sys

# 起動と同じく tsumugi.app を最初に import したとき、textual が kitty protocol を
# オフで読み込むかを別プロセスで確かめる（このプロセスはすでに textual を読んでいる）
SCRIPT = (
    "import tsumugi.app, textual.constants; print(textual.constants.DISABLE_KITTY_KEY)"
)


def _run(env_value: str | None) -> str:
    env = dict(os.environ)
    env.pop("TEXTUAL_DISABLE_KITTY_KEY", None)
    if env_value is not None:
        env["TEXTUAL_DISABLE_KITTY_KEY"] = env_value
    out = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def test_kitty_keyboard_protocol_disabled_by_default() -> None:
    # iTerm2 で IME の確定が壊れるため、既定ではオフ
    assert _run(None) == "True"


def test_kitty_keyboard_protocol_can_be_enabled() -> None:
    assert _run("0") == "False"
