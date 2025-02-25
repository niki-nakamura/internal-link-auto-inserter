

# internal-link-auto-inserter

特定の WordPress 記事に対して「内部リンク挿入」を自動・半自動化するためのリポジトリです。  
以下のようなフローで、記事の取得・リンクマッピング・自動挿入・使用状況の可視化を行います。

## 機能概要

1. **記事一覧の取得 (crawl_links.py)**  
   WordPress REST API から `/media/column/` を含む投稿を取得し、`data/articles.json` に保存します。

2. **リンクマッピング (linkMapping.json)**  
   - 「キーワード → リンク先URL」を登録し、さらにそれをカテゴリごとにまとめるファイルです。
   - キーワードが記事本文内に登場した場合、そのテキストを `<a href="指定URL">...</a>` に自動変換したいときのマッピングを管理します。

3. **リンク使用状況 (detect_link_usage.py & linkUsage.json)**  
   - 現在、どの記事にどの内部リンク(キーワード)が挿入されているか、何回挿入されているかを可視化して管理するためのファイルです。

4. **内部リンク自動挿入 (insert_links.py)**  
   - `linkUsage.json` で「ON」(= `articles_used_in` に記載)になっている記事に対して、WordPress の記事本文(HTML)を取得し、キーワードをリンク化して再度記事を更新します。
   - ひとつの記事あたり挿入するリンク数は最大3つ (暫定) に制限しています。

5. **Streamlit GUI (manage_link_mapping.py)**  
   - コンテナ起動時に Streamlit アプリが立ち上がり、Web UI から linkMapping, linkUsage, articles などを管理できるようにしています。

## 開発環境のセットアップ

本リポジトリには Dev Container (`.devcontainer/devcontainer.json`) の設定が含まれています。  
VSCode などで[Dev Containers](https://containers.dev/) または [GitHub Codespaces](https://github.com/features/codespaces) を利用することで、コンテナ環境が自動で構築されます。

### 1. リポジトリをクローン
```bash
git clone https://github.com/[YOUR-ACCOUNT]/internal-link-auto-inserter.git
cd internal-link-auto-inserter
```

### 2. Dev Container / Codespaces で開く
- VSCode の「Remote Containers」もしくは「Codespaces」を使用して、`.devcontainer` の設定に従ったコンテナを起動します。

### 3. コンテナ起動時の処理
- `packages.txt` に書かれた APT パッケージがインストールされます。
- `requirements.txt` に書かれた Python ライブラリがインストールされます。
- `scripts/manage_link_mapping.py` が `streamlit` で自動起動し、ポート `8501` がフォワードされます。

ブラウザまたは VSCode の Port Forward 機能経由で `http://localhost:8501` (Codespaces の場合はリダイレクトURL) にアクセスすることで、
GUI が利用可能です。

## GitHub Actions 設定

### 1. [crawl-links.yml](.github/workflows/crawl-links.yml)

- **週1回 (月曜午前3時) または手動** で起動
- WordPress REST API から `/media/column/` を含む記事一覧を取得し、`data/articles.json` を更新・コミットします。

```yaml
name: Crawl links
on:
  workflow_dispatch:
  schedule:
    - cron: '0 3 * * 1'

jobs:
  run-crawl-links:
    steps:
      # 省略（詳細はファイルを参照）
```

### 2. [link-usage-detect.yml](.github/workflows/link-usage-detect.yml)

- **週1回 (月曜午前3時) または手動** で起動
- 取得済みの記事 (`data/articles.json`) を実際に GET して、HTML 内に既存で埋め込まれているリンクがどれだけあるかを解析し、`data/linkUsage.json` に保存・コミットします。

```yaml
name: Detect link usage
on:
  workflow_dispatch:
  schedule:
    - cron: '0 3 * * 1'

jobs:
  detect-link-usage:
    steps:
      # 省略（詳細はファイルを参照）
```

### 3. [link-insertion.yml](.github/workflows/link-insertion.yml)

- **手動起動** のみ
- 環境変数 (GitHub Secrets) の `WP_URL`, `WP_USERNAME`, `WP_PASSWORD` を使い、実際の WordPress 記事にリンクを挿入 (更新) します。

```yaml
name: Internal Link Insertion
on:
  workflow_dispatch:

jobs:
  link-insertion-job:
    steps:
      # 省略（詳細はファイルを参照）
```

## 主なスクリプト

### 1. `scripts/crawl_links.py`
- WordPress の REST API から投稿を取得し、`/media/column/` を含む記事だけを `data/articles.json` に保存します。

### 2. `scripts/detect_link_usage.py`
- `articles.json` の URL にアクセスし、リンクマッピング (`linkMapping.json`) の URL が実際に HTML にいくつ含まれているかをカウント。
- 結果を `linkUsage.json` に保存します。

### 3. `scripts/insert_links.py`
- `linkUsage.json` を見て、「挿入対象記事 (articles_used_in)」となっている記事本文を取得。
- 該当キーワードが見つかれば `<a href="...">...</a>` に置換し、記事を上書き更新します (WP API を使用)。

### 4. `scripts/manage_link_mapping.py` (Streamlit アプリ)
- ブラウザ上で `linkMapping.json`, `linkUsage.json`, `articles.json` を管理可能なツール。
- VSCode DevContainer / Codespaces 起動時に自動実行します（`port=8501` でアクセス）。

## 利用手順の概要

1. **WordPress の記事一覧取得**  
   - 手動もしくは `crawl-links.yml` により `data/articles.json` を更新

2. **linkMapping の編集**  
   - Streamlit UI (localhost:8501) または直接 JSON ファイルを編集  
   - 「キーワード → リンクURL」をカテゴリごとに登録

3. **linkUsage の更新**  
   - 手動もしくは `link-usage-detect.yml` により全記事をクロールし、実際に貼られているリンクを `data/linkUsage.json` に反映

4. **リンク挿入**  
   - Streamlit UI の「記事別リンク管理（手動）」タブなどで「ON」にしたい記事×キーワードを設定
   - `link-insertion.yml` を手動実行 (GitHub Actions) あるいは `scripts/insert_links.py` をローカルで直接起動

5. **最終チェック**  
   - リンクが正しく挿入されているかを再度 `detect_link_usage.py` などで確認

## 環境変数 / Secrets

- **WP_URL**: WordPress の REST API を呼ぶベースURL (例: `https://example.com`)
- **WP_USERNAME**: Basic 認証に使用するユーザー名 (WPユーザー)
- **WP_PASSWORD**: Basic 認証に使用するパスワード
- **GITHUB_TOKEN**: (オプション) GitHub API にコミットするときに使用

GitHub Actions 実行時には [Repository Secrets](https://docs.github.com/ja/actions/security-guides/encrypted-secrets) にこれらを登録します。  
ローカルや Codespaces で試す場合は `.env` や VSCode の「Settings」などに設定しても良いでしょう。

## .devcontainer/devcontainer.json の動作

- Python 3.12 ベースイメージ
- `updateContentCommand` により、`packages.txt` と `requirements.txt` が自動インストール
- `postAttachCommand` で `scripts/manage_link_mapping.py` (Streamlit) が自動起動
