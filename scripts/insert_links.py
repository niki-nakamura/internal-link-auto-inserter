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

def insert_link_once(content: str, link_mapping: dict, article_url: str) -> str:
    """
    記事本文中で最初に登場したキーワード1つだけをリンク化する。
    以下の場合はリンク化しない:
      - link_mapping にあるURL が article_url と同じ (A = B の場合)
      - 既に <a> タグ内にあるテキスト
    """
    original_content = content

    # --- ショートコードを一時退避 ---
    shortcode_pattern = r"(\[.*?\])"
    shortcodes = []
    def shortcode_replacer(m):
        shortcodes.append(m.group(0))
        return f"__SHORTCODE_{len(shortcodes)-1}__"
    content = re.sub(shortcode_pattern, shortcode_replacer, content)

    # --- <a> タグ部分を一時退避 ---
    #    （既存リンクは置換しないため、検索から除外しておく）
    anchor_pattern = r"(<a[^>]*>.*?</a>)"
    anchors = []
    def anchor_replacer(m):
        anchors.append(m.group(0))
        return f"__ANCHOR_{len(anchors)-1}__"
    content = re.sub(anchor_pattern, anchor_replacer, content, flags=re.IGNORECASE|re.DOTALL)

    # ここから「最も上に出現するキーワード」を探し、見つかったら1回だけリンク化する
    # link_mapping: { "キーワード": "URL", ... }
    # まず全文を走査して最初に登場するキーワードを特定
    first_match_index = None
    first_match_kw = None
    first_match_url = None

    for i in range(len(content)):
        # この時点でショートコードや既存リンクは除外済み（プレースホルダになっている）ので、
        # テキストをそのまま検索すればOK
        for kw, url in link_mapping.items():
            # A=B の場合はスキップ
            if url == article_url:
                continue
            # そこから先が kw かどうか
            if content[i:i+len(kw)] == kw:
                first_match_index = i
                first_match_kw = kw
                first_match_url = url
                break
        if first_match_kw is not None:
            break

    if first_match_kw is not None:
        # キーワードをリンクに置き換える
        # 先頭～キーワード部分 + <a> タグ + 末尾 を組み合わせる
        before = content[:first_match_index]
        matched = content[first_match_index:first_match_index+len(first_match_kw)]
        after = content[first_match_index+len(first_match_kw):]
        new_matched = f'<a href="{first_match_url}">{matched}</a>'
        content = before + new_matched + after

    # --- 一時退避した <a> タグを元に戻す ---
    def anchor_restorer(m):
        idx = int(m.group(1))
        return anchors[idx]
    content = re.sub(r"__ANCHOR_(\d+)__", anchor_restorer, content)

    # --- ショートコードを元に戻す ---
    def shortcode_restorer(m):
        idx = int(m.group(1))
        return shortcodes[idx]
    content = re.sub(r"__SHORTCODE_(\d+)__", shortcode_restorer, content)

    # 変更が無ければそのまま返す
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

    # 3) 全記事をループし、該当URLだけ処理
    for article in articles_data:
        post_id = article["id"]
        # ここでは記事のURLを仮に article["link"] として取得する例
        article_link = article.get("link", "")

        raw_content = get_post_raw_content(post_id, wp_url, wp_username, wp_password)
        if not raw_content:
            print(f"[WARN] No content for post {post_id} ({article.get('title','')})")
            continue

        updated_content = insert_link_once(raw_content, flat_map, article_link)

        if updated_content != raw_content:
            print(f"[INFO] Updating post {post_id} ({article.get('title','')})...")
            status, _ = update_post_content(post_id, updated_content, wp_url, wp_username, wp_password)
            print(f"    -> status={status}")
        else:
            print(f"[INFO] No changes for post {post_id} ({article.get('title','')})")

if __name__ == "__main__":
    main()
