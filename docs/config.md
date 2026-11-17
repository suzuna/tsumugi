# 設定

`~/.config/tsumugi/config.toml`（`XDG_CONFIG_HOME` があれば `$XDG_CONFIG_HOME/tsumugi/config.toml`）に書く。読めないときは既定値で起動し、下段に警告を出す。

```toml
# 起動時にサイドバーのツリーを開かない（既定は true）
sidebar = false

# ツリーの名前順 "asc" / "desc"（既定は "asc"）
tree_sort = "desc"

# 長い行を右端で折り返す（既定は false）
soft_wrap = true

# 見た目のカスタム CSS（Textual CSS）
css = "style.tcss"

# 保存先のフォルダがなければ作る（既定は false。micro の mkparents と同じ）
mkparents = true

# タブが1枚のときはタブバーを隠す（既定は false。1枚でも出す）
hide_single_tab = true

# この行数より長いファイルはシンタックスハイライトしない。0 なら全部しない（既定は 3000）
highlight_max_lines = 5000
```

`highlight_max_lines` の行数は、開くときとディスクから読み直すときに見る。編集で上限をまたいでも、ハイライトを付けたり消したりはしない。

## カスタム CSS

`css` に Textual CSS（`.tcss`）のパスを書くと、既定の見た目より優先して読み込む。相対パスは設定ファイルと同じディレクトリから探す。

主なウィジェット名は `EditorScreen`（画面全体）、`Buffer`（エディタ）、`#sidebar`（サイドバー）、`StatusBar`（下のバー）、`TabBar`（上のタブバー）、`ExplorerScreen #explorer-box`（エクスプローラのオーバーレイの枠）、`FinderScreen #finder-box`（Ctrl+O の枠）、`HelpScreen > VerticalScroll`（ヘルプの枠）。ステータスバーは既定で `text-style: reverse` なので、色を付けるときは `text-style: none` にする。タブバーの `color` は選択していないタブの文字色で、既定はグレー（`ansi_bright_black`）。操作中のペインのタブバーには `-focused` クラスが付き、既定は `TabBar.-focused { background: ansi_bright_black; color: ansi_default; }` でバーに色を付ける。操作中のペインの選択中のタブは `TabBar > .tab-bar--active` で、既定は `background: $background; color: ansi_default`（エディタと同じ背景）。分割しているとき、操作していないほうのペインの選択中のタブは `TabBar > .tab-bar--unfocused` で、既定は `color: ansi_default`（本文と同じ文字色）。サイドバーの見出し（ツリーの起点のパス）は `#sidebar RootPath` で、ツリーにフォーカスがある間はサイドバーに `-focused` クラスが付く（このときペインのタブバーからは `-focused` が外れる）。既定は `EditorScreen #sidebar.-focused RootPath { background: ansi_bright_black; color: ansi_default; }` で、タブバーと同じ色の帯にする。ペインは `Pane`、分割の区切り線は2つ目のペイン `Pane.-second` の枠線。ヘルプのキーの列は `HelpText > .help--key` で、既定は `color: $accent; text-style: bold`。スクロールバーの色は `* { scrollbar-color: ...; }` のように全体に指定する。既定はつまみがグレー（`ansi_bright_black`）、マウスを乗せたりつかんだりしている間は白（`ansi_white`）、溝は端末の背景色で、`scrollbar-color-hover` / `scrollbar-color-active` / `scrollbar-background` などで個別に変えられる。

```css
StatusBar {
    text-style: none;
    background: #ea7599;
    color: #ffffff;
}

/* バーは背景より少し明るい色、選択していないタブはくすんだ色 */
TabBar {
    background: #24133f;
    color: #8a7fa0;
}
/* 操作中のペインのバー */
TabBar.-focused {
    background: #613057;
    color: #a990b8;
}
/* 選択中のタブ（背景はエディタと同じ色にする） */
TabBar > .tab-bar--active,
TabBar > .tab-bar--unfocused {
    background: #180b33;
    color: #ffffff;
}

/* サイドバーの見出しはタブバーと同じ色の帯にする */
EditorScreen #sidebar RootPath {
    background: #24133f;
}
EditorScreen #sidebar.-focused RootPath {
    background: #613057;
}
```
