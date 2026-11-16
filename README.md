# tsumugi

micro 風の操作感で使える、ターミナル用の小さなテキストエディタ。Ctrl+B でオーバーレイのファイルツリーを開いて、そこからファイルを選べる。

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

| キー | 動作 |
|---|---|
| Ctrl+S | 保存（無題ならファイル名を聞く） |
| Ctrl+Q | タブを閉じる（未保存なら確認）。最後のタブなら終了 |
| Ctrl+B | ファイルエクスプローラ（オーバーレイ）を開く |
| Ctrl+E | サイドバーのツリーを表示 / 非表示 |
| Ctrl+W | サイドバーとエディタの間でフォーカスを移動 |
| Ctrl+T | 新規タブ |
| Ctrl+PgUp / Ctrl+PgDn | 前 / 次のタブ（タブバーのクリックでも切替） |
| Alt+, / Alt+. | 前 / 次のタブ（kitty keyboard protocol 対応ターミナルのみ） |
| Ctrl+Z / Ctrl+Y | undo / redo |
| Ctrl+C / Ctrl+X | コピー / カット（選択なしなら行単位） |
| Ctrl+V | ペースト |
| Ctrl+K | 行カット |
| Ctrl+D | 行（または選択範囲）の複製 |
| Alt+Up / Alt+Down | 行の移動 |
| Ctrl+A | 全選択 |
| Shift+矢印 / マウスドラッグ | 選択 |
| Ctrl+F | 検索（入力しながらインクリメンタルに移動、Enter で確定） |
| Ctrl+N / Ctrl+P | 次 / 前を検索 |
| Ctrl+G | ヘルプ |

### エクスプローラ

ツリーは micro の filemanager と同じ書き方で、ディレクトリは `+ name/`（閉）/ `- name/`（開）、ファイルは字下げだけで表示する。

```
~/repos/tsumugi
+ src/
- tests/
    test_app.py
  README.md
```

ツリーは2通りで出せる。

- Ctrl+B: 画面中央にオーバーレイで出る。ファイルを選ぶと閉じてエディタへ戻る
- Ctrl+E: 画面左の列（サイドバー）に出る。ファイルを選ぶとタブで開き、フォーカスはツリーに残る。Ctrl+W でエディタと行き来する

どちらも最初は設定の `explorer_root`（既定は `~`）を起点に開き、以降は最後にいたディレクトリから開く（両者で共有）。ファイルを選ぶと新しいタブで開く。ただし空の無題バッファは置き換え、すでに開いているファイルならそのタブに切り替える。

| キー | 動作 |
|---|---|
| 矢印 | 移動 |
| Enter / クリック | ファイルを開く・ディレクトリを展開 |
| → | ディレクトリを展開 |
| ← | 開いたディレクトリを閉じる。ファイルや閉じたディレクトリの上なら親ディレクトリへカーソル移動 |
| Backspace | 親ディレクトリへ |
| . | 隠しファイルの表示切替 |
| s | 名前の昇順 / 降順を切り替え（ディレクトリが先なのは変わらない） |
| Esc / Ctrl+B | 閉じる（オーバーレイのみ） |

## 設定

`~/.config/tsumugi/config.toml`（`XDG_CONFIG_HOME` が設定されていれば `$XDG_CONFIG_HOME/tsumugi/config.toml`）に書く。

```toml
# エクスプローラを最初に開くディレクトリ（既定は ~）
explorer_root = "~/repos"

# 起動時にサイドバーのツリーを開く（既定は false）
sidebar = true

# ツリーの名前順 "asc"（昇順）/ "desc"（降順）。既定は "asc"。起動後は s で切り替えられる
tree_sort = "desc"

# 長い行を右端で折り返す（既定は false）。折り返した続きの行には行番号を付けない
soft_wrap = true

# 見た目のカスタム CSS（Textual CSS）
css = "style.tcss"
```

- `sidebar = true` のとき、ファイルを指定して起動したらエディタに、ファイルなしで起動したらツリーにフォーカスする

- `explorer_root` の `~` は展開される。相対パスはホームディレクトリ基準
- ディレクトリが存在しない、TOML が壊れているなどの場合は `~` で開き、起動時に下段へ警告を出す

### カスタム CSS

`css` に Textual CSS（`.tcss`）のパスを書くと、tsumugi の既定の見た目より優先して読み込む。`~` は展開され、相対パスは設定ファイルと同じディレクトリから探す。ファイルがなければ警告を出して無視する。CSS の書き方が間違っていると、起動時に Textual がエラーを出して止まる。

主なウィジェット名は `EditorScreen`（画面全体）、`Buffer`（エディタ）、`#sidebar`（サイドバー）、`StatusBar`（下のバー）。ステータスバーは既定で `text-style: reverse` なので、色を付けるときは `text-style: none` にする。

例: 背景を紫、下のバー・区切り線・スクロールバーをピンクにする

```css
EditorScreen,
EditorScreen Buffer,
ExplorerScreen > ExplorerPanel,
HelpScreen > VerticalScroll {
    background: #180b33;
}

StatusBar {
    text-style: none;
    background: #ea7599;
    color: #ffffff;
}

EditorScreen #sidebar {
    border-right: vkey #ea7599;
}

* {
    scrollbar-color: #ea7599;
    scrollbar-color-hover: #ea7599;
    scrollbar-color-active: #ea7599;
    scrollbar-background: #180b33;
    scrollbar-background-hover: #180b33;
    scrollbar-background-active: #180b33;
    scrollbar-corner-color: #180b33;
}
```

## micro との違い

- シンタックスハイライト、分割表示、コマンドバー（Ctrl+E）、プラグインはない
- Ctrl+B は micro ではシェル実行だけど、tsumugi ではエクスプローラ
- Ctrl+E は micro ではコマンドバーだけど、tsumugi ではサイドバー。Ctrl+W は micro の分割移動と同じ感覚でサイドバーとエディタを行き来する
- 検索は大文字小文字を区別する部分一致（正規表現なし）
- 開けるのは UTF-8 のテキストファイルだけ

## 開発

```sh
uv run pytest
```
