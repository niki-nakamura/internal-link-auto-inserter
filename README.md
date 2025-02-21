# 内部リンク自動挿入システム
# internal-link-auto-inserter

WordPress の投稿記事へ自動的に内部リンクを挿入するためのスクリプトや管理ツールをまとめたリポジトリです。  
ローカル/Codespacesの Dev Container で動作させたり、GitHub Actions を使って定期的に記事情報を取得したり、リンクの使用状況を管理できます。

## 1. 概要

- **主な機能**  
  1. **記事クローリング (crawl_links.py)**  
     - WordPress REST API から対象サイトの記事一覧を取得し、`data/articles.json` に保存します。  
     - `/media/column/` を含む投稿のみ抽出して管理対象としています。
  
  2. **リンク挿入 (insert_links.py)**  
     - linkMapping.json（キーワード→URL対応） を基に、対象の WordPress 記事に内部リンクを挿入します。  
     - WordPress の Basic 認証 (ユーザ名/パスワード) を用いて、POSTで記事を更新します。

  3. **リンク使用状況検出 (detect_link_usage.py)**  
     - （将来的には）挿入済みリンクを解析し、キーワードがどの記事で何回使われているかを `data/linkUsage.json` へ記録します。  
     - 現在はテスト状態で、今後 GitHub Actions と組み合わせて運用する予定です。

  4. **リンクマッピング管理 (manage_link_mapping.py)**  
     - Streamlit アプリ。`data/linkMapping.json` と `data/linkUsage.json` を管理するツールです。  
     - カテゴリごとのキーワード・URL 登録や、記事ごとのリンク使用可否などをGUIで編集可能です。
  
- **GitHub Actions ワークフロー**  
  - **crawl-links.yml**  
    - 週1回（または手動）で実行され、最新の WordPress 記事を取得 → `articles.json` を自動更新  
  - **link-insertion.yml**  
    - 手動トリガーで実行し、リンク挿入スクリプトを走らせます。  
    - WordPress の URL / ユーザ名 / パスワードは GitHub Secrets 経由で注入します。  
  - **link-usage-detect.yml**  
    - リンク使用状況検出を行うワークフロー（サンプル）。必要に応じて拡張・運用します。
  
- **Dev Container (.devcontainer)**  
  - Python 3.12 ベースのコンテナで、Streamlit や requests などをインストールし、`manage_link_mapping.py` を簡単に起動できます。  
  - VSCode / GitHub Codespaces 上での開発を想定しています。

## 2. フォルダ構成

```
internal-link-auto-inserter/
├─ .devcontainer/
│   └─ devcontainer.json              # Python3.12ベースのコンテナ定義
├─ .github/workflows/
│   ├─ crawl-links.yml                # 記事クローラー(週1または手動)
│   ├─ link-insertion.yml             # リンク挿入(手動実行)
│   └─ link-usage-detect.yml          # リンク使用状況検出(サンプル)
├─ data/
│   ├─ linkMapping.json               # キーワード→URLマッピング
│   ├─ linkUsage.json                 # リンク使用状況(記事ごとに何回挿入されたか)
│   └─ articles.json                  # WordPressから取得した記事一覧(id/title/url)
├─ scripts/
│   ├─ crawl_links.py                 # WordPress記事クローリング
│   ├─ detect_link_usage.py           # リンク使用状況の検出(未完成/拡張予定)
│   ├─ insert_links.py                # WordPress記事へのリンク挿入
│   ├─ manage_link_mapping.py         # Streamlitアプリ（リンク管理GUI）
│   └─ ...
├─ README.md                          # ← (本ファイル。運用手順などを記載)
├─ packages.txt                       # aptパッケージ一覧
└─ requirements.txt                   # pipパッケージ一覧 (streamlit, requests 等)
```

## 3. セットアップ手順

### 3.1 Dev Container / Codespaces を使用する場合

1. 本リポジトリを [GitHub Codespaces](https://docs.github.com/ja/codespaces) か VSCode の Dev Container で開きます。  
2. Dev Container が起動すると、`requirements.txt` と `packages.txt` がインストールされます。  
3. コンテナ起動後、`manage_link_mapping.py` を自動的に Streamlit で立ち上げる設定になっています。  
   - `localhost:8501` / Codespaces の場合はポート転送でアクセスしてください。  
4. Webブラウザ（VSCodeのプレビュー or 外部ブラウザ）でアクセスし、リンクマッピングや使用状況をGUI上で操作できます。

### 3.2 ローカルPC（Dev Containerを使わない場合）

1. Python 3.12 以上がインストールされていることを確認します。  
2. リポジトリをクローン後、`pip install -r requirements.txt` を実行して依存関係を導入します。
3. `scripts/manage_link_mapping.py` を起動し、Streamlitアプリを使う場合:
   ```bash
   streamlit run scripts/manage_link_mapping.py --server.enableCORS false --server.enableXsrfProtection false
   ```
   - ポート番号はデフォルト8501 です。  

## 4. 主要スクリプトの使い方

### 4.1 記事クローリング: `crawl_links.py`

- WordPress REST API を使用して記事情報を取得 → `data/articles.json` に上書き保存します。  
- 例:  
  ```bash
  python scripts/crawl_links.py
  ```
- GitHub Actions (`.github/workflows/crawl-links.yml`) により週1回自動実行 + コミットされる設定になっています。

### 4.2 リンク挿入: `insert_links.py`

- `data/linkMapping.json`（キーワードとリンク先URLの対応表）を読み込み、WordPressの記事に内部リンクを挿入します。  
- WordPress の更新には Basic 認証を使用するため、以下の環境変数を設定してください:
  - `WP_URL` … 例: `https://example.com`
  - `WP_USERNAME` … Basic 認証ユーザ名
  - `WP_PASSWORD` … Basic 認証パスワード
- 例:  
  ```bash
  WP_URL="https://example.com" \
  WP_USERNAME="my-user" \
  WP_PASSWORD="my-pass" \
  python scripts/insert_links.py
  ```
- GitHub Actions (`.github/workflows/link-insertion.yml`) で手動実行した場合も同様に Secrets を注入します。

### 4.3 リンク使用状況検出: `detect_link_usage.py`

- 現状はサンプル実装です。記事本文を取得し、既に挿入されたリンクを解析して `data/linkUsage.json` に書き込む想定です。  
- 今後、頻度制御や重複挿入チェックなどを行いたい場合に活用してください。

### 4.4 Streamlit管理ツール: `manage_link_mapping.py`

- `data/linkMapping.json` や `data/linkUsage.json` をGUIで編集し、GitHub へコミットまで行うことができます。  
- **カテゴリー** → **キーワード一覧** → **URL** の構成で管理可能です。  
- 記事ごとに「このキーワードを挿入する／しない」の制御を手動で行うこともできます。

## 5. GitHub Actions

- [**crawl-links.yml**](.github/workflows/crawl-links.yml)  
  - **毎週月曜午前3時**(cron)に自動実行  
  - 手動トリガーも可能  
  - 取得した `articles.json` を GitHub に自動コミット
- [**link-insertion.yml**](.github/workflows/link-insertion.yml)  
  - **手動トリガーのみ**  
  - 環境変数 (Secrets) を使ってリンク挿入を実行
- [**link-usage-detect.yml**](.github/workflows/link-usage-detect.yml)  
  - （現在はサンプルのみ。運用時は適宜設定）

## 6. データファイルの役割

- `data/articles.json`  
  - WordPress REST API からクローリングした記事リスト。  
  - `id`, `title`, `url` の最低限の情報を保持。
- `data/linkMapping.json`  
  - 内部リンクにしたい **キーワード** と **URL** のマッピング。  
  - カテゴリ単位で整理しており、Streamlit管理ツールで追加・削除・編集できます。
- `data/linkUsage.json`  
  - 挿入済みリンクの記録。  
  - キーワードごとに、「どの記事に何回挿入したか」を集計する想定。

## 7. 注意事項・運用のポイント

- **WordPress への更新権限**  
  - `insert_links.py` を実行すると投稿が直接更新されます。  
  - 実行前に必ずテスト環境やステージングで動作確認することを推奨します。
- **挿入回数の管理**  
  - 現在は1記事あたりキーワード1回までを想定した置換ロジックです。  
  - 既にリンク付きになっている箇所は再挿入しない仕組みになっていますが、過剰に挿入されないよう注意してください。
- **記事本文のブロック崩れ**  
  - `insert_links.py` は WordPress の raw コンテンツをダイレクトに書き換えます。  
  - 特殊なブロック構成の場合、予期せぬ崩れが生じる可能性があるため事前テストを必ず実施してください。

## 8. ライセンス

- 本リポジトリのスクリプト部分は MIT License 等で運用を想定しています（実プロジェクトの方針にあわせて適宜設定してください）。
- WordPress から取得する記事データ（`articles.json` など）は、あくまで管理目的に限り社内/個人用にご利用ください。







