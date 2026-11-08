# 初期設定

この手順では、Macに台帳を作り、Chromeの商品ページから照合できるようにします。
設定が済んでいる場合は、[普段の使い方](../README.md#手持ちの本を登録する)へ進んでください。

## 用意するもの

- macOSとGoogle Chrome。
- [mise](https://mise.jdx.dev/)。
- 本の登録や履歴の取り込みに使う、サブスクリプションで利用できるCodex。
- 履歴を取り込む場合は、Chromeを操作できるCodexの環境。

リポジトリをGitで取得するか、ZIPをダウンロードして展開し、今後も使い続けられる場所へ保存してください。
以降のコマンドは、すべてこのリポジトリのフォルダー（README.mdがある場所）をターミナルで開いて実行します。

## 1. 実行環境と拡張機能を準備する

`mise.toml` の内容を確認してから、次のコマンドを実行します。
miseが必要なPython、Node.js、uvを用意し、このフォルダー専用の実行環境と拡張機能を作ります。

```sh
mise trust mise.toml
mise install --locked
mise run deps
mise exec -- npm run build --prefix extension
```

Chromeはリポジトリ内の実行環境と拡張機能を参照します。導入後もこのフォルダーを保管してください。

## 2. 台帳を作る

初回のみ、次を実行します。

```sh
mise exec -- uv run --locked motteta init
```

標準の保存先は `~/Library/Application Support/motteta/ledger.sqlite3` です。

## 3. ChromeにMottetaを読み込む

1. Chromeで `chrome://extensions/` を開きます。
2. 「デベロッパーモード」をオンにします。
3. 「パッケージ化されていない拡張機能を読み込む」を選びます。
4. このリポジトリ内の `extension/dist` フォルダーを選びます。
5. 拡張機能の一覧に「Motteta」が追加されたことを確認します。

Chromeのツールバーにある拡張機能の一覧（パズルのアイコン）から、Mottetaを固定しておくと詳細を開きやすくなります。
Mottetaの「サイトへのアクセス」では、照合に使う対応サイトでの実行を許可してください。
対象はAmazon.co.jp、楽天ブックス、楽天市場、O’Reilly Japan、Gihyo Digital Publishing、SEshopです。
すでに導入済みの拡張を更新した場合は、拡張機能と商品ページを再読み込みしてください。
追加サイトで判定が出ない場合は、Mottetaの「サイトへのアクセス」でそのサイトを許可しているか確認します。

## 4. Chromeと台帳を接続する

ターミナルへ戻り、次を実行します。
ChromeのMottetaと、このMacに保存した台帳を結び付ける設定です。

```sh
mise exec -- uv run --locked motteta browser install --browser chrome --extension-id okdnghjdepkaopghconacdggmlajdmdh
mise exec -- uv run --locked motteta doctor
```

上のIDは同梱する拡張機能のものです。
Chromeの拡張機能画面に表示されたMottetaのIDが異なる場合は、そのIDに置き換えます。
`doctor` の結果が `"result": "ok"` なら、台帳と接続設定のファイルを確認できています。

次に、ChromeでMottetaのアイコンをクリックしてください。
ポップアップに「ローカル台帳：接続済み」と表示されれば、Chromeから台帳を利用できています。

## 5. 本を登録して使い始める

Codexでこのリポジトリのフォルダーを開き、[手持ちの本を登録する](../README.md#手持ちの本を登録する)の依頼例を使って一冊登録してください。
履歴をまとめて登録したい場合は、[購入履歴の取り込み](../README.md#購入履歴をまとめて取り込む)へ進みます。

登録後、Chromeで対応する商品詳細ページを開きます。
すでに開いていたページは再読み込みしてください。
書名付近の「Motteta：…」と、ポップアップ内の登録内容を確認できます。

## 接続できない場合

[保存とトラブル対処](operations.md#結果が出ない場合)を参照してください。
Codexへ調査を依頼する場合は、ポップアップのエラー文を添えてください。
