# 保存とトラブル対処

台帳の保存先、バックアップと復元、商品ページに結果が出ない場合の対処を説明します。
初めて導入する場合は[初期設定](setup.md)、日常の使い方は[README](../README.md)を参照してください。
以下のコマンドは、初期設定と同じくMottetaのリポジトリのフォルダーで実行します。

## 台帳の保存先

macOSの標準の保存先は `~/Library/Application Support/motteta/ledger.sqlite3` です。
CLIの `--data-dir`、または環境変数 `MOTTETA_DATA_DIR` でフォルダを明示できます。
CLIでは `motteta --data-dir <directory> ...` のようにコマンドより前に指定します。
台帳は[初期設定](setup.md)で作成します。

## ブラウザ接続の登録

接続を登録し直す場合は、[初期設定](setup.md)の接続コマンドを実行します。

別の台帳へ切り替える場合は、Codexへ保存先を伝え、Chromeの接続先も同じ台帳へ変更するよう依頼してください。

```sh
mise exec -- uv run --locked motteta doctor
```

`doctor` は台帳と接続ファイルを調べます。
接続を解除する手順は[利用をやめる場合](#利用をやめる場合)を参照してください。

## 拡張機能の権限

自動照合の対象は `amazon.co.jp`、`www.amazon.co.jp`、`books.rakuten.co.jp`、`item.rakuten.co.jp`、`www.oreilly.co.jp`、`gihyo.jp`、`www.seshop.com` です。
対応する商品ページを読み取る権限と、Mac内の台帳へ接続する権限を使います。
Chromeの「サイトへのアクセス」で、利用するサイトを許可してください。

照合には現在選択されている商品の情報を使います。
タブへ戻ると台帳を再確認します。
画面構造が未対応なら「確認できません」と表示し、ポップアップに理由を示します。

## バックアップと復元

### バックアップを保存する

```sh
mise exec -- uv run --locked motteta backup --output "$HOME/motteta-backup.sqlite3"
```

バックアップには、日付などを付けた新しいファイル名を指定してください。

### バックアップから復元する

```sh
mkdir -p "$HOME/motteta-restored"
mise exec -- uv run --locked motteta restore --input "$HOME/motteta-backup.sqlite3" --output "$HOME/motteta-restored/ledger.sqlite3"
mise exec -- uv run --locked motteta --data-dir "$HOME/motteta-restored" status
```

上の例では、新しい台帳を `~/motteta-restored/ledger.sqlite3` に復元します。
復元した台帳を使う場合は、Codexに復元先を伝えてChromeの接続登録を依頼してください。

### JSONで書き出して復元する

完全なJSON書き出しからも復元できます。

```sh
mise exec -- uv run --locked motteta export --format json > "$HOME/motteta-export.json"
mkdir -p "$HOME/motteta-json-restored"
mise exec -- uv run --locked motteta restore --format json --input "$HOME/motteta-export.json" --output "$HOME/motteta-json-restored/ledger.sqlite3"
```

JSONには台帳の全記録と観測、訂正、取得範囲を含みます。

## 結果が出ない場合

まず、ChromeのツールバーからMottetaのポップアップを開きます。
アイコンが見当たらない場合は、拡張機能の一覧（パズルのアイコン）から開けます。

| 状況 | 対処 |
| --- | --- |
| 商品ページにMottetaの表示が出ない | 対応する商品詳細ページか確認し、拡張機能のサイトへのアクセスを許可します。拡張機能を読み込む前から開いていたページは再読み込みします。 |
| 「ローカル台帳：接続できません」 | 直下のエラー文を確認します。`doctor` を実行し、台帳が作成済みか、リポジトリを移動や削除していないか確認します。 |
| 「商品詳細ページを開いてください」 | 対応する商品詳細ページへ移動します。台帳への接続状態は、その上の「ローカル台帳：…」で確認できます。 |
| 商品ページとの通信エラー | `chrome://extensions/` でMottetaを再読み込みしてから、商品ページも再読み込みします。 |
| 「確認できません」で商品を特定できない旨の説明が出る | 商品ページを再読み込みします。改善しない場合は、商品URLを添えてCodexへ読み取り処理の調査を依頼します。 |
| 登録済みのはずなのに「記録なし」 | Codexに書名で台帳を検索させ、対象の記録と購入履歴の未確認範囲を調べます。 |
| 「同じ本の可能性あり」 | 候補の書名と紙か電子かをポップアップで確認します。 |

Codexへ接続や読み取りの調査を依頼する際は、商品URLとポップアップのエラー文を伝えてください。
履歴の取り込みで未確認の範囲がある場合は、取り込み結果で示された箇所から続きを依頼できます。

## 更新した場合

リポジトリを更新したら、同じフォルダーで依存関係と拡張機能を更新します。

```sh
mise install --locked
mise run deps
mise exec -- npm run build --prefix extension
```

その後、`chrome://extensions/` でMottetaを再読み込みし、開いている商品ページも再読み込みしてください。
リポジトリを移動した場合や拡張機能のIDが変わった場合は、[初期設定](setup.md)の接続登録もやり直します。

## 利用をやめる場合

Chromeと台帳の接続を解除するには、次を実行します。

```sh
mise exec -- uv run --locked motteta browser uninstall --browser chrome
```

続いて、Chromeの拡張機能画面からMottetaを削除します。
接続の解除や拡張機能の削除では、台帳の記録は残ります。
