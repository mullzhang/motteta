# CLIの利用ガイド

ターミナルから、登録した本の一覧、検索結果、確認対象を閲覧する方法を説明します。
導入がまだの場合は[初期設定](setup.md)を先に行ってください。
以下のコマンドはすべて、このリポジトリのフォルダー（README.mdのある場所）で実行します。

## 登録した本の一覧を見る

```sh
mise exec -- uv run --locked motteta export --format csv
```

登録済みの入手記録をCSVで表示します。
`id` は記録ID、`title` は書名、`format` は紙か電子か、`source` は購入先、`acquired_on` は購入日、`quantity` は数量です。
注文状態は `order_state`、所持状態は `possession_state` で確認できます。
`format` の `print` は紙、`digital` は電子、`unknown` は不明を表します。
同じ本を複数回購入していれば、購入ごとの記録が並びます。

CSVファイルとして保存して表計算ソフトで開くこともできます。
次の例はホームフォルダーへ保存します。

```sh
mise exec -- uv run --locked motteta export --format csv > "$HOME/motteta-books.csv"
```

詳しい情報を含む全記録は、空の検索語を指定するとJSONで表示できます。

```sh
mise exec -- uv run --locked motteta search ""
```

## 書名や著者名で検索する

```sh
mise exec -- uv run --locked motteta search "AI"
```

検索語を、探したい書名や著者名の一部に置き換えてください。
ISBNや店舗の商品IDでも検索できます。
結果はJSONの `records` に表示されます。該当する記録がない場合は空の配列になります。

## 確認待ちの本を見る

```sh
mise exec -- uv run --locked motteta review list
```

未解消の確認対象をJSONの `reviews` に表示します。
入手を識別できずに確認対象として保存された本は、購入記録として確定するまで `search` やCSVの一覧に含まれません。
確認対象の `payload` に確認に必要な情報、`kind` に確認が必要な理由が入ります。
例えば `missing_identity` は、購入や入手を識別する情報が不足していることを表します。
解消する場合は、Codexへ対象の確認対象IDと依頼内容を伝えてください。

## 件数と履歴の取得状況を見る

```sh
mise exec -- uv run --locked motteta status
```

`record_count` は確定した入手記録の件数、`unresolved_reviews` は未解消の確認対象の件数です。
購入先とアカウントごとの取得範囲や未確認事項も確認できます。

## ヘルプを見る

```sh
mise exec -- uv run --locked motteta --help
mise exec -- uv run --locked motteta search --help
mise exec -- uv run --locked motteta export --help
```

コマンド一覧は `--help`、各コマンドの引数やオプションは、そのコマンドの後ろへ付ける `--help` で表示します。
通常の照会結果もJSONです。`--json` を付けると改行や字下げを省いた機械処理向けのJSONになります。

## その他の操作

以下の表は `motteta` に続ける引数を示しています。
実行するときは、上の例と同様に `mise exec -- uv run --locked motteta` に続けて指定します。
JSONの入力ファイルが必要な操作は、Codexへ依頼できます。

| 引数 | 用途 |
| --- | --- |
| `init` | 新しい台帳を作る。 |
| `add --input <file>` | 購入や所持の記録を1件追加する。 |
| `import <file>` | 取得した履歴JSONを取り込む。サイトの閲覧自体はCodexが行う。 |
| `check --input <file>` | 商品候補と台帳を照合する。 |
| `update <record-id> --input <file>` | 登録内容を訂正する。 |
| `review resolve <review-id> --input <file>` | 確認対象を解消する。 |
| `bind-identity <record-id> --input <file>` | 確認済みの派生キーを既存の購入へ関連付ける。 |
| `backup --output <file>` | 台帳のバックアップを保存する。 |
| `restore --input <file> --output <file>` | バックアップを別のファイルへ復元する。 |
| `export --format json` | 台帳全体を復元可能なJSONで書き出す。 |
| `doctor` | 台帳やブラウザ接続の設定ファイルを点検する。 |
| `browser install --browser chrome --extension-id <id>` | Chromeと台帳の接続を登録する。 |
| `browser uninstall --browser chrome` | Chromeとの接続を解除する。 |

入力JSONと終了コードは[入力と応答の契約](contracts.md)、接続設定は[初期設定](setup.md)、保存先、バックアップ、復元は[保存とトラブル対処](operations.md)で説明しています。
