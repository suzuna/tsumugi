"""tsumugi - a tiny micro-like terminal text editor."""

import os

# kitty keyboard protocol をオフにする。iTerm2 では IME の確定が「Enter + 確定文字」の
# CSI u で届き、Textual が改行として扱ったり、長いと生のシーケンスを入力したりするため。
# textual.constants は import 時に環境変数を読むので、textual より先に読まれるここで設定する。
# TEXTUAL_DISABLE_KITTY_KEY=0 で起動すれば従来どおり有効になる。
os.environ.setdefault("TEXTUAL_DISABLE_KITTY_KEY", "1")

__version__ = "0.1.0"
