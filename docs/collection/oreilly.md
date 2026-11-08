# O’Reilly Japan Ebook Storeの履歴取得

対象は [O’Reilly Japan Ebook Store](https://www.oreilly.co.jp/ebook/) で購入した電子書籍です。
「O’Reilly」「oreilly」という依頼は、このストアとして扱います。
oreilly.comの定額学習サービスで閲覧できる本は、買い切りの購入に含めません。
既存の購入先IDを再利用し、初めて登録する場合は `source.id: oreilly-japan`、`source.name: O’Reilly Japan Ebook Store`、`source.kind: online` とします。

## 購入済み一覧を開く

1. 接続済みのChromeでストアを開きます。
2. ログイン後の「購入済みの商品」を開きます。画面の案内は[利用案内](https://www.oreilly.co.jp/ebook/help.html)を参照してください。
3. 一覧の続きを最後まで確認し、依頼期間に該当する入手を取得します。日付が分からない一覧は、[共通の期間と取得範囲の扱い](../collection.md#購入済み一覧と取得範囲)に従います。

## 記録する内容

| 項目 | 読み取り方 |
| --- | --- |
| 書名と版 | 購入済み一覧の対象行を起点にし、必要な書誌情報だけ商品ページで補います。 |
| 形態とファイル形式 | Ebookの入手は `book.format: digital`。その購入で提供されると確認できた形式だけ、`pdf` や `epub` などの入力値で `file_formats` に入れます。 |
| 購入日 | 購入日として表示された値を使います。 |
| 入手の根拠 | 購入済み一覧の観測は `evidence.kind: owned_list`。一覧の参照先と観測日時を記録します。 |
| ISBN | 購入した電子版との対応を確認できた値を使います。 |

商品ページの `/books/` の後の13桁の番号は、`book.identifiers` に `namespace: oreilly-japan`、`scope: oreilly.co.jp` として保存できます。

PDFとEPUBが一つの購入に付いていれば、一件の入手記録にまとめます。
入手の識別と再取り込みは[共通の手順](../collection.md#入手の識別と再取り込み)に従います。
