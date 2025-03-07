

# README

以下は、本リポジトリ **`internal-link-auto-inserter`** を利用・開発する方向けの README の例です。  
各種ファイル・ディレクトリの役割、および使用方法を説明しています。

---

## internal-link-auto-inserter

WordPress 記事へ自動で内部リンクを挿入するためのスクリプト群、および管理ツールです。  
GitHub Actions や Streamlit アプリを使い、以下の自動化を実現します:

- WordPress REST API から記事一覧を取得し、`articles.json` に保存  
- 記事本文中へ所定のキーワードに応じたリンクを自動挿入・削除  
- 現状のリンク使用状況をクロールし、`linkUsage.json` として可視化  
- YAML / JSON 等を GitHub Actions で自動コミット

### 目次

1. [ディレクトリ構成](#ディレクトリ構成)
2. [動作環境](#動作環境)
3. [セットアップ方法](#セットアップ方法)
4. [主要ファイルの説明](#主要ファイルの説明)
5. [GitHub Actions ワークフロー](#github-actions-ワークフロー)
6. [Streamlit 管理画面](#streamlit-管理画面)
7. [ライセンス](#ライセンス)

---

## 1. ディレクトリ構成

```
internal-link-auto-inserter/
├─ .devcontainer/         # Dev Container / GitHub Codespaces 設定
│   └─ devcontainer.json
├─ .github/workflows/     # GitHub Actions のワークフロー定義
│   ├─ crawl-links.yml
│   ├─ link-insertion.yml
│   └─ link-usage-detect.yml
├─ data/
│   ├─ articles.json       # 取得した記事一覧(ID, タイトル, URL)
│   ├─ linkMapping.json    # キーワード→URL のマッピング (カテゴリ階層)
│   └─ linkUsage.json      # キーワードごとのリンク使用状況 (記事IDと回数)
├─ scripts/
│   ├─ crawl_links.py      # WP REST API から記事一覧を取得し、articles.json を生成
│   ├─ detect_link_usage.py# 記事をクロールしてリンク使用状況を更新
│   ├─ insert_links.py     # WordPress 記事へ内部リンクを挿入・削除
│   └─ manage_link_mapping.py # Streamlit アプリ本体
├─ packages.txt            # apt パッケージ群 (devcontainer 用)
├─ requirements.txt        # Python ライブラリ (Streamlit, requests 等)
└─ README.md               # 本ファイル (説明書き)
```

---

## 2. 動作環境

- Python 3.9 以降 (開発用の .devcontainer は Python 3.12 ベース)
- 必要 Python ライブラリ: `streamlit`, `requests` (詳しくは `requirements.txt` を参照)
- WordPress (REST API が有効になっていること)
- GitHub Actions を使用する場合は GitHub リポジトリ、および適切なシークレット設定が必要

---

## 3. セットアップ方法

### 3.1 リポジトリをクローン

```bash
git clone https://github.com/＜YOUR-ACCOUNT＞/internal-link-auto-inserter.git
cd internal-link-auto-inserter
```

### 3.2 Python 依存関係のインストール

```bash
pip install -r requirements.txt
```

※ 開発環境として [Dev Container](https://code.visualstudio.com/docs/remote/containers) / [GitHub Codespaces](https://github.com/features/codespaces) を利用する場合は、`.devcontainer/devcontainer.json` により自動でセットアップが走ります。

### 3.3 環境変数 (WordPress 用認証情報) の設定

WordPress の Basic 認証用に、以下の環境変数を設定します。

- `WP_URL` … WordPress サイトの URL  (例: `https://example.com`)
- `WP_USERNAME` … Basic 認証のユーザー名
- `WP_PASSWORD` … Basic 認証のパスワード

ローカルでテストする場合は、 `.env` ファイルなどを使って環境変数を用意すると便利です。

---

## 4. 主要ファイルの説明

### 4.1 `scripts/crawl_links.py`

WordPress REST API (例: `https://your-site.com/wp-json/wp/v2/posts`) から投稿記事を全件取得し、  
`/media/column/` を含む URL の記事のみを抽出して `data/articles.json` に保存するスクリプトです。

- **実行例**:  
  ```bash
  python scripts/crawl_links.py
  ```
- GitHub Actions (`crawl-links.yml`) でも定期実行が設定されています。

### 4.2 `scripts/detect_link_usage.py`

- `articles.json` 内の各記事ページを実際に GET し、内部リンクの使用状況を調査します。  
- 調査結果を `data/linkUsage.json` に書き込みます。  
- **実行例**:  
  ```bash
  python scripts/detect_link_usage.py
  ```

### 4.3 `scripts/insert_links.py`

- `data/linkUsage.json` と `data/articles.json` を元に、WordPress の特定記事へリンクを挿入・削除します。  
- 環境変数 `WP_URL`, `WP_USERNAME`, `WP_PASSWORD` が必要です。  
- **実行例**:  
  ```bash
  WP_URL="https://example.com" WP_USERNAME="user" WP_PASSWORD="pass" python scripts/insert_links.py
  ```

### 4.4 `scripts/manage_link_mapping.py`

- Streamlit アプリ (Web UI) による管理ツール本体です。  
- `data/linkMapping.json` の編集、`articles.json` の取得、`linkUsage.json` の編集やリンク挿入をまとめて行えます。  
- **実行例**:  
  ```bash
  streamlit run scripts/manage_link_mapping.py
  ```
- Dev Container/Codespaces 上では、 `.devcontainer/devcontainer.json` の `postAttachCommand` により自動起動されます。

---

## 5. GitHub Actions ワークフロー

### 5.1 `crawl-links.yml`

- 手動または週1回（月曜 3:00）に起動し、`crawl_links.py` を実行
- 取得した記事リスト (`articles.json`) をコミット & プッシュ

### 5.2 `link-insertion.yml`

- 手動トリガーで起動
- `insert_links.py` を実行し、WordPress 記事本文にリンクを挿入

### 5.3 `link-usage-detect.yml`

- 手動または週1回（月曜 3:00）に起動
- `detect_link_usage.py` を実行し、`linkUsage.json` を更新 & コミット

---

## 6. Streamlit 管理画面

`scripts/manage_link_mapping.py` を起動すると、以下の機能が利用できます。

1. **リンクマッピング管理**  
   - カテゴリごとにキーワードとリンク先 URL を設定
   - `linkMapping.json` に保存
2. **全記事リンク管理**  
   - `articles.json` に登録された記事一覧を参照し、キーワードの ON/OFF を一括設定
   - `linkUsage.json` に反映し、必要に応じて WordPress 投稿へ即時反映
3. **WordPress記事一覧管理**  
   - WordPress REST API から記事取得 → `articles.json` へ保存

---

## 7. ライセンス

このリポジトリのコードは、特に断りがない限り [MIT License](LICENSE) にて公開しています。
