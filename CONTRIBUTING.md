# 開発手順

Mottetaを利用するための導入と操作は、[README](README.md)と[初期設定](docs/setup.md)を参照してください。
この文書では、コードの変更、テスト、配布物の作成を説明します。

最初にmiseの設定内容を確認し、プロジェクトを信頼してから `mise install --locked` と `mise run setup` を実行します。
Pythonとuvはmiseで導入し、Pythonのアプリと開発用依存関係はuv、拡張機能の依存関係はnpmで管理します。
`mise.toml`、`mise.lock`、`uv.lock`、`extension/package-lock.json` をGitで管理します。

| コマンド | 用途 |
| --- | --- |
| `mise run setup` | 依存関係とローカルのGitフックを導入する。 |
| `mise run deps` | CIなどで、Gitフックを登録せず依存関係を導入する。 |
| `mise run format` | PythonのコードをRuffで整形する。 |
| `mise run lint` | Ruffの静的検査、整形の確認、生成済みの型定義とアダプター登録の確認、TypeScriptの型検査を実行する。 |
| `mise run test` | Pythonと拡張機能のオフライン自動テストを実行する。 |
| `mise run build` | Pythonのwheelとソース配布物、拡張機能、配布用ZIPを作成する。 |
| `mise run check` | ロック、スキーマ、pre-commit、テスト、ビルドをまとめて確認する。 |

pre-commitは静的検査、整形、JSON、YAML、TOML、末尾空白と改行を確認します。
`check_all.py` は追跡済みファイルと新規ファイルを一度に対象にします。
通常のフックはコミット対象のファイルから起動します。

## 入力形式を変更する

Pythonの入力契約は `src/motteta/core/models.py` を正本とします。
入力を変更したら、次の手順でスキーマと拡張機能の型定義を再生成します。

```sh
mise exec -- uv run --locked python scripts/generate_schemas.py
mise exec -- npm run schemas --prefix extension
mise run check
```

未知の入力項目は拒否します。

## 新しい購入先や商品ページに対応する

履歴取得は共通のJSONへ変換し、取得先ごとの注意点を `docs/collection.md` に追記します。
商品ページの対応は `extension/src/adapters/services/<service-id>/` に `adapter.json` と `adapter.ts` を追加します。
対象URL、商品IDの範囲、表示位置、抽出処理をそのフォルダにまとめ、人工的なHTML資料とテストを用意します。
アダプターの登録と権限設定はビルド時に生成します。
生成方法と契約は [ブラウザアダプターの追加手順](docs/browser-adapters.md)を参照してください。
照合や重複登録の規則は共通のPython処理へ置きます。

回帰テストには、架空の書籍情報を使ったJSONとHTMLを用意します。

## 公開する変更

公開文書は `README.md` と `docs/`、検証結果や作業ログは `docs_local/` に置きます。
`docs_local/` はGitの管理対象外です。
台帳、取得した履歴、認証情報はリポジトリ外へ保存します。
配布物は `dist/` に生成します。

## 技術資料

- [構成と判定の境界](docs/architecture.md)。
- [入力と応答の契約](docs/contracts.md)と[入力例](examples/)。
- [履歴取得時の判断基準](docs/collection.md)。
- [ブラウザアダプターの追加手順](docs/browser-adapters.md)。
