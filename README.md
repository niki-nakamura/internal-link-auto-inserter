

**README.md**

```markdown
# 内部リンク自動挿入システム

## 概要
このリポジトリは、GitHub Actions と独自スクリプト（例：Python）を活用し、WordPress の投稿本文に対して自動で内部リンクを挿入する仕組みを実装するためのサンプルプロジェクトです。本システムでは、以下の機能を実現します。

- **自動リンク挿入ロジック**  
  投稿本文内の指定キーワードに対して、事前に定義したリンク先 URL を挿入します。  
  ※1記事あたりのリンク挿入数や、既存リンクの除外など、細かい制御が可能です。

- **WordPress 連携**  
  WP REST API や WP-CLI＋SSH を利用して、対象の投稿を取得・更新します。  
  認証情報は GitHub Actions の Secrets で安全に管理します。

- **GitHub Actions による自動化**  
  手動実行、スケジュール実行、プッシュ時など任意のトリガーでスクリプトを実行します。

- **バージョン管理**  
  投稿本文やリンク設定ファイルを GitHub 上で管理し、変更履歴を追跡可能にします。

## フォルダ構成
以下はリポジトリの基本的なフォルダ構成例です。

```
my-internal-linker/
├─ .github/
│   └─ workflows/
│       └─ link-insertion.yml   // GitHub Actions ワークフロー定義ファイル
├─ data/
│   └─ linkMapping.json         // キーワードと URL のマッピングデータ
├─ scripts/
│   └─ insert_links.py          // 内部リンク挿入ロジックを実装するスクリプト（Python例）
└─ README.md
```

## 主な実装手順

### 1. 要件定義
- **自動リンク挿入ロジック**  
  キーワードとリンク先 URL のマッピングを元に、投稿本文中に自動でリンクを挿入する処理を設計します。  
  ※重複挿入防止、リンク挿入回数の制限などのルールも検討します。

- **WordPress 連携**  
  投稿本文の取得・更新には WP REST API（または WP-CLI＋SSH）を利用し、認証情報は GitHub Secrets で管理します。

- **自動化の仕組み**  
  GitHub Actions を用いて、任意のトリガー（例：手動実行、スケジュール実行、プッシュ時）でスクリプトを実行します。

### 2. リポジトリ構築とフォルダ作成
上記のフォルダ構成に沿って、GitHub リポジトリを作成してください。

### 3. スクリプト実装例

#### 3-1. 設定ファイルの読み込み
```python
import json

def load_link_mapping(path='data/linkMapping.json'):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
```
※ JSON ファイルを読み込み、 `{"キーワード": "URL", ...}` の形式でマッピングデータを取得します。

#### 3-2. 投稿データの取得
```python
import requests

def get_post_content(post_id, wp_url, wp_username, wp_password):
    response = requests.get(
        f"{wp_url}/wp-json/wp/v2/posts/{post_id}",
        auth=(wp_username, wp_password)
    )
    data = response.json()
    return data.get('content', {}).get('rendered', '')
```
※ WP REST API を利用して、対象投稿の本文 (HTML) を取得します。

#### 3-3. テキストのパース & リンク挿入
```python
import re

def insert_links_to_content(content, link_mapping, max_links_per_post=3):
    links_added = 0
    for keyword, url in link_mapping.items():
        if links_added >= max_links_per_post:
            break
        pattern = rf'(?<!<a[^>]*>)(?P<kw>{re.escape(keyword)})(?![^<]*<\/a>)'
        def replacement(match):
            nonlocal links_added
            if links_added < max_links_per_post:
                links_added += 1
                return f'<a href="{url}">{match.group("kw")}</a>'
            else:
                return match.group("kw")
        content = re.sub(pattern, replacement, content, count=1)
    return content
```
※ キーワードに対して、既にリンクが存在しない箇所にリンクを挿入する処理を実装します。

#### 3-4. 投稿内容の更新
```python
def update_post_content(post_id, new_content, wp_url, wp_username, wp_password):
    payload = {
        'content': new_content
    }
    response = requests.post(
        f"{wp_url}/wp-json/wp/v2/posts/{post_id}",
        json=payload,
        auth=(wp_username, wp_password)
    )
    return response.status_code, response.text
```
※ 更新後の本文を WP REST API 経由で WordPress に反映します。

#### 3-5. メイン実行関数の例
```python
def main():
    # リンクマッピングの読み込み
    link_mapping = load_link_mapping('data/linkMapping.json')
    
    # 対象投稿IDのリスト（例として固定のIDリスト）
    post_ids = [1, 2, 3]
    
    # WordPress 接続情報（GitHub Actions の Secrets で管理）
    wp_url = "https://example.com"
    wp_username = "myuser"
    wp_password = "mypassword"
    
    for pid in post_ids:
        original_content = get_post_content(pid, wp_url, wp_username, wp_password)
        updated_content = insert_links_to_content(original_content, link_mapping)
        status, res_text = update_post_content(pid, updated_content, wp_url, wp_username, wp_password)
        print(f"Updated post {pid}: status={status}")
```

### 4. GitHub Actions の設定例
以下は、`.github/workflows/link-insertion.yml` の設定例です。

```yaml
name: Internal Link Insertion

on:
  workflow_dispatch:   # 手動実行
  schedule:
    - cron: '0 3 * * *'   # 毎日午前3時に実行する例

jobs:
  link-insertion-job:
    runs-on: ubuntu-latest

    steps:
      - name: Check out the repository
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: pip install requests

      - name: Run link insertion script
        env:
          WP_URL: ${{ secrets.WP_URL }}
          WP_USERNAME: ${{ secrets.WP_USERNAME }}
          WP_PASSWORD: ${{ secrets.WP_PASSWORD }}
        run: |
          python scripts/insert_links.py
```
※ GitHub Secrets にて WP_URL、WP_USERNAME、WP_PASSWORD を設定し、セキュアな環境で実行します。

## テスト・検証フェーズ
1. **ステージング環境での検証**  
   テスト用の WordPress 環境で、リンク挿入の挙動を確認します。

2. **少数記事での動作チェック**  
   限定的な記事に対して実行し、意図しない改変がないか検証します。

3. **特殊ケースのテスト**  
   ・既にリンクが設定済みのキーワード  
   ・同一キーワードが複数存在する場合  
   ・複雑な HTML タグの中での処理など

## 運用と拡張
- **キーワード・URL リストの更新**  
  `data/linkMapping.json` を更新し、Git プッシュすることで即座に反映可能です。

- **リンク挿入ロジックの改善**  
  挿入頻度やマッチングルールの調整、部分一致・完全一致の切り替え等、運用状況に応じて拡張できます。

- **リンク切れチェックやレポート生成**  
  挿入結果のログ取得や、リンク先の 404 チェックなどを追加実装することで、運用の精度を高められます。

## 免責事項
本プロジェクトは、内部リンク自動挿入の一例として提供しています。実際の運用にあたっては、十分なテストと検証を行ってください。

## ライセンス
本プロジェクトは [MIT License](LICENSE) の下で公開されています。
