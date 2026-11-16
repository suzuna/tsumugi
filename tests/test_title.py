import io

import pytest

from tsumugi.app import terminal_title

PUSH = "\x1b[22;0t"
SET = "\x1b]0;tsumugi\x07"
POP = "\x1b[23;0t"


class FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_sets_and_restores_title() -> None:
    out = FakeTTY()
    with terminal_title("tsumugi", out):
        assert out.getvalue() == PUSH + SET
    assert out.getvalue() == PUSH + SET + POP


def test_restores_title_on_error() -> None:
    out = FakeTTY()
    with pytest.raises(RuntimeError):
        with terminal_title("tsumugi", out):
            raise RuntimeError("boom")
    assert out.getvalue().endswith(POP)


def test_does_nothing_when_not_a_tty() -> None:
    out = io.StringIO()
    with terminal_title("tsumugi", out):
        pass
    assert out.getvalue() == ""
