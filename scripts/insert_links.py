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

def update_post_content(post_id, new_content, wp_url, wp_username, wp_password):
    headers = get_auth_headers(wp_username, wp_password)
    payload = {'content': new_content}
    resp = requests.post(f"{wp_url}/wp-json/wp/v2/posts/{post_id}", json=payload, headers=headers)
    print(f"update_post_content(post_id={post_id}): status={resp.status_code}")
    return resp.status_code, resp.text

def insert_links_to_content(content, link_mapping, article_url, max_links_per_post=3):
    """
    link_mapping: { \"キーワード\": \"URL\", ... }
    """
    
    # セルフリンク禁止:
    # 「link_mapping」の中で、この「article_url」と一致するURLを除外する。
    filtered_mapping = {}
    for kw, url in link_mapping.items():
        # もしこのURLが記事URL（article_url）と同じなら、この記事では挿入しない
        if url == article_url:
            continue
        filtered_mapping[kw] = url

    # 以降の処理は、"自分自身へのリンク"を含まないフィルタ済みマッピングを使う
    link_mapping = filtered_mapping
    
    links_added = 0
    shortcode_pattern = r'(\\[.*?\\])'
    shortcodes = []

    def shortcode_replacer(m):
        shortcodes.append(m.group(0))
        return f"__SHORTCODE_{len(shortcodes)-1}__"

    # ショートコード退避
    content = re.sub(shortcode_pattern, shortcode_replacer, content)

    # リンク挿入
    for kw, url in link_mapping.items():
        if links_added >= max_links_per_post:
            break
        pattern = rf'(<a[^>]*>.*?</a>|{re.escape(kw)})'

        def replacement(m):
            nonlocal links_added
            text = m.group(0)
            # 既にリンク
            if text.lower().startswith("<a"):
                return text
            links_added += 1
            return f'<a href=\"{url}\">{text}</a>'

        updated = re.sub(pattern, replacement, content, count=1)
        if updated != content:
            content = updated

    def shortcode_restore(m):
        idx = int(m.group(1).split("_")[-1])
        return shortcodes[idx]

    content = re.sub(r'__SHORTCODE_(\\d+)__', shortcode_restore, content)
    return content

def remove_links_by_url(content, url):
    """
    URLが一致する <a href=\"url\">...</a> をアンリンク化: <a ...>テキスト</a> → テキスト
    """
    # \"(.*?)\" でリンクテキストをキャプチャ
    pattern = rf'<a[^>]*href\\s*=\\s*\"{re.escape(url)}\"[^>]*>(.*?)</a>'
    before = content
    content, num_replaced = re.subn(pattern, r'\\1', content, flags=re.IGNORECASE|re.DOTALL)
    if num_replaced > 0:
        print(f"[DEBUG] Removed {num_replaced} link(s) for URL={url}")
    return content

def remove_off_links(content, off_list):
    """
    off_list: List of (kw, url)
    → URLベースでリンクを削除
    """
    shortcode_pattern = r'(\\[.*?\\])'
    shortcodes = []

    def shortcode_replacer(m):
        shortcodes.append(m.group(0))
        return f"__SHORTCODE_{len(shortcodes)-1}__"

    content = re.sub(shortcode_pattern, shortcode_replacer, content)

    for (kw, url) in off_list:
        content = remove_links_by_url(content, url)

    def shortcode_restore(m):
        idx = int(m.group(1).split("_")[-1])
        return shortcodes[idx]

    content = re.sub(r'__SHORTCODE_(\\d+)__', shortcode_restore, content)
    return content

def main():
    wp_url = os.environ.get("WP_URL", "")
    wp_username = os.environ.get("WP_USERNAME", "")
    wp_password = os.environ.get("WP_PASSWORD", "")

    if not (wp_url and wp_username and wp_password):
        print("[ERROR] Missing WP credentials")
        return

    link_usage = load_json(LINK_USAGE_JSON)
    articles = load_json(ARTICLES_JSON)
    if not link_usage or not articles:
        print(\"[ERROR] linkUsage.json or articles.json is empty\")
        return

    # ONマッピング & OFFリスト
    article_to_on = {}
    article_to_off = {}

    all_keywords = list(link_usage.keys())
    all_article_ids = [a[\"id\"] for a in articles]

    # ONをまとめる
    for kw in all_keywords:
        usage_info = link_usage[kw]
        link_url = usage_info.get(\"url\", \"\")
        used_in = usage_info.get(\"articles_used_in\", {})
        for art_id in used_in.keys():
            article_to_on.setdefault(art_id, {})
            article_to_on[art_id][kw] = link_url

    # OFFをまとめる
    for kw in all_keywords:
        usage_info = link_usage[kw]
        link_url = usage_info.get(\"url\", \"\")
        used_in = usage_info.get(\"articles_used_in\", {})
        for art_id in all_article_ids:
            if art_id not in used_in:
                article_to_off.setdefault(art_id, [])
                article_to_off[art_id].append((kw, link_url))

    # 処理 (OFF→ON)
    for art in articles:
        art_id = art[\"id\"]
        post_id = int(art_id)
        art_title = art.get(\"title\", \"(不明)\")
        raw_content = get_post_raw_content(post_id, wp_url, wp_username, wp_password)
        if not raw_content:
            print(f\"[WARN] No content for post {art_id} ({art_title})\")
            continue

        off_list = article_to_off.get(art_id, [])
        on_map = article_to_on.get(art_id, {})

        # OFF
        temp_content = remove_off_links(raw_content, off_list)
        # ON
        article_url = art["url"]  # この記事自身のURL
        updated_content = insert_links_to_content(temp_content, on_map, article_url, max_links_per_post=3)

        if updated_content != raw_content:
            print(f\"[INFO] Updating post {post_id} ({art_title})...\")
            status, txt = update_post_content(post_id, updated_content, wp_url, wp_username, wp_password)
            print(f\"    -> status={status}\")
        else:
            print(f\"[INFO] No changes for post {post_id} ({art_title})\")

if __name__ == \"__main__\":
    main()
