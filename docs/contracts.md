# 入力と応答の契約

入力の正本はPythonのPydanticモデル、公開する形式は `schemas/` にあるJSON Schemaです。
`examples/` はすべて架空のデータです。
形式の版は `schema_version: 1` で、未定義の項目と不正な状態を拒否します。

## 単件追加

`add --input <file> --json`、または `add --input - --json` を使います。
必須項目は `schema_version`、`request_id`、`book`、`acquisition_kind`、`quantity`、`order_state`、`possession_state`、`evidence` です。
`book` の必須項目は書名の `title` と形態の `format` です。

| 項目 | 値と扱い |
| --- | --- |
| `format` | `print`、`digital`、`unknown`。 |
| `acquisition_kind` | 購入は `purchase`、購入を断定しない所持申告は `ownership_assertion`。 |
| `order_state` | 購入は `completed`、`ordered`、`preordered`、`cancelled`、`returned`、`unknown`。所持申告では `null`。 |
| `possession_state` | `owned`、`disposed`、`gift`、`unknown`。購入済みだけでは現在の所持を断定しない。 |
| `quantity` | 正の整数。PDFとEPUBの一括購入は数量一冊とし、`book.file_formats` に両方を記録する。 |
| `acquired_on` | `null`、`YYYY`、`YYYY-MM`、`YYYY-MM-DD`。登録日時で補わない。 |
| `source` | 不明なら `null`。既知なら自由な `id`、表示用の `name`、`online` または `physical` の `kind` を持つ。 |
| `account` | ローカルで区別するための識別名。認証情報やメールアドレスを要求しない。 |
| `evidence` | 一つ以上の根拠。`kind`、タイムゾーン付きの `observed_at`、任意の参照先と注記。 |

ISBNはチェック桁を検証し、ISBN-10をISBN-13へ正規化します。
ISBNを購入の一意キーにしません。
店舗の商品IDは `book.identifiers` に `namespace`、`scope`、`value` として保存します。
拡張機能が使う組み合わせは次のとおりです。

| サイト | `namespace` | `scope` | `value` |
| --- | --- | --- | --- |
| Amazon | `amazon` | `amazon.co.jp` | ASIN |
| 楽天ブックス | `rakuten-books` | `books.rakuten.co.jp` | 商品ID |
| 楽天市場 | `rakuten-market` | `item.rakuten.co.jp/ショップID` | 商品ID |
| O’Reilly Japan | `oreilly-japan` | `oreilly.co.jp` | `/books/` の後の13桁の番号 |
| Gihyo Digital Publishing | `gihyo-dp` | `gihyo.jp/dp` | 電子書籍URL末尾のISBNからハイフンを除いた値 |
| SEshop | `seshop` | `seshop.com` | `/product/detail/` の後の商品ID。書誌欄の「商品番号」とは別。 |

これらは商品を識別する情報で、購入や明細のIDではありません。
O’Reillyの紙と電子の併売ページ、SEshopの紙とPDFのセットは、候補の `format` を `unknown` として照合します。

同じ依頼には同じ `request_id` と同じ内容を使います。
同じIDで内容が異なる場合は競合となります。
後から訂正する場合は、内部の記録IDに対する `update` を使います。
`--dry-run` ではトランザクションを確定せず、台帳がなければメモリ上で検証するため、保存先も作成しません。

## 履歴の取り込み

`import <history.json> --json` を使います。
入力は `import_id`、購入先、アカウント、観測日時、`records`、取得範囲の `coverage` です。
各明細は `item_id` を持ち、単件追加と同じ書籍と入手情報を使います。
購入先とアカウントは一括入力から共通に適用します。

同じ購入の識別には、購入先、アカウント、`external.order_id` と `external.line_id` を使います。
購入済み一覧では、安定した `external.holding_id` を使えます。
安定した明細の識別情報がなければ、購入を自動で追加せず、`missing_identity` の確認対象として保持します。
商品IDだけでは別の機会の購入を区別できません。

### 明細IDがない注文の派生キー

サイト発行の明細IDがなくても、注文全体を確認し、対象の商品IDと形態に対応する明細が一件だと確認できた場合は、`external.derived_identity` を渡せます。
これはMotteta側の派生キーで、`line_id` と `holding_id` は不明のまま保持します。
入力例は [history-derived.json](../examples/history-derived.json) です。

| 項目 | 意味 |
| --- | --- |
| `scheme` | 生成規則の版。現在は `order_product_format_v1`。 |
| `product` | `book.identifiers` またはISBNと一致する `namespace`、`scope`、`value`。 |
| `format` | 商品の `format` と一致する `print` または `digital`。 |
| `order_complete` | 注文内の購入明細全体を確認できたか。履歴全体の取得完了とは別。 |
| `matching_line_count` | 注文内で、この商品IDと形態に対応する明細の件数。不明なら `null`。リンクの本数や冊数ではない。 |
| `observed_at`、`reference`、`note` | 一意性を確認した日時、参照先、明細の対応関係を説明する根拠。 |

`order_complete: true` かつ `matching_line_count: 1` の場合だけ、次のJSON配列をキーにします。

```text
[source.id, account, "derived", "order_product_format_v1", order_id,
 product.namespace, product.scope, product.value, format]
```

数量、購入日、注文状態、確認日時はキーに含めません。
サイト発行の `holding_id`、次に `order_id` と `line_id` が優先し、派生キーはそれらがない場合に使います。
派生キーで新しい観測を取り込むときは、毎回注文内の一意性を確認します。
同じレコード内の最新の `purchase_history` 根拠と日時・参照先が一致する必要があり、以前の確認を新しく観測したものとして使い回しません。
CLIが確認するのは入力の整合性で、実際に画面全体を確認したかどうかは取得する側の責任です。

注文全体を確認できない場合や対応明細が複数ある場合は、派生キーで自動対応付けせず `missing_identity` にします。
同じ一括入力に、同じ注文・商品・形態の明細が複数あるのに一件だと主張した場合は入力エラーです。
既存の同じ購入候補があるのにキーが未登録の場合も、候補ID付きの `missing_identity` とし、購入を自動で増やしません。

### 既存購入への関連付け

明細ID不明のまま確定した購入へ派生キーを追加するには、既存の購入記録IDと [identity-binding.json](../examples/identity-binding.json) の形式の入力を使います。

```sh
motteta bind-identity <record-id> --input <binding.json> --dry-run --json
motteta bind-identity <record-id> --input <binding.json> --json
```

入力には新しい `request_id`、理由、既存購入と一致する `source_id`、`account`、`order_id`、確認済みの `derived_identity` を指定します。
対象が購入記録で、購入先、アカウント、注文番号、確定済みの商品ID、形態が一致することを検査します。
別の購入へ登録済みのキーは競合として拒否します。
同じ依頼IDと入力の再実行は再適用せず、別の依頼IDで同じ関連付けを指定した場合も既存として返します。

関連付けは対応表と監査用の観測へ保存し、購入件数、数量、購入日、状態、元の明細ID、購入状態の観測日時を変更しません。
履歴取り込みでも、一意性の根拠は各回の観測に保存します。現在の購入データへ永続的な保証として貼り付けるものではありません。
関連付け後の新しい観測では、そのキーで同じ購入を更新できます。
元のJSONと取り込みIDを書き換える必要はありません。

`coverage` は依頼した期間、確認できた期間、完了／一部完了／失敗、訪問した範囲、未確認箇所、再開情報を持ちます。
依頼した範囲全体を確認し、未確認箇所も再開位置も残っていない場合だけ `complete` にできます。
前回見つかった注文が今回見つからなくても削除やキャンセルにしません。
古い観測を取り込んでも新しい状態へ巻き戻しません。
取り込み全体を一つのトランザクションで反映し、途中の書き込みに失敗した場合は全体を取り消します。

## 訂正と確認対象の解消

`update <record-id> --input <correction.json> --json` では、新しい依頼ID、理由、`fields` に変更する項目を渡します。
`book` を変更するときは、その項目の全体を渡します。
訂正した項目はその後の自動取得より優先します。

`review list --json` で未解消の確認対象と候補を表示します。
`review resolve <review-id> --input <resolution.json> --json` に渡せる操作は次のとおりです。

| 操作 | 意味 |
| --- | --- |
| `keep_separate` | 候補を別のものとして保持し、確認対象を解消する。 |
| `same_work` | 対象と `target_record_id` を同じ作品として関連づける。紙、電子、別版の入手記録を別々に残す。 |
| `same_edition` | 二つの版の記録を、指定した対象の版へ統合する。購入件数は統合しない。 |
| `same_acquisition` | 同じ購入の二重記録を `target_record_id` へ統合する。数量が異なる場合は、先に根拠付きで訂正する。 |
| `accept_record` | 安定した明細IDがない確認対象を、人が確かめた一件として登録する。 |

`same_work`、`same_edition`、`same_acquisition` には、明示した根拠と対象の記録IDが必要です。
統合後も元の記録と観測を保持し、元の依頼を再実行して二重登録されることを防ぎます。

確認済みの派生キーを持つ `missing_identity` では、`same_acquisition` に既存の購入IDを渡すと、そのキーを既存購入へ関連付けて解消できます。
この操作は未取り込みの観測の数量や状態を既存購入へ上書きしません。
既存の同じ購入候補がある派生キーの確認対象は、二重登録を防ぐため `accept_record` では確定できません。

## 応答と終了コード

`--json` はコマンドの前後どちらにも指定できます。
書き出し以外の機械向け応答は標準出力のJSONで、引数や入力の不備も同じ形式で返します。
購入記録の作成、更新、既存件数、確認対象、記録IDを結果に含めます。
`search`、`check`、`status` はそれぞれの照会結果を返します。

| コード | 意味 |
| --- | --- |
| `0` | 正常に完了。照合の結果、記録がない場合も含む。 |
| `2` | 入力や引数が不正。 |
| `3` | 確認対象、未取得範囲、競合が残っている。保存できた記録もJSONで明示する。 |
| `4` | 台帳や実行環境の問題で実行できない。 |

`check` は、識別子と形態が一致する `exact`、同じ作品として確認済みの `related`、確認が必要な `possible` を区別します。
巻が双方で分かっていて異なる記録は、ISBN、商品ID、書名のどの照合でも候補から除外し、作品の関連をたどる起点にも使いません。
巻が不明な場合は推測で除外せず、紙と電子の違いだけでも候補を除外しません。
書名が似ているだけの記録や、識別情報が不足している記録は `possible` とし、確認済みの作品との関係を自動で作りません。

通常の表示は、確定した版または作品の対応がある場合の「記録あり」、候補だけの場合の「同じ本の可能性あり」、該当記録がない場合の「記録なし」です。
注文状態、所持状態、紙と電子の区別はポップアップの詳細で示し、判定文の種類は増やしません。
商品ページでは照合結果が返ってから判定を表示し、「確認中…」を挟みません。
同じ商品の再照合中は前の判定を保持し、結果が変わらなければ表示を書き換えません。商品または既知の形態が変わった場合は、古い判定を消します。
記録がない `no_match` と、識別情報不足の `unidentified`、実行不能の `error` も区別します。
読み取りや接続ができなかった場合の判定文は「確認できません」とし、理由をポップアップへ表示します。
「記録なし」は取り込み済みの範囲についての結果です。
