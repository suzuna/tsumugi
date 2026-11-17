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
```

## カスタム CSS

`css` に Textual CSS（`.tcss`）のパスを書くと、既定の見た目より優先して読み込む。相対パスは設定ファイルと同じディレクトリから探す。

主なウィジェット名は `EditorScreen`（画面全体）、`Buffer`（エディタ）、`#sidebar`（サイドバー）、`StatusBar`（下のバー）、`TabBar`（上のタブバー）、`ExplorerScreen > ExplorerPanel`（エクスプローラのオーバーレイの枠）、`HelpScreen > VerticalScroll`（ヘルプの枠）。ステータスバーは既定で `text-style: reverse` なので、色を付けるときは `text-style: none` にする。タブバーで選択中のタブは `TabBar > .tab-bar--active` で、既定は `text-style: reverse bold`。分割しているとき、フォーカスしていないほうのペインの選択中のタブは `TabBar > .tab-bar--unfocused` で、既定は `text-style: bold underline`。ペインは `Pane`、分割の区切り線は2つ目のペイン `Pane.-second` の枠線。ヘルプのキーの列は `HelpText > .help--key` で、既定は `color: $accent`。

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
