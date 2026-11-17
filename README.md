# tsumugi

micro 風の操作感で使える、ターミナル用の小さなテキストエディタ。

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
```

## キーバインド

基本は micro と同じ。全部のキーは Ctrl+G のヘルプで見られる。micro と違うのはこれだけ。

| キー | tsumugi | micro |
|---|---|---|
| Ctrl+B | ファイルエクスプローラ（オーバーレイ） | シェル実行 |
| Ctrl+E | サイドバーのツリーを表示 / 非表示 | コマンドバー |
| Ctrl+W | サイドバーとエディタの間でフォーカスを移動 | 分割の移動 |
| Ctrl+PgUp / Ctrl+PgDn | 前 / 次のタブ | なし |
| Alt+, / Alt+. | 前 / 次のタブ。ただし kitty keyboard protocol 対応ターミナルで `TEXTUAL_DISABLE_KITTY_KEY=0` を付けて起動したときだけ | 前 / 次のタブ |

ほかの違い。

- シンタックスハイライト、分割表示、コマンドバー、プラグイン、マクロ、マルチカーソルはない
- Ctrl+O（ファイルを開く）、Ctrl+L（行ジャンプ）、Ctrl+R（行番号の切替）は割り当てていない
- 検索は大文字小文字を区別する部分一致（正規表現なし）
- 無題のバッファを保存するとき、相対パスはツリーで最後に見ていたフォルダが基準になる
- 開けるのは UTF-8 のテキストファイルだけ
- 開いているファイルがディスク上で書き換えられたら、未編集なら自動で読み直す。編集中なら下段に知らせ、保存するときに上書きしていいか聞く

kitty keyboard protocol は既定でオフにしている。iTerm2 などでは IME の確定が kitty の形式で届き、日本語が入力できなくなるため。

### エクスプローラ

ツリーは micro の filemanager と同じ書き方で、ディレクトリは `+ name/`（閉）/ `- name/`（開）、ファイルは字下げだけで表示する。

```
~/repos/tsumugi
+ src/
- tests/
    test_app.py
  README.md
```

Ctrl+B では画面中央にオーバーレイで出て、ファイルを選ぶと閉じる。Ctrl+E では左の列に出て、ファイルを選んでもフォーカスはツリーに残る。どちらも最後にいたディレクトリから開き、選んだファイルは新しいタブで開く（空の無題バッファは置き換え、開いているファイルならそのタブへ切り替え）。

ツリーは0.5秒ごとにディスクと見比べて、ほかのプロセスが足したり消したりしたファイルを反映する。展開状態とカーソル位置はそのまま残る。

| キー | 動作 |
|---|---|
| Enter / クリック | ファイルを開く・ディレクトリを展開 |
| → / ← | ディレクトリを展開 / 閉じる（閉じたものの上なら親へカーソル移動） |
| Backspace | 親ディレクトリへ |
| . | 隠しファイルの表示切替 |
| s | 名前の昇順 / 降順を切り替え |
| r / F2 | 名前を変える（サイドバーのみ）。開いているファイルのタブも付け替える |
| d | ゴミ箱へ移す（サイドバーのみ。macOS の `trash` コマンドを使う） |
| m | ディレクトリを作る（サイドバーのみ）。カーソルがディレクトリならその中、ファイルならその隣。`a/b` で入れ子も作れる |
| Esc / Ctrl+B | 閉じる（オーバーレイのみ） |

## 設定

`~/.config/tsumugi/config.toml`（`XDG_CONFIG_HOME` があれば `$XDG_CONFIG_HOME/tsumugi/config.toml`）に書く。読めないときは既定値で起動し、下段に警告を出す。

```toml
# エクスプローラを最初に開くディレクトリ（既定は ~。相対パスはホーム基準）
explorer_root = "~/repos"

# 起動時にサイドバーのツリーを開く（既定は false）
sidebar = true

# ツリーの名前順 "asc" / "desc"（既定は "asc"）
tree_sort = "desc"

# 長い行を右端で折り返す（既定は false）
soft_wrap = true

# 見た目のカスタム CSS（Textual CSS）
css = "style.tcss"

# 保存先のフォルダがなければ作る（既定は false。micro の mkparents と同じ）
mkparents = true
```

### カスタム CSS

`css` に Textual CSS（`.tcss`）のパスを書くと、既定の見た目より優先して読み込む。相対パスは設定ファイルと同じディレクトリから探す。

主なウィジェット名は `EditorScreen`（画面全体）、`Buffer`（エディタ）、`#sidebar`（サイドバー）、`StatusBar`（下のバー）、`TabBar`（上のタブバー）。ステータスバーは既定で `text-style: reverse` なので、色を付けるときは `text-style: none` にする。タブバーで選択中のタブは `TabBar > .tab-bar--active` で、既定は `text-style: reverse bold`。

```css
StatusBar {
    text-style: none;
    background: #ea7599;
    color: #ffffff;
}

/* バーに色を付けると、選択中のタブはその色の反転になる */
TabBar {
    background: #ea7599 50%;
    color: #ffffff;
}
```

## 開発

```sh
uv run pytest
```

コミット前に ruff（import 順の整列と formatter）を通す。設定は pyproject.toml の `[tool.ruff]`。

```sh
uv run ruff check --fix .
uv run ruff format .
```
