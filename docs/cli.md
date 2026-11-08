# CLIの利用ガイド

ターミナルから、登録した本の一覧、検索結果、確認対象を閲覧する方法を説明します。
導入がまだの場合は[初期設定](setup.md)を先に行ってください。
以下のコマンドはすべて、このリポジトリのフォルダー（README.mdのある場所）で実行します。

## 登録した本の一覧を見る

```sh
mise exec -- uv run --locked motteta list
```

書名（`Title`）、形態（`Format`）、購入先（`Source`）、入手日（`Acquired`）を表で表示します。
同じ本を複数回購入していれば、購入ごとの記録が並びます。

## 書名や著者名で検索する

```sh
mise exec -- uv run --locked motteta search "AI"
```

検索語を、探したい書名や著者名の一部に置き換えてください。
ISBNや店舗の商品IDでも検索できます。
該当する本を一覧と同じ表で表示します。

## 本の詳細を見る

登録時に返された記録IDを指定します。

```sh
mise exec -- uv run --locked motteta show "対象の記録ID"
```

書名の全文、著者、形態、購入先、購入日、数量、注文状態、所持状態などを表示します。

## シェルやほかのツールから連携する

`list`、`search`、`show` は、`--json` を付けると機械処理向けのJSONを返します。

```sh
mise exec -- uv run --locked motteta list --json
mise exec -- uv run --locked motteta search "AI" --json
mise exec -- uv run --locked motteta show "対象の記録ID" --json
```

`list` と `search` は `records` 配列、`show` は `record` に記録を返します。
各記録の `id` が `show` に渡す記録IDです。
シェル関数で `list --json` の結果を整形すれば、pecoなどで選んだ記録の詳細を `show` で表示できます。

## CSVへ書き出す

ホームフォルダーへCSVファイルを保存します。

```sh
mise exec -- uv run --locked motteta export --format csv > "$HOME/motteta-books.csv"
```

## 確認待ちの本を見る

```sh
mise exec -- uv run --locked motteta review list
```

未解消の確認対象をJSONの `reviews` に表示します。
入手を識別できずに確認対象として保存された本は、購入記録として確定するまで `list` や `search` の一覧に含まれません。
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
