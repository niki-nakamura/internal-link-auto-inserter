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

def insert_links_to_content(content, link_mapping, max_links_per_post=3):
    """
    既存の内部リンク挿入ロジック。
    link_mapping: { "キーワード": "URL", ... }
    """
    links_added = 0
    shortcode_pattern = r'(\[.*?\])'
    shortcodes = []

    def shortcode_replacer(m):
        shortcodes.append(m.group(0))
        return f"__SHORTCODE_{len(shortcodes)-1}__"

    # ショートコードを一時退避
    content = re.sub(shortcode_pattern, shortcode_replacer, content)

    # キーワードを本文中で検索し、最初に見つかった箇所だけ<a>に置き換え
    for kw, url in link_mapping.items():
        if links_added >= max_links_per_post:
            break
        # 既にリンクがある箇所はスキップ（<a...>）
        pattern = rf'(<a[^>]*>.*?</a>|{re.escape(kw)})'

        def replacement(m):
            nonlocal links_added
            text = m.group(0)
            # 既にリンクタグの場合はそのまま
            if text.lower().startswith("<a"):
                return text
            # 未リンク箇所をリンク化
            links_added += 1
            return f'<a href="{url}">{text}</a>'

        updated = re.sub(pattern, replacement, content, count=1)
        if updated != content:
            content = updated

    # ショートコードを復元
    def shortcode_restore(m):
        idx = int(m.group(1).split("_")[-1])
        return shortcodes[idx]

    content = re.sub(r'__SHORTCODE_(\d+)__', shortcode_restore, content)
    return content

def remove_links_from_content(content, off_keywords):
    """
    OFFキーワードに該当するリンク(<a>...</a>)を削除（アンリンク）する。
    <a href="...">キーワード</a> → キーワード に戻す簡易実装。
    ショートコードは insert_links_to_content() と同様に退避→復元。
    """
    shortcode_pattern = r'(\[.*?\])'
    shortcodes = []

    def shortcode_replacer(m):
        shortcodes.append(m.group(0))
        return f"__SHORTCODE_{len(shortcodes)-1}__"

    # ショートコードを一時退避
    content = re.sub(shortcode_pattern, shortcode_replacer, content)

    # OFFキーワードを含む <a>タグ をアンリンク化
    for kw in off_keywords:
        escaped_kw = re.escape(kw)
        # 例: <a href="...">飛行機</a> → 飛行機
        pattern = rf'<a[^>]*>({escaped_kw})</a>'
        content = re.sub(pattern, r'\1', content)

    # ショートコードを復元
    def shortcode_restore(m):
        idx = int(m.group(1).split("_")[-1])
        return shortcodes[idx]

    content = re.sub(r'__SHORTCODE_(\d+)__', shortcode_restore, content)
    return content

def main():
    """
    1) 環境変数から WP_URL, WP_USERNAME, WP_PASSWORD を取得
    2) linkUsage.json, articles.json をロード
    3) linkUsage.json で「articles_used_in」にある記事 → ON扱い / 無い記事 → OFF扱い
       OFF → remove_links_from_content()
       ON  → insert_links_to_content()
       の順で更新し、WordPressに保存する
    """
    wp_url = os.environ.get("WP_URL", "")
    wp_username = os.environ.get("WP_USERNAME", "")
    wp_password = os.environ.get("WP_PASSWORD", "")

    if not (wp_url and wp_username and wp_password):
        print("[ERROR] WP_URL, WP_USERNAME, WP_PASSWORD not set in environment. Abort.")
        return

    link_usage = load_json(LINK_USAGE_JSON)
    articles   = load_json(ARTICLES_JSON)
    if not link_usage or not articles:
        print("[ERROR] linkUsage.json or articles.json is empty. Abort.")
        return

    # 全キーワードを列挙
    all_keywords = list(link_usage.keys())

    # 記事IDごとに「ONにしたいキーワード(Map)」「OFFにしたいキーワード(list)」を仕分け
    article_to_on = {}   # { art_id: { kw: url, ... } }
    article_to_off = {}  # { art_id: [kw1, kw2, ...] }

    # 「articles_used_in」に含まれている記事ID → ON
    for kw in all_keywords:
        url = link_usage[kw].get("url", "")
        used_in = link_usage[kw].get("articles_used_in", {})
        for art_id in used_in.keys():
            article_to_on.setdefault(art_id, {})
            article_to_on[art_id][kw] = url

    # すべての記事IDを取得
    all_article_ids = [a["id"] for a in articles]

    # OFF対象: 「全記事IDのうち、articles_used_inに含まれていないもの」
    for kw in all_keywords:
        used_in = link_usage[kw].get("articles_used_in", {})
        for art_id in all_article_ids:
            if art_id not in used_in:
                article_to_off.setdefault(art_id, [])
                article_to_off[art_id].append(kw)

    # 記事ごとに OFF→ON を適用して WordPressに更新
    for art in articles:
        art_id = art["id"]
        post_id = int(art_id)
        art_title = art.get("title", "(不明)")

        raw_content = get_post_raw_content(post_id, wp_url, wp_username, wp_password)
        if not raw_content:
            print(f"[WARN] Article {art_id} ({art_title}) -> skip, no content.")
            continue

        off_kws = article_to_off.get(art_id, [])
        on_map  = article_to_on.get(art_id, {})

        # OFFキーワード削除
        temp_content = remove_links_from_content(raw_content, off_kws)
        # ONキーワード挿入
        updated_content = insert_links_to_content(temp_content, on_map, max_links_per_post=3)

        # 変化があればWP更新
        if updated_content != raw_content:
            status, _ = update_post_content(post_id, updated_content, wp_url, wp_username, wp_password)
            print(f"Updated post {post_id}({art_title}), status={status}")
        else:
            print(f"No changes for post {post_id}({art_title}).")

if __name__ == "__main__":
    main()
