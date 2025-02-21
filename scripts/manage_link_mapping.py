import streamlit as st
import json
import os
import base64
import requests
import re

# 追加: WordPress投稿を更新するための関数たち
def get_auth_headers(username, password):
    token = base64.b64encode(f"{username}:{password}".encode()).decode('utf-8')
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }

def get_post_raw_content(post_id, wp_url, wp_username, wp_password):
    headers = get_auth_headers(wp_username, wp_password)
    resp = requests.get(f"{wp_url}/wp-json/wp/v2/posts/{post_id}?context=edit", headers=headers)
    if resp.status_code != 200:
        print(f"[WARN] get_post_raw_content: status={resp.status_code}, post_id={post_id}")
        return ""
    data = resp.json()
    return data.get("content", {}).get("raw", "")

def insert_links_to_content(content, link_mapping, max_links_per_post=1):
    """
    linkMapping : {キーワード: URL, ...}
    ここでは全キーワードを1つずつ挿入する(上限 max_links_per_post回)という簡易例。
    """
    links_added = 0

    # ショートコード等の除外例(必要に応じて)
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
        if links_added > 0:
            content = updated

    # ショートコードを戻す
    def shortcode_restore(m):
        idx = int(m.group(1).split("_")[-1])
        return shortcodes[idx]
    content = re.sub(r'__SHORTCODE_(\d+)__', shortcode_restore, content)

    return content

def update_post_content(post_id, new_content, wp_url, wp_username, wp_password):
    headers = get_auth_headers(wp_username, wp_password)
    payload = {"content": new_content}
    resp = requests.post(f"{wp_url}/wp-json/wp/v2/posts/{post_id}", json=payload, headers=headers)
    return resp.status_code, resp.text


def run_insert_links(articles_data, link_usage, wp_url, wp_username, wp_password):
    """
    link_usage: 
      { 
        "暇つぶしゲームアプリ": { "url": "...", "articles_used_in": { "1234": 1, "5678": 1 } },
        ...
      }
    の形の情報をもとに、ONになっている記事(articles_used_in)ごとに
    WPの本文を取得→キーワード挿入→更新 を行う。
    """

    # 1) 記事ID → linkMapping の形に再構成する (1記事ごとにどのKWを挿入すべきか)
    article_to_kw = {}  # { "1234": { "暇つぶしゲームアプリ":"URL", ... }, ... }

    for kw, usage_info in link_usage.items():
        link_url = usage_info.get("url", "")
        articles_dict = usage_info.get("articles_used_in", {})
        for art_id in articles_dict.keys():
            if art_id not in article_to_kw:
                article_to_kw[art_id] = {}
            article_to_kw[art_id][kw] = link_url

    # 2) 各記事を回して、本文を更新
    for art_id, kw_map in article_to_kw.items():
        # WP投稿IDは文字列の場合もあるのでintにする
        post_id = int(art_id)
        # articles_data からタイトル等参照(必要なら)
        found = next((a for a in articles_data if a["id"] == art_id), None)
        title = found["title"] if found else "??"

        # まず生の本文を取得
        raw_content = get_post_raw_content(post_id, wp_url, wp_username, wp_password)
        if not raw_content:
            print(f"[WARN] Article {art_id}({title}) content is empty or failed to fetch.")
            continue

        # キーワード→URL マップを insert_links_to_content に渡す
        updated_content = insert_links_to_content(raw_content, kw_map, max_links_per_post=3)
        if updated_content and updated_content != raw_content:
            status, resp_text = update_post_content(post_id, updated_content, wp_url, wp_username, wp_password)
            print(f"Updated post {post_id} => status={status}")
        else:
            print(f"No changes for post {post_id}.")


# -----------------------------------------
# 以降が既存の manage_link_mapping.py などに組み込み
# -----------------------------------------

import streamlit as st
import json
import os

# ...ここに load_json, save_json_locally, commit_to_github, flatten_link_mapping,
# link_mapping_management, link_usage_view, articles_management などがあると想定

def article_based_link_management():
    st.subheader("記事別リンク管理（手動設定用）")
    # WordPress接続情報を secrets から読む想定
    wp_url = st.secrets.get("WP_URL", "")
    wp_username = st.secrets.get("WP_USERNAME", "")
    wp_password = st.secrets.get("WP_PASSWORD", "")

    nested_link_mapping = load_json("data/linkMapping.json")
    link_mapping_flat   = flatten_link_mapping(nested_link_mapping)
    link_usage = load_json("data/linkUsage.json")
    articles_data = load_json("data/articles
