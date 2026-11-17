# tsumugi

micro 風の操作感で使える、TUIの小さなテキストエディタ。

## 特徴

- micro の操作感のうち、よく使う機能だけを Textual で再実装している
- micro の設定やプラグインではやりにくい部分（見た目やファイルツリー周りなど）を、好みに合わせて作り込める

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
