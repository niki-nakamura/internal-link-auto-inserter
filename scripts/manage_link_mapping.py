import streamlit as st
import json
import os
import base64
import requests
import re

# ===================================
# WordPress 更新関連のユーティリティ
# ===================================
def get_auth_headers(username, password):
    token = base64.b64encode(f"{username}:{password}".encode()).decode("utf-8")
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
    既存リンクは上書きせず、max_links_per_post 個まで挿入の例。
    """
    links_added = 0

    # ショートコード等の単純除外例 (必要があれば調整)
    shortcode_pattern = r"(\[.*?\])"
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
            links_added += 1
            return f'<a href="{url}">{text}</a>'

        updated = re.sub(pattern, replacement, content, count=1)
        if updated != content:
            content = updated

    def shortcode_restore(m):
        idx = int(m.group(1).split("_")[-1])
        return shortcodes[idx]

    content = re.sub(r"__SHORTCODE_(\d+)__", shortcode_restore, content)
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
        "キーワードA": {
          "url": "https://...",
          "articles_used_in": {
             "1234": 1, "5678": 1
          }
        },
        ...
      }

    articles_data: [{id: "1234", title:"...", url:"..."}, ...]

    link_usageに基づき、ONになっている記事にリンクを挿入してWP更新。
    """
    article_to_kw_map = {}
    for kw, usage_info in link_usage.items():
        url = usage_info.get("url", "")
        used_in = usage_info.get("articles_used_in", {})
        for art_id_str in used_in.keys():
            if art_id_str not in article_to_kw_map:
                article_to_kw_map[art_id_str] = {}
            article_to_kw_map[art_id_str][kw] = url

    for art_id_str, kw_map in article_to_kw_map.items():
        post_id = int(art_id_str)
        # 記事タイトルのログ出力用
        found_article = next((a for a in articles_data if a["id"] == art_id_str), None)
        title = found_article["title"] if found_article else "??"

        raw_content = get_post_raw_content(post_id, wp_url, wp_username, wp_password)
        if not raw_content:
            print(f"[WARN] No content for {post_id} ({title}), skip.")
            continue

        updated_content = insert_links_to_content(raw_content, kw_map, max_links_per_post=3)
        if updated_content != raw_content:
            status, txt = update_post_content(post_id, updated_content, wp_url, wp_username, wp_password)
            print(f"Updated post {post_id} ({title}), status={status}")
        else:
            print(f"No changes for post {post_id} ({title}).")

# ===================================
# ファイル操作・GitHubコミット関数
# ===================================
LINK_MAPPING_JSON_PATH = "data/linkMapping.json"
LINK_USAGE_JSON_PATH   = "data/linkUsage.json"
ARTICLES_JSON_PATH     = "data/articles.json"

GITHUB_REPO_OWNER = "niki-nakamura"
GITHUB_REPO_NAME  = "internal-link-auto-inserter"

LINK_MAPPING_FILE_PATH = "data/linkMapping.json"
LINK_USAGE_FILE_PATH   = "data/linkUsage.json"
ARTICLES_FILE_PATH     = "data/articles.json"
BRANCH = "main"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                  " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

def load_json(path):
    if not os.path.exists(path):
        # articles.json は [] で初期化、それ以外は {}
        return [] if "articles" in path else {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json_locally(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def commit_to_github(json_str, target_file_path, commit_message):
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

# ===================================
# タブ1: リンクマッピング管理
# ===================================
def link_mapping_management():
    st.subheader("リンクマッピング管理 (linkMapping.json)")

    link_mapping_data = load_json(LINK_MAPPING_JSON_PATH)

    # 旧来フラット形式 → Uncategorized化
    if link_mapping_data and not all(isinstance(v, dict) for v in link_mapping_data.values()):
        st.warning("旧来のフラット linkMapping.json を 'Uncategorized' カテゴリに移行しました。")
        link_mapping_data = {"Uncategorized": link_mapping_data}
        save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)

    if not link_mapping_data:
        link_mapping_data = {}

    # カテゴリ一覧
    st.write("## カテゴリ別キーワード一覧")
    if not link_mapping_data:
        st.info("まだカテゴリーがありません。追加してください。")
    else:
        category_list = sorted(link_mapping_data.keys())
        for category_name in category_list:
            with st.expander(f"カテゴリー: {category_name}", expanded=False):
                cat_data = link_mapping_data[category_name]

                # カテゴリ名の変更 or 削除
                col1, col2 = st.columns([3,1])
                new_cat_name = col1.text_input(
                    f"カテゴリー名変更({category_name})",
                    value=category_name,
                    key=f"catname_{category_name}"
                ).strip()
                if col2.button("削除", key=f"btn_del_cat_{category_name}"):
                    del link_mapping_data[category_name]
                    save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                    st.success(f"カテゴリー '{category_name}' を削除しました。")
                    return

                if new_cat_name and new_cat_name != category_name:
                    if new_cat_name in link_mapping_data:
                        st.error(f"既に同名のカテゴリー '{new_cat_name}' が存在します。")
                    else:
                        link_mapping_data[new_cat_name] = cat_data
                        del link_mapping_data[category_name]
                        category_name = new_cat_name
                        save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                        st.success(f"カテゴリー名を '{new_cat_name}' に変更しました。")
                        return

                # キーワード一覧
                st.write("---")
                st.write(f"### キーワード一覧 (カテゴリ={category_name})")
                for kw, url in list(cat_data.items()):
                    c1, c2, c3 = st.columns([3,5,1])
                    new_kw  = c1.text_input("キーワード", value=kw,
                                            key=f"kw_{category_name}_{kw}").strip()
                    new_url = c2.text_input("URL", value=url,
                                            key=f"url_{category_name}_{kw}").strip()

                    if c3.button("削除", key=f"btn_del_kw_{category_name}_{kw}"):
                        del cat_data[kw]
                        save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                        st.success(f"キーワード '{kw}' を削除しました。")
                        return

                    # 更新
                    if new_kw != kw:
                        if new_kw in cat_data:
                            st.error(f"キーワード '{new_kw}' は既に存在します。")
                        else:
                            del cat_data[kw]
                            cat_data[new_kw] = new_url
                            save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                            st.success(f"キーワード名を '{new_kw}' に変更しました。")
                            return
                    elif new_url != url:
                        cat_data[kw] = new_url
                        save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                        st.success(f"URLを更新しました (キーワード={kw}).")
                        return

                # 新規キーワード追加
                st.write("---")
                st.write(f"### 新規キーワード追加 (カテゴリ={category_name})")
                add_kw  = st.text_input(f"新規キーワード", key=f"addkw_{category_name}").strip()
                add_url = st.text_input(f"新規URL", key=f"addurl_{category_name}").strip()

                if st.button(f"追加→{category_name}", key=f"btn_add_{category_name}"):
                    if add_kw and add_url:
                        if add_kw in cat_data:
                            st.warning(f"'{add_kw}' は既に存在します。")
                        else:
                            cat_data[add_kw] = add_url
                            save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                            st.success(f"追加: {add_kw} => {add_url}")
                            return
                    else:
                        st.warning("キーワード/URLを入力してください。")

    st.write("## 新規カテゴリー追加")
    new_cat = st.text_input("カテゴリー名 (例: ゲーム系など)", key="input_new_category").strip()
    if st.button("新規カテゴリー作成", key="btn_new_cat"):
        if new_cat:
            if new_cat in link_mapping_data:
                st.warning(f"カテゴリー '{new_cat}' は既に存在。")
            else:
                link_mapping_data[new_cat] = {}
                save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                st.success(f"新規カテゴリーを追加しました: {new_cat}")
        else:
            st.warning("カテゴリー名を入力してください。")

    if st.button("linkMapping.json をGitHubへコミット"):
        mapping_str = json.dumps(link_mapping_data, ensure_ascii=False, indent=2)
        commit_to_github(mapping_str, LINK_MAPPING_FILE_PATH, "Update linkMapping.json from Streamlit")


# ===================================
# タブ2: リンク使用状況の確認
# ===================================
def link_usage_view():
    st.subheader("全記事の内部リンク状況一覧 (linkUsage.json)")

    link_usage = load_json(LINK_USAGE_JSON_PATH)
    articles_data = load_json(ARTICLES_JSON_PATH)

    if not link_usage:
        st.info("linkUsage.json が空です。まだリンク挿入のON/OFFが設定されていないかもしれません。")
        return
    if not articles_data:
        st.info("articles.json が空です。WordPress記事一覧管理で取得してください。")
        return

    # 記事別の合計リンク数を算出
    article_usage_summary = {}
    for kw, usage_info in link_usage.items():
        used_in = usage_info.get("articles_used_in", {})
        for art_id, cnt in used_in.items():
            if art_id not in article_usage_summary:
                article_usage_summary[art_id] = {
                    "title": None,
                    "url": None,
                    "total_link_count": 0,
                    "details": {}
                }
            article_usage_summary[art_id]["total_link_count"] += cnt
            article_usage_summary[art_id]["details"].setdefault(kw, 0)
            article_usage_summary[art_id]["details"][kw] += cnt

    # まだ0リンクの記事も追加
    for art in articles_data:
        art_id = art["id"]
        if art_id not in article_usage_summary:
            article_usage_summary[art_id] = {
                "title": art["title"],
                "url": art["url"],
                "total_link_count": 0,
                "details": {}
            }
        else:
            # タイトル/URLの上書き (一応反映)
            article_usage_summary[art_id]["title"] = art["title"]
            article_usage_summary[art_id]["url"]   = art["url"]

    # フィルタ
    st.write("### フィルタ・ソート")
    c1, c2, c3 = st.columns([3,3,2])
    f_article = c1.text_input("記事タイトル検索 (一部一致)", key="usage_art_search").strip()
    f_kw      = c2.text_input("内部リンクキーワード検索 (一部一致)", key="usage_kw_search").strip()
    sort_opt  = c3.selectbox("ソート順", ["多い順","少ない順","記事ID昇順","記事ID降順"], key="usage_sort")

    summary_list = []
    for art_id, info in article_usage_summary.items():
        # タイトル検索
        if f_article:
            if f_article.lower() not in info["title"].lower():
                continue
        # キーワード検索
        if f_kw:
            if not any(f_kw.lower() in kw.lower() for kw in info["details"].keys()):
                continue
        summary_list.append((art_id, info))

    # ソート
    if sort_opt == "多い順":
        summary_list.sort(key=lambda x: x[1]["total_link_count"], reverse=True)
    elif sort_opt == "少ない順":
        summary_list.sort(key=lambda x: x[1]["total_link_count"])
    elif sort_opt == "記事ID昇順":
        summary_list.sort(key=lambda x: int(x[0]))
    else:
        summary_list.sort(key=lambda x: int(x[0]), reverse=True)

    st.write(f"### 該当記事数: {len(summary_list)} 件")
    for art_id, info in summary_list:
        st.markdown(f"**[{info['title']}]({info['url']})** (ID={art_id})")
        if info["total_link_count"] > 0:
            detail_str = ", ".join(f"{k}({c}回)" for k,c in info["details"].items())
            st.write(f"- リンク挿入合計: {info['total_link_count']}, 明細: {detail_str}")
        else:
            st.write("- 内部リンクはありません。")

    if st.button("使用状況をGitHubへコミット"):
        usage_str = json.dumps(link_usage, ensure_ascii=False, indent=2)
        commit_to_github(usage_str, LINK_USAGE_FILE_PATH, "Update linkUsage.json from Streamlit")


# ===================================
# タブ3: 記事別リンク管理（手動）
# ===================================
def article_based_link_management():
    st.subheader("記事別リンク管理（手動）: 複数記事に一括でリンクON/OFF設定 & WP更新")

    # WP接続情報
    wp_url      = st.secrets.get("WP_URL", "")
    wp_username = st.secrets.get("WP_USERNAME", "")
    wp_password = st.secrets.get("WP_PASSWORD", "")

    nested_mapping = load_json(LINK_MAPPING_JSON_PATH)
    link_usage     = load_json(LINK_USAGE_JSON_PATH)
    articles_data  = load_json(ARTICLES_JSON_PATH)

    if not articles_data:
        st.warning("articles.json が空です。WordPress記事一覧管理タブで取得してください。")
        return
    if not nested_mapping:
        st.warning("linkMapping.json が空です。リンクマッピング管理タブで設定してください。")
        return

    link_mapping_flat = flatten_link_mapping(nested_mapping)
    if not link_usage:
        link_usage = {}

    # 1) 記事検索 + 複数選択
    #   => `key=`を付けて、TextInputの重複エラーを回避
    search_term = st.text_input("記事タイトル検索 (一部一致)", "", key="artsearch_manual")
    if search_term.strip():
        filtered_articles = [
            a for a in articles_data if search_term.lower() in a["title"].lower()
        ]
    else:
        filtered_articles = articles_data

    if not filtered_articles:
        st.info("該当記事がありません。")
        return

    # 複数選択
    article_disp_list = [f"{a['id']} | {a['title']}" for a in filtered_articles]
    selected_disp = st.multiselect("対象記事選択", article_disp_list, key="multi_articles_manual")

    selected_articles = []
    for disp in selected_disp:
        art_id_str = disp.split("|")[0].strip()
        found = next((a for a in filtered_articles if a["id"] == art_id_str), None)
        if found:
            selected_articles.append(found)

    if not selected_articles:
        st.info("記事が未選択です。")
        return

    st.write("### 選択中の記事一覧")
    for a in selected_articles:
        st.write(f"- {a['id']} : {a['title']}")

    st.write("---")
    st.write("### キーワードのリンクON/OFF (複数記事同時)")

    # 全キーワードチェック
    changed = False
    for kw, url in link_mapping_flat.items():
        if kw not in link_usage:
            link_usage[kw] = {"url": url, "articles_used_in": {}}
        # urlが更新された場合を同期
        else:
            if link_usage[kw].get("url") != url:
                link_usage[kw]["url"] = url

        used_in = link_usage[kw]["articles_used_in"]
        # 選択された記事すべてがONか？
        all_on = all(art["id"] in used_in for art in selected_articles)

        # checkboxも重複キーのエラーを防ぐために unique key を付ける
        new_val = st.checkbox(
            f"{kw}",
            value=all_on,
            key=f"multi_kw_chk_{kw}"
        )
        if new_val != all_on:
            changed = True
            if new_val:
                # ON
                for art in selected_articles:
                    used_in[art["id"]] = 1
            else:
                # OFF
                for art in selected_articles:
                    used_in.pop(art["id"], None)

    if changed:
        st.warning("キーワードON/OFFが変更されました。下記ボタンで保存・WP更新してください。")

    if st.button("保存 & WordPress更新", key="save_wp_btn"):
        # 1) linkUsage.json 保存
        save_json_locally(link_usage, LINK_USAGE_JSON_PATH)
        st.success("linkUsage.json を更新しました。")

        # 2) WPに反映
        if not (wp_url and wp_username and wp_password):
            st.error("WP_URL / WP_USERNAME / WP_PASSWORD が設定されていません。")
            return
        run_insert_links(articles_data, link_usage, wp_url, wp_username, wp_password)
        st.success("WordPress記事を更新しました (選択記事に内部リンクを挿入)。")

        # 3) GitHubコミット (オプション)
        if st.checkbox("変更した linkUsage.json をGitHubコミットする", key="commit_usage_check"):
            usage_str = json.dumps(link_usage, ensure_ascii=False, indent=2)
            commit_to_github(usage_str, LINK_USAGE_FILE_PATH, "Update linkUsage.json & WP updated")


# ===================================
# タブ4: WordPress記事一覧管理
# ===================================
def articles_management():
    st.subheader("WordPress記事一覧管理 (articles.json)")
    articles_data = load_json(ARTICLES_JSON_PATH)
    st.write(f"現在の登録件数: {len(articles_data)}")

    if articles_data:
        with st.expander("登録済みの記事一覧"):
            for a in articles_data:
                st.write(f"- {a['id']}, {a['title']}, {a['url']}")

    st.write("---")
    base_url = st.text_input("WP REST APIエンドポイントURL", value="https://good-apps.jp/media/wp-json/wp/v2/posts", key="wp_rest_url")
    if st.button("記事を取得 (REST API)", key="wp_rest_fetch"):
        all_posts = []
        page = 1
        per_page = 50
        max_pages = 50

        while True:
            params = {"per_page": per_page, "page": page}
            r = requests.get(base_url, headers=HEADERS, params=params)
            if r.status_code != 200:
                st.warning(f"記事取得失敗: HTTP {r.status_code}")
                break

            data_posts = r.json()
            if not isinstance(data_posts, list) or not data_posts:
                break

            all_posts.extend(data_posts)
            total_pages = r.headers.get("X-WP-TotalPages")
            if total_pages:
                if page >= int(total_pages):
                    break
            else:
                if len(data_posts) < per_page:
                    break
            page += 1
            if page > max_pages:
                st.warning(f"最大ページ {max_pages} まで取得し中断しました。")
                break

        # /media/column/ を含む投稿だけ抽出する例
        column_posts = []
        for p in all_posts:
            link = p.get("link", "")
            if "/media/column/" in link:
                column_posts.append({
                    "id": str(p["id"]),
                    "title": p["title"]["rendered"],
                    "url": link
                })

        st.info(f"取得: {len(all_posts)}件中 '/media/column/'含む {len(column_posts)}件のみ採用")
        articles_data = column_posts
        save_json_locally(articles_data, ARTICLES_JSON_PATH)
        st.success(f"articles.json を {len(articles_data)}件 で更新しました。")

    if st.button("articles.json をGitHubへコミット", key="commit_articles"):
        js = json.dumps(articles_data, ensure_ascii=False, indent=2)
        commit_to_github(js, ARTICLES_FILE_PATH, "Update articles.json from WP REST API")


# ===================================
# メインアプリ (タブ切り替え)
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
        link_mapping_management()

    with tabs[1]:
        link_usage_view()

    with tabs[2]:
        article_based_link_management()

    with tabs[3]:
        articles_management()

if __name__ == "__main__":
    main()
