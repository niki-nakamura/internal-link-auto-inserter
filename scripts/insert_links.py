#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import requests
import re
import base64

LINK_USAGE_JSON = "data/linkUsage.json"
ARTICLES_JSON   = "data/articles.json"

def get_auth_headers(username, password):
    token = base64.b64encode(f"{username}:{password}".encode()).decode('utf-8')
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def get_post_raw_content(post_id, wp_url, wp_username, wp_password):
    headers = get_auth_headers(wp_username, wp_password)
    resp = requests.get(
        f"{wp_url}/wp-json/wp/v2/posts/{post_id}?context=edit",
        headers=headers
    )
    print(f"get_post_raw_content(post_id={post_id}): status={resp.status_code}")
    if resp.status_code != 200:
        return ""
    data = resp.json()
    return data.get("content", {}).get("raw", "")

def insert_links_to_content(content, link_mapping, max_links_per_post=3):
    """
    link_mapping: { "キーワード": "URL", ... }
    すでにリンクのある箇所は無視。
    ショートコードなど一部を除外したい例をコメントで記載。
    """
    links_added = 0
    shortcode_pattern = r'(\[.*?\])'
    shortcodes = []

    def shortcode_replacer(m):
        shortcodes.append(m.group(0))
        return f"__SHORTCODE_{len(shortcodes)-1}__"

    content = re.sub(shortcode_pattern, shortcode_replacer, content)

    for kw, url in link_mapping.items():
        if links_added >= max_links_per_post:
            break
        pattern = rf'(<a[^>]*>.*?</a>|{re.escape(kw)})'
        def replacement(m):
            nonlocal links_added
            text = m.group(0)
            if text.lower().startswith("<a"):
                return text
            if links_added < max_links_per_post:
                links_added += 1
                return f'<a href="{url}">{text}</a>'
            else:
                return text

        updated = re.sub(pattern, replacement, content, count=1)
        if updated != content:
            content = updated

    def shortcode_restore(m):
        idx = int(m.group(1).split("_")[-1])
        return shortcodes[idx]
    content = re.sub(r'__SHORTCODE_(\d+)__', shortcode_restore, content)

    return content

def update_post_content(post_id, new_content, wp_url, wp_username, wp_password):
    headers = get_auth_headers(wp_username, wp_password)
    payload = {'content': new_content}
    resp = requests.post(f"{wp_url}/wp-json/wp/v2/posts/{post_id}", json=payload, headers=headers)
    print(f"update_post_content(post_id={post_id}): status={resp.status_code}")
    return resp.status_code, resp.text

def main():
    """
    1) WP_URL, WP_USERNAME, WP_PASSWORD を環境変数から取得
    2) linkUsage.json, articles.json をロード
    3) linkUsage.json の "articles_used_in" が ON の記事IDごとに
       → その記事に必要なキーワードだけまとめて insert_links_to_content
       → WordPress更新
    """
    wp_url = os.environ.get("WP_URL", "")
    wp_username = os.environ.get("WP_USERNAME", "")
    wp_password = os.environ.get("WP_PASSWORD", "")

    if not (wp_url and wp_username and wp_password):
        print("[ERROR] WP_URL, WP_USERNAME, WP_PASSWORD not set. Abort.")
        return

    link_usage = load_json(LINK_USAGE_JSON)
    articles = load_json(ARTICLES_JSON)
    if not link_usage or not articles:
        print("[ERROR] linkUsage.json or articles.json is empty. Abort.")
        return

    # article_to_kws: {記事ID: {キーワード:URL, ...}}
    article_to_kws = {}
    for kw, usage_info in link_usage.items():
        link_url = usage_info.get("url", "")
        for art_id in usage_info.get("articles_used_in", {}).keys():
            if art_id not in article_to_kws:
                article_to_kws[art_id] = {}
            article_to_kws[art_id][kw] = link_url

    # 各記事を更新
    for art_id, kw_map in article_to_kws.items():
        post_id = int(art_id)
        # 記事タイトルを取得（ログ出力用）
        found_article = next((a for a in articles if a["id"] == art_id), None)
        art_title = found_article["title"] if found_article else "(不明)"

        raw_content = get_post_raw_content(post_id, wp_url, wp_username, wp_password)
        if not raw_content:
            print(f"[WARN] Article {art_id}({art_title}) -> skip, no content")
            continue

        updated_content = insert_links_to_content(raw_content, kw_map, max_links_per_post=3)
        if updated_content != raw_content:
            status, resp_txt = update_post_content(post_id, updated_content, wp_url, wp_username, wp_password)
            print(f"Updated post {post_id}({art_title}), status={status}")
        else:
            print(f"No changes for post {post_id}({art_title}).")

if __name__ == "__main__":
    main()
