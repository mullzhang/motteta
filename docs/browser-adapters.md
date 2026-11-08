# ブラウザ拡張のサービスを追加する

サービス固有の設定と処理は、`extension/src/adapters/services/` のサービスごとのフォルダへ置きます。
新しいフォルダの `adapter.json` と `adapter.ts` を作成してビルドすると、自動で登録とアクセス権限へ反映されます。
共通のレジストリ、表示処理、バックグラウンド処理、manifestの雛形にサービス名を追加する必要はありません。

## ファイルの役割

| ファイル | 管理するもの |
| --- | --- |
| 各サービスの `adapter.json` | サービスID、対象URL、識別子の範囲、ページ内の表示位置。 |
| 各サービスの `adapter.ts` | 商品URLの識別、商品IDの抽出、書籍情報の読み取り。 |
| `src/adapters/types.ts` | 設定と抽出処理の共通の型。サービス名は列挙しない。 |
| `src/adapters/registry.ts` | 設定に一致するアダプターの選択と、共通の照会形式への変換。 |
| `src/adapters/helpers.ts` | ISBN、書籍の構造化情報など、サービスに依存しない読み取り処理。 |
| `manifest.base.json` | 拡張機能の名前、版、公開鍵、共通の権限と実行ファイルの設定。 |
| `generate-adapters.mjs` | サービスフォルダの収集と、登録コードおよびmanifestの生成。 |

`src/generated/adapters.ts` と `manifest.json` は生成物です。
Gitで追跡して生成元との整合を検査しますが、手作業で編集しません。
ビルド時にも再生成し、対応するコードを拡張機能へ同梱します。
サービスの実行コードを外部サイトから読み込む仕組みはありません。

## 設定を書く

以下は架空のサービスの例です。
`extension/src/adapters/services/example-store/adapter.json` を作成します。

```json
{
  "id": "example-store",
  "matches": ["https://books.example.invalid/books/*"],
  "scope": "books.example.invalid",
  "anchorSelector": ".product-title"
}
```

`id` は英小文字で始まる英小文字、数字、ハイフンの識別子で、他のアダプターと重複させません。
照会に使う商品識別子の名前空間にも、この値を使います。
`scope` は商品IDが一意になる範囲です。
ショップごとに商品IDが異なる場合などは、抽出処理でこの値にショップIDを付けられます。
`id` と `scope` は保存済みの商品IDとの照合に使うため、既存サービスの値を変える場合は保存済みの対応関係も考慮します。

`matches` はHTTPSのURLに限定し、ホストの完全一致または `*.example.invalid` の形と、パスの `*` に対応します。
必要に応じてポートも指定できます。
クエリー文字列を含めてパスを照合し、フラグメントは照合に含めません。
`<all_urls>`、ホスト全体の `*`、HTTPなどは受け付けません。[Chromeの一致条件](https://developer.chrome.com/docs/extensions/develop/concepts/match-patterns)、[URLとクエリーの照合](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Match_patterns#path)

コンテンツスクリプトの実行対象と、送信元のURL検査に同じ定義を使います。
`host_permissions` は同じ定義のホストから生成します。
ホスト権限ではパスが無視されるため、生成する権限のパスは `/*` とします。[Chromeのホスト権限の形式](https://developer.chrome.com/docs/extensions/develop/concepts/match-patterns)

`anchorSelector` は、短い判定を直後に表示する要素のCSSセレクターです。
商品本体の見出しや商品名欄を指定し、サイトのロゴに一致する汎用の見出しは含めません。
一致する要素がない場合はページへ判定を挿入せず、再描画後に表示先が現れた時点で挿入します。

## 抽出処理を書く

同じフォルダに `adapter.ts` を作成し、`AdapterHandler` を満たすオブジェクトを既定のエクスポートにします。
現在のURLに対応するBook形式の構造化情報がある場合は、共通の読み取り処理を使えます。

```typescript
import { extractStructuredBook } from "../../helpers";
import type { AdapterHandler } from "../../types";

const handler: AdapterHandler = {
  productAt(url, settings) {
    const match = url.pathname.match(/^\/books\/([^/]+)\/?$/);
    return match ? { scope: settings.scope, id: match[1] } : null;
  },
  extract: extractStructuredBook,
};

export default handler;
```

独自のDOMを読む場合は、`extract(doc, url, product)` を実装します。
確認できた `product` と、書名と形態を含む `book` を返します。
共通処理がサービスID、商品識別子、形式の版、URLを付けて、Native Messagingの照会形式に変換します。
選択中の商品IDがURLから取得した値と異なる場合は、抽出結果の `product.id` に現在の値を返します。

商品本体を特定できない場合は `null` を返し、別商品のおすすめ欄から情報を補いません。
複数のアダプターが同じ商品URLを引き受けた場合も、登録順によって一つを選ばず、未特定として扱います。

## 生成して検証する

リポジトリのルートから実行します。

```sh
mise exec -- npm run adapters --prefix extension
mise run check
```

`npm run build --prefix extension` と `mise run build` でも、アダプターの登録とmanifestを再生成します。
新しいファイルを追加した後や設定を変更した後は、検査の前に生成してください。
`npm run check` と `npm test` は生成元と生成物が食い違っていると失敗します。

アダプターの追加時は、商品ID、ISBN、形態、書名付近への配置、対象外URLの除外を自動テストに含めます。
生成した拡張機能から照会できることも確認します。
テストには架空の書籍データを使い、実際の購入履歴や利用者の保存HTMLをリポジトリへ追加しません。
