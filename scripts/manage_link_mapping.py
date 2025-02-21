import streamlit as st
import json
import os
import base64
import requests
import re

# ===================================
# WordPressに投稿を更新する関数群
# ===================================
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

def insert_links_to_content(content, link_mapping, max_links_per_post=3):
    """
    link_mapping: { キーワード: URL, ... }
    """
    links_added = 0
    shortcode_pattern = r'(\[.*?\])'
    shortcodes = []
    def shortcode_replacer(m):
        shortcodes.append(m.group(0))
        return f"__SHORTCODE_{len(shortcodes)-1}__"

    content = re.sub(shortcode_pattern, shortcode_replacer, content)

    for kw, url in link_mapping.items():
        # もし上限以上挿入したくないなら break
        if links_added >= max_links_per_post:
            break
        pattern = rf'(<a[^>]*>.*?</a>|{re.escape(kw)})'
        def replacement(m):
            nonlocal links_added
            text = m.group(0)
            if text.lower().startswith("<a"):
                # 既にリンクがある箇所ならスルー
                return text
            if links_added < max_links_per_post:
                links_added += 1
                return f'<a href="{url}">{text}</a>'
            else:
                return text

        updated = re.sub(pattern, replacement, content, count=1)
        if links_added > 0:
            content = updated

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
    の形をもとに、該当記事の本文を取得→キーワード挿入→更新する
    """
    article_to_kw_map = {}  # {"1234": {"暇つぶしゲームアプリ":"URL", ... }, ...}
    for kw, usage_info in link_usage.items():
        url = usage_info.get("url", "")
        for art_id in usage_info.get("articles_used_in", {}).keys():
            if art_id not in article_to_kw_map:
                article_to_kw_map[art_id] = {}
            article_to_kw_map[art_id][kw] = url

    for art_id, kw_map in article_to_kw_map.items():
        # WPの投稿IDは整数
        post_id = int(art_id)
        found_article = next((a for a in articles_data if a["id"] == art_id), None)
        art_title = found_article["title"] if found_article else "(不明)"

        raw_content = get_post_raw_content(post_id, wp_url, wp_username, wp_password)
        if not raw_content:
            print(f"[WARN] skip article {art_id}({art_title}) - no content fetched.")
            continue

        updated_content = insert_links_to_content(raw_content, kw_map, max_links_per_post=3)
        if updated_content != raw_content:
            status, resp_txt = update_post_content(post_id, updated_content, wp_url, wp_username, wp_password)
            print(f"Updated post {post_id}({art_title}), status={status}")
        else:
            print(f"No changes for post {post_id}({art_title}).")


# ===================================
# ここから manage_link_mapping.py 本体
# ===================================

import streamlit as st
import json
import os
import requests
import re

LINK_MAPPING_JSON_PATH = 'data/linkMapping.json'
LINK_USAGE_JSON_PATH = 'data/linkUsage.json'
ARTICLES_JSON_PATH = 'data/articles.json'

GITHUB_REPO_OWNER = "niki-nakamura"
GITHUB_REPO_NAME = "internal-link-auto-inserter"

LINK_MAPPING_FILE_PATH = "data/linkMapping.json"
LINK_USAGE_FILE_PATH = "data/linkUsage.json"
ARTICLES_FILE_PATH = "data/articles.json"
BRANCH = "main"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                  " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

def load_json(path):
    if not os.path.exists(path):
        if "articles" in path:
            return []
        else:
            return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json_locally(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def commit_to_github(json_str: str, target_file_path: str, commit_message: str):
    try:
        token = st.secrets["secrets"]["GITHUB_TOKEN"]
    except KeyError:
        st.error("[ERROR] GITHUB_TOKEN がStreamlit Secretsに設定されていません。")
        return

    url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{target_file_path}?ref={BRANCH}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    get_res = requests.get(url, headers=headers)
    if get_res.status_code == 200:
        sha = get_res.json().get("sha")
    elif get_res.status_code == 404:
        sha = None
    else:
        st.error(f"[ERROR] Fetching file from GitHub: {get_res.status_code}, {get_res.text}")
        return

    content_b64 = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
    put_data = {
        "message": commit_message,
        "content": content_b64,
        "branch": BRANCH
    }
    if sha:
        put_data["sha"] = sha

    put_res = requests.put(url, headers=headers, json=put_data)
    if put_res.status_code in [200, 201]:
        st.success(f"GitHubへのコミットに成功しました: {target_file_path}")
    else:
        st.error(f"[ERROR] GitHubへのコミットに失敗: {put_res.status_code} / {put_res.text}")

def flatten_link_mapping(nested_map: dict) -> dict:
    flat_map = {}
    for cat, kwdict in nested_map.items():
        flat_map.update(kwdict)
    return flat_map

# ------------------------------------------------
# タブ：記事別リンク管理（手動設定用）
#  -> linkUsage.json更新 ＋ 実際のWP反映
# ------------------------------------------------
def article_based_link_management():
    st.subheader("記事別リンク管理（手動）: 複数記事に一括でリンクON/OFFし、即時WordPress更新")

    # 1) WordPress接続情報 (secrets)
    wp_url = st.secrets.get("WP_URL", "")
    wp_username = st.secrets.get("WP_USERNAME", "")
    wp_password = st.secrets.get("WP_PASSWORD", "")

    # 2) データ読み込み
    nested_link_mapping = load_json(LINK_MAPPING_JSON_PATH)
    link_mapping_flat = flatten_link_mapping(nested_link_mapping)
    link_usage = load_json(LINK_USAGE_JSON_PATH)
    articles_data = load_json(ARTICLES_JSON_PATH)

    if not articles_data:
        st.warning("articles.json が空です。WordPress記事一覧管理タブで取得してください。")
        return
    if not link_mapping_flat:
        st.warning("linkMapping.json が空です。リンクマッピング管理タブでキーワードを追加してください。")
        return

    # 3) 記事検索＋複数選択
    search_term = st.text_input("記事タイトル検索 (一部一致)", key="search_articles_multi").strip()
    if search_term:
        filtered = [a for a in articles_data if search_term.lower() in a["title"].lower()]
    else:
        filtered = articles_data

    if not filtered:
        st.write("該当記事がありません。")
        return

    article_disp_list = [f"{art['id']} | {art['title']}" for art in filtered]
    selected_disp = st.multiselect("記事を複数選択", article_disp_list, key="multi_select_articles")
    selected_articles = []
    for disp in selected_disp:
        art_id_str = disp.split("|")[0].strip()
        found = next((a for a in filtered if a["id"] == art_id_str), None)
        if found:
            selected_articles.append(found)

    if not selected_articles:
        st.info("記事が未選択です。")
        return

    st.write("#### 選択中の記事一覧")
    for art in selected_articles:
        st.write(f"- {art['id']} : {art['title']}")

    st.write("---")
    st.write("### キーワードのリンクON/OFF設定 (複数記事同時)")

    changes_made = False
    for kw, url in link_mapping_flat.items():
        # linkUsageにエントリがない場合初期化
        if kw not in link_usage:
            link_usage[kw] = {"url": url, "articles_used_in": {}}
        usage_info = link_usage[kw]
        used_in = usage_info["articles_used_in"]

        # 選択記事すべてがONかどうか
        all_on = all(art["id"] in used_in for art in selected_articles)

        new_val = st.checkbox(kw, value=all_on, key=f"multi_kw_{kw}")
        if new_val != all_on:
            changes_made = True
            if new_val:
                # ON
                for art in selected_articles:
                    usage_info["articles_used_in"][art["id"]] = 1
            else:
                # OFF
                for art in selected_articles:
                    usage_info["articles_used_in"].pop(art["id"], None)

    if changes_made:
        st.warning("キーワードON/OFFが変更されました。下記ボタンで保存するとWPに反映します。")

    if st.button("保存し、WP更新も実行", key="save_and_run_insert"):
        # 1) linkUsage.json更新
        save_json_locally(link_usage, LINK_USAGE_JSON_PATH)
        st.success("linkUsage.jsonを更新しました。")

        # 2) WordPress投稿を更新
        if not (wp_url and wp_username and wp_password):
            st.error("WP_URL, WP_USERNAME, WP_PASSWORD が設定されていません。")
            return
        # run_insert_linksで実際にWP更新
        run_insert_links(articles_data, link_usage, wp_url, wp_username, wp_password)
        st.success("選択記事に内部リンクを挿入し、WordPress更新が完了しました。")

        # 3) GitHubコミット確認
        if st.checkbox("linkUsage.jsonをGitHubへコミットする", key="do_commit"):
            usage_str = json.dumps(link_usage, ensure_ascii=False, indent=2)
            commit_to_github(usage_str, LINK_USAGE_FILE_PATH, "Update linkUsage.json & WP insertion done")


# ===================================
# 他タブ (リンクマッピング管理、リンク使用状況の確認、WordPress記事一覧管理)
#   ... 省略または既存のコードのまま ...
# ===================================

def main():
    st.title("内部リンク管理ツール")

    tabs = st.tabs([
        "リンクマッピング管理",
        "リンク使用状況の確認",
        "記事別リンク管理（手動）",
        "WordPress記事一覧管理"
    ])

    with tabs[0]:
        # link_mapping_management() ...
        pass
    with tabs[1]:
        # link_usage_view() ...
        pass
    with tabs[2]:
        article_based_link_management()
    with tabs[3]:
        # articles_management() ...
        pass

if __name__ == "__main__":
    main()
