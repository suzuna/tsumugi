# tsumugi

micro に近いキー操作で、ファイルを探して開く・並べる部分を作り込んだ TUI のテキストエディタ。Python + Textual で作っている。

## 特徴

- ファイルツリー：画面中央のオーバーレイと左のサイドバーの2通りで出せる。名前の変更・ゴミ箱へ移す・ディレクトリ作成もツリーの中でできる
- あいまい検索で開く：Ctrl+O でファイル名を数文字打てば開ける
- VS Code 式のペイン：ペインごとにタブの列を持ち、タブをドラッグや Ctrl+] でペインの間へ移せる（ペインは2つまで）
- 見た目のカスタマイズ：Textual CSS でタブバー・ステータスバー・スクロールバーなどの色を変えられる

そのかわり、プラグイン・マクロ・マルチカーソル・コマンドバーなど、micro の多機能な部分は持たない（micro との違いは [docs/usage.md](docs/usage.md)）。

## インストール

Python 3.15 と uv が必要。

```sh
uv tool install -e .
```

これで `tsumugi` コマンドがどこからでも使えるようになる。開発中にそのまま動かすなら `uv run tsumugi`。

## 使い方

```sh
tsumugi              # 無題のバッファで起動
tsumugi foo.txt      # ファイルを開く（存在しなければ新規ファイルとして開く）
tsumugi a.txt b.txt  # 複数ファイルをタブで開く
tsumugi ~/repos/foo  # ディレクトリを開く（ツリーの起点にして、そこへ cd する）
```

起動のくわしい説明、キーバインド、エクスプローラの操作は [docs/usage.md](docs/usage.md)、設定ファイルとカスタム CSS は [docs/config.md](docs/config.md) にまとめている。

## 開発

```sh
uv run pytest
```

コミット前に ruff（import 順の整列と formatter）を通す。設定は pyproject.toml の `[tool.ruff]`。

```sh
uv run ruff check --fix .
uv run ruff format .
```
