# Gihyo Digital Publishingの履歴取得

対象は [Gihyo Digital Publishing](https://gihyo.jp/dp) で購入した電子書籍です。
「gihyo」「技評の電子書籍」という依頼は、このストアとして扱います。
既存の購入先IDを再利用し、初めて登録する場合は `source.id: gihyo-dp`、`source.name: Gihyo Digital Publishing`、`source.kind: online` とします。

## マイページを開く

1. 接続済みのChromeで[マイページ](https://gihyo.jp/dp/my-page)を開きます。
2. 購入済みの書籍一覧を読みます。画面の案内は[マイページの説明](https://gihyo.jp/dp/help/buy/mypage)を参照してください。
3. 一覧の続きを確認し、依頼期間に該当する入手を取得します。購入日のない項目は、[共通の期間と取得範囲の扱い](../collection.md#購入済み一覧と取得範囲)に従います。

## 記録する内容

| 項目 | 読み取り方 |
| --- | --- |
| 書名と版 | マイページの対象項目から特定し、必要な書誌情報だけ対象の商品ページで補います。 |
| 形態とファイル形式 | `book.format: digital`。PDFとEPUBの両方を確認できた場合は `file_formats: ["pdf", "epub"]` とし、同じ入手で利用できる形式を一つにまとめます。 |
| 購入日 | 購入日として表示された値を使います。 |
| 入手の根拠 | マイページの一覧は `evidence.kind: owned_list`。一覧の参照先と観測日時を記録します。 |
| ISBN | 購入した電子版と対応する値だけを使い、分からなければ `null` にします。 |

対象の電子書籍URLが `/dp/ebook/年/ISBN` の形なら、そのISBNをチェック桁まで検証して使います。
商品IDはハイフンを除いた同じ値とし、`book.identifiers` に `namespace: gihyo-dp`、`scope: gihyo.jp/dp` として保存します。

利用可能な形式は、[取得方法の説明](https://gihyo.jp/dp/help/reading/contents)にある形式ごとの表示で確認します。
入手の識別と再取り込みは[共通の手順](../collection.md#入手の識別と再取り込み)に従います。
