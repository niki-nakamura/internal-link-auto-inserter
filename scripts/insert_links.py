#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import requests
import re
import base64

LINK_MAPPING_JSON = "data/linkMapping.json"
ARTICLES_JSON     = "data/articles.json"

def get_auth_headers(username, password):
    token = base64.b64encode(f"{username}:{password}".encode()).decode('utf-8')
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def flatten_link_mapping(nested_map: dict) -> dict:
    """カテゴリ分けされた linkMapping.json を平坦化する"""
    flat_map = {}
    for category_dict in nested_map.values():
        # category_dict は {"キーワード": "URL", ...} のdict
        flat_map.update(category_dict)
    return flat_map

def get_post_raw_content(post_id, wp_url, wp_username, wp_password):
    headers = get_auth_headers(wp_username, wp_password)
    url = f"{wp_url}/wp-json/wp/v2/posts/{post_id}?context=edit"
    resp = requests.get(url, headers=headers)
    print(f"get_post_raw_content(post_id={post_id}): status={resp.status_code}")
    if resp.status_code != 200:
        return ""
    data = resp.json()
    return data.get("content", {}).get("raw", "")

def update_post_content(post_id, new_content, wp_url, wp_username, wp_password):
    headers = get_auth_headers(wp_username, wp_password)
    payload = {"content": new_content}
    resp = requests.post(f"{wp_url}/wp-json/wp/v2/posts/{post_id}", json=payload, headers=headers)
    print(f"update_post_content(post_id={post_id}): status={resp.status_code}")
    return resp.status_code, resp.text

def insert_links_to_content(content, link_mapping, max_links_per_post=3):
    """
    link_mapping: { "キーワード": "URL", ... }
    キーワードが文章中に現れたら最初の1回だけアンカータグ化（既にリンクがある箇所はスキップ）。
    """
    links_added = 0

    # ショートコード等を一時退避
    shortcode_pattern = r"(\[.*?\])"
    shortcodes = []

    def shortcode_replacer(m):
        shortcodes.append(m.group(0))
        return f"__SHORTCODE_{len(shortcodes)-1}__"

    content = re.sub(shortcode_pattern, shortcode_replacer, content)

    # キーワードごとに検索してリンク化
    for kw, url in link_mapping.items():
        if links_added >= max_links_per_post:
            break

        # 既存の <a> タグで囲まれた部分はスキップする
        pattern = rf'(<a[^>]*>.*?</a>|{re.escape(kw)})'

        def replacement(m):
            nonlocal links_added
            text = m.group(0)
            # 既に<a>タグなら変更なし
            if text.lower().startswith("<a"):
                return text
            # 初回だけ置換
            links_added += 1
            return f'<a href="{url}">{text}</a>'

        updated = re.sub(pattern, replacement, content, count=1)
        if updated != content:
            content = updated

    # ショートコードを復元
    def shortcode_restore(m):
        idx = int(m.group(1).split("_")[-1])
        return shortcodes[idx]

    content = re.sub(r"__SHORTCODE_(\d+)__", shortcode_restore, content)
    return content

def main():
    # 環境変数でWPのURL・認証情報を取得
    wp_url = os.environ.get("WP_URL", "")
    wp_username = os.environ.get("WP_USERNAME", "")
    wp_password = os.environ.get("WP_PASSWORD", "")

    if not (wp_url and wp_username and wp_password):
        print("[ERROR] Missing WP credentials")
        return

    # 1) linkMapping, articles をロード
    mapping_data = load_json(LINK_MAPPING_JSON)
    articles_data = load_json(ARTICLES_JSON)
    if not articles_data:
        print("[ERROR] articles.json is empty or missing")
        return

    # 2) linkMapping をフラット化
    flat_map = flatten_link_mapping(mapping_data)

    # 3) 全記事をループし、キーワードがあれば置換 → 更新
    for article in articles_data:
        post_id = article["id"]
        raw_content = get_post_raw_content(post_id, wp_url, wp_username, wp_password)
        if not raw_content:
            print(f"[WARN] No content for post {post_id} ({article.get('title','')})")
            continue

        updated_content = insert_links_to_content(raw_content, flat_map, max_links_per_post=3)
        if updated_content != raw_content:
            print(f"[INFO] Updating post {post_id} ({article.get('title','')})...")
            status, _ = update_post_content(post_id, updated_content, wp_url, wp_username, wp_password)
            print(f"    -> status={status}")
        else:
            print(f"[INFO] No changes for post {post_id} ({article.get('title','')})")

if __name__ == "__main__":
    main()
