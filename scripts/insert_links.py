
import json

def load_link_mapping(path='data/linkMapping.json'):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

import requests

def get_post_content(post_id, wp_url, wp_username, wp_password):
    """
    WordPress REST API を使い特定の投稿を取得する例
    """
    # Basic認証 or Application Password 等による認証
    response = requests.get(
        f"{wp_url}/wp-json/wp/v2/posts/{post_id}",
        auth=(wp_username, wp_password)
    )
    data = response.json()
    return data.get('content', {}).get('rendered', '')

import re

def insert_links_to_content(content, link_mapping, max_links_per_post=1):
    """
    キーワードにマッチした箇所にリンクを挿入する。
    重複を避けるため、すでに <a>タグ がある箇所は除外。
    max_links_per_post で1記事あたりの挿入リンク数を制限。
    """
    links_added = 0
    
    # 大文字小文字を区別する/しない等、要件に応じて調整
    for keyword, url in link_mapping.items():
        if links_added >= max_links_per_post:
            break

    # 検索して1回だけ置換してみる
    pattern = rf'(?<!<a[^>]*>)(?P<kw>{re.escape(keyword)})(?![^<]*<\/a>)'
    ...
    content_after = re.sub(pattern, replacement, content, count=1)
    
    # もし置換が発生していたら(= links_addedが増えていたら)、そこでループを抜ける
    if links_added > 0:
        break
        
        # すでにリンクがある箇所を避けるため、正規表現で <a> タグを含む部分は対象外にする etc.
        # シンプルな例として、keyword単位で置換 (要検討: 全置換 vs 部分置換)
        pattern = rf'(?<!<a[^>]*>)(?P<kw>{re.escape(keyword)})(?![^<]*<\/a>)'
        
        # 実際には1回だけ置換したら終了するのか、複数回置換するのか要件で変わる
        def replacement(match):
            nonlocal links_added
            if links_added < max_links_per_post:
                links_added += 1
                return f'<a href="{url}">{match.group("kw")}</a>'
            else:
                return match.group("kw")
        
        content = re.sub(pattern, replacement, content, count=1)
    
    return content

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

def main():
    # 1. リンクマッピング読込
    link_mapping = load_link_mapping('data/linkMapping.json')
    
    # 2. 対象の投稿IDリストを取得する(例: 自前管理 or WP APIで一覧取得)
    post_ids = [24823,24862]  # 追加減可能
    
    # 3. WP接続情報 (GitHub ActionsのSecretsで渡す)
    wp_url = "https://example.com"
    wp_username = "myuser"
    wp_password = "mypassword"  # or token
    
    for pid in post_ids:
        # 本文取得
        original_content = get_post_content(pid, wp_url, wp_username, wp_password)
        
        # リンク挿入
        updated_content = insert_links_to_content(original_content, link_mapping)
        
        # 更新APIコール
        status, res_text = update_post_content(pid, updated_content, wp_url, wp_username, wp_password)
        print(f"Updated post {pid}: status={status}")

