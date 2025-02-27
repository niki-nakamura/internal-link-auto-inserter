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

def remove_links_from_content(content, off_list):
    """
    OFF対象(kw, url)のリストに基づいて、「URLが一致するaタグをアンリンク化」する。
    
    <a href="{url}">任意のテキスト</a> を その「任意テキスト」のみに戻す。

    ショートコードは insert_links_to_content() と同様に退避→復元。
    
    off_list: [ (kw1, url1), (kw2, url2), ... ] (kwはデバッグ用)
    """
    shortcode_pattern = r'(\[.*?\])'
    shortcodes = []

    def shortcode_replacer(m):
        shortcodes.append(m.group(0))
        return f"__SHORTCODE_{len(shortcodes)-1}__"

    # ショートコードを一時退避
    content = re.sub(shortcode_pattern, shortcode_replacer, content)

    # OFFリンク削除: URL一致ベース
    for (kw, url) in off_list:
        # 例: <a href="URL">...</a> → ... (テキストのみ)
        #    [^>]* でhref以外の属性があってもマッチさせる
        #    (.*?) はリンクテキストをキャプチャ
        pattern = rf'<a[^>]*href\s*=\s*"{re.escape(url)}"[^>]*>(.*?)</a>'

        before = content
        content, num_replaced = re.subn(pattern, r'\1', content, flags=re.IGNORECASE|re.DOTALL)
        if num_replaced > 0:
            print(f"[DEBUG] Removed {num_replaced} link(s) for URL={url} (kw='{kw}')")

    # ショートコード復元
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
       OFF → remove_links_from_content()  (URL一致で削除)
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

    # 全キーワード一覧
    all_keywords = list(link_usage.keys())

    # 記事IDごとに:
    #   ON用  -> { kw: url, ... }
    #   OFF用 -> [(kw, url), (kw2, url2), ...]
    article_to_on = {}
    article_to_off = {}

    # 1) ON用マッピングを組み立てる (articles_used_inに含まれる記事)
    for kw in all_keywords:
        usage_info = link_usage[kw]
        link_url   = usage_info.get("url", "")
        used_in    = usage_info.get("articles_used_in", {})

        for art_id in used_in.keys():
            article_to_on.setdefault(art_id, {})
            article_to_on[art_id][kw] = link_url

    # 2) OFF用リストを組み立てる (逆に含まれていない記事)
    all_article_ids = [a["id"] for a in articles]

    for kw in all_keywords:
        usage_info = link_usage[kw]
        link_url   = usage_info.get("url", "")
        used_in    = usage_info.get("articles_used_in", {})

        for art_id in all_article_ids:
            if art_id not in used_in:
                # OFF対象 (kw, url)
                article_to_off.setdefault(art_id, [])
                article_to_off[art_id].append((kw, link_url))

    # 3) 記事ごとに「OFF→ON」の順で実行
    for art in articles:
        art_id = art["id"]
        post_id = int(art_id)
        art_title = art.get("title", "(不明)")

        raw_content = get_post_raw_content(post_id, wp_url, wp_username, wp_password)
        if not raw_content:
            print(f"[WARN] Article {art_id} ({art_title}) -> skip, no content.")
            continue

        off_list = article_to_off.get(art_id, [])
        on_map   = article_to_on.get(art_id, {})

        # (A) OFFリンク削除 (URLが一致する<a>タグをアンリンク)
        temp_content = remove_links_from_content(raw_content, off_list)

        # (B) ONリンク挿入
        updated_content = insert_links_to_content(temp_content, on_map, max_links_per_post=3)

        # 変化があればWP更新
        if updated_content != raw_content:
            print(f"[INFO] Article {art_id} ({art_title}) -> content changed, updating WP...")
            status, resp_text = update_post_content(post_id, updated_content, wp_url, wp_username, wp_password)
            print(f"  -> update_post_content status={status}")
        else:
            print(f"[INFO] Article {art_id} ({art_title}) -> no changes")

if __name__ == "__main__":
    main()
