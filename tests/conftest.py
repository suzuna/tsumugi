import os

import pytest


@pytest.fixture(autouse=True)
def _restore_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    """テストやアプリが chdir しても、テストのあとで元のカレントディレクトリに戻す。

    ツリーの起点はカレントディレクトリなので、テストは os.chdir で起点を決める。
    """
    monkeypatch.chdir(os.getcwd())
