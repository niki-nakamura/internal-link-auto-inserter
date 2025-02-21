import streamlit as st
import json
import os
import base64
import requests

# ===================================
# 設定類
# ===================================
LINK_MAPPING_JSON_PATH = 'data/linkMapping.json'
LINK_USAGE_JSON_PATH = 'data/linkUsage.json'
ARTICLES_JSON_PATH = 'data/articles.json'  # WordPressから取得した記事を保存する

GITHUB_REPO_OWNER = "niki-nakamura"
GITHUB_REPO_NAME = "internal-link-auto-inserter"

LINK_MAPPING_FILE_PATH = "data/linkMapping.json"
LINK_USAGE_FILE_PATH = "data/linkUsage.json"
ARTICLES_FILE_PATH = "data/articles.json"
BRANCH = "main"

# bot対策用User-Agent
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                  " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

# ===================================
# ユーティリティ関数
# ===================================
def load_json(path: str):
    """JSONファイルを読み込む。存在しなければ空の構造を返す。"""
    if not os.path.exists(path):
        if "articles" in path:
            return []
        else:
            return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json_locally(data, path: str):
    """辞書 or リストをJSONにして上書き保存"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def commit_to_github(json_str: str, target_file_path: str, commit_message: str):
    """GitHubのContents APIを使って data/*.json を更新"""
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
    """
    linkMapping.json が
      { "カテゴリA": {"KW1":"URL1", "KW2":"URL2"},
        "カテゴリB": {"KW3":"URL3"} }
    のようになっている場合をフラット化:
      {"KW1":"URL1", "KW2":"URL2", "KW3":"URL3"}
    """
    flat_map = {}
    for category, kw_dict in nested_map.items():
        flat_map.update(kw_dict)
    return flat_map


# ===================================
# タブ1: リンクマッピング管理
# ===================================
def link_mapping_management():
    st.subheader("リンクマッピング管理 (linkMapping.json)")

    link_mapping_data = load_json(LINK_MAPPING_JSON_PATH)
    if link_mapping_data and not all(isinstance(v, dict) for v in link_mapping_data.values()):
        # 旧フラットを "Uncategorized" に移行
        st.warning("旧来のフラット linkMapping.json を検出、'Uncategorized' として移行しました。")
        link_mapping_data = {"Uncategorized": link_mapping_data}
        save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)

    if not link_mapping_data:
        link_mapping_data = {}

    if not link_mapping_data:
        st.info("まだカテゴリーがありません。フォームから追加してください。")
    else:
        category_list = sorted(link_mapping_data.keys())
        for category_name in category_list:
            with st.expander(f"カテゴリー: {category_name}", expanded=False):
                cat_data = link_mapping_data[category_name]

                col_cat1, col_cat2 = st.columns([3, 1])
                new_cat_name = col_cat1.text_input("カテゴリー名を変更",
                                                   value=category_name,
                                                   key=f"cat_{category_name}").strip()

                if col_cat2.button("削除", key=f"delete_cat_{category_name}"):
                    del link_mapping_data[category_name]
                    save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                    st.success(f"削除しました: カテゴリー {category_name}")
                    st.info("ページ再読み込みで反映されます。")
                    return

                # カテゴリー名変更
                if new_cat_name and new_cat_name != category_name:
                    if new_cat_name in link_mapping_data:
                        st.error(f"カテゴリー名 '{new_cat_name}' は既に存在します。")
                    else:
                        link_mapping_data[new_cat_name] = cat_data
                        del link_mapping_data[category_name]
                        category_name = new_cat_name

                # キーワード一覧
                for kw, url in list(cat_data.items()):
                    c1, c2, c3 = st.columns([3, 5, 1])
                    new_kw  = c1.text_input("キーワード", value=kw, key=f"kw_{category_name}_{kw}").strip()
                    new_url = c2.text_input("URL", value=url, key=f"url_{category_name}_{kw}").strip()

                    if c3.button("削除", key=f"del_{category_name}_{kw}"):
                        del cat_data[kw]
                        save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                        st.success(f"削除しました: '{kw}' (カテゴリー:{category_name})")
                        st.info("ページ再読み込みで反映されます。")
                        return

                    # キー変更 or URL変更
                    if new_kw != kw:
                        if new_kw in cat_data:
                            st.error(f"既に存在するキーワード '{new_kw}' には上書き不可。")
                        else:
                            del cat_data[kw]
                            cat_data[new_kw] = new_url
                    elif new_url != url:
                        cat_data[kw] = new_url

                st.write("---")
                # 新キーワード追加
                st.write(f"### 新規キーワード追加 (カテゴリー:{category_name})")
                add_kw  = st.text_input(f"新しいキーワード ({category_name})",
                                        key=f"add_kw_{category_name}").strip()
                add_url = st.text_input(f"新しいURL ({category_name})",
                                        key=f"add_url_{category_name}").strip()
                if st.button(f"追加 (キーワード→URL) to {category_name}",
                             key=f"btn_add_{category_name}"):
                    if add_kw and add_url:
                        if add_kw in cat_data:
                            st.warning(f"既に同キーワード存在: {add_kw}")
                        else:
                            cat_data[add_kw] = add_url
                            save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                            st.success(f"追加: [{category_name}] {add_kw} => {add_url}")
                            st.info("再読み込みすると反映されます。")
                            return
                    else:
                        st.warning("キーワード & URL両方を入力してください。")

    st.write("---")
    # 新規カテゴリー追加
    st.write("### 新規カテゴリー追加")
    new_cat_name = st.text_input("カテゴリー名（例: '交通・移動'）").strip()
    if st.button("カテゴリーを追加"):
        if new_cat_name:
            if new_cat_name in link_mapping_data:
                st.warning(f"同名カテゴリー '{new_cat_name}' が既に存在します。")
            else:
                link_mapping_data[new_cat_name] = {}
                save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                st.success(f"新規カテゴリーを追加: {new_cat_name}")
                st.info("ページ再読み込みで反映されます。")
                return
        else:
            st.warning("カテゴリー名を入力してください。")

    # GitHubコミット
    if st.button("保存（追加・編集後は必ず押す）"):
        save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
        st.success("linkMapping.jsonを更新しました。")
        mapping_str = json.dumps(link_mapping_data, ensure_ascii=False, indent=2)
        commit_to_github(mapping_str, LINK_MAPPING_FILE_PATH,
                         "Update linkMapping.json (with categories) from Streamlit")


# ===================================
# ★★ タブ2: リンク使用状況の確認 ★★
#  -> 「全XXX件の記事の内部リンク状況一覧」だけを表示
#  -> すぐ下に検索(記事タイトル/内部リンクキーワード) & ソートボックスを用意
# ===================================
def link_usage_view():
    st.subheader("全記事の内部リンク状況一覧")

    link_usage = load_json(LINK_USAGE_JSON_PATH)
    articles_data = load_json(ARTICLES_JSON_PATH)

    if not link_usage:
        st.info("linkUsage.json が空です。")
        return
    if not articles_data:
        st.info("articles.json が空です。")
        return

    # 1) 記事ごとの usage summary を構築
    article_usage_summary = {}
    # linkUsage.json => {kw: {url:..., articles_used_in:{art_id:count}}}
    for kw, usage_info in link_usage.items():
        for art_id, cnt in usage_info.get("articles_used_in", {}).items():
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

    # articles.json でタイトル/URL補完。
    # 内部リンク0のものもここでエントリを作る
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
            # 既に辞書があってもtitle/urlを入れる
            article_usage_summary[art_id]["title"] = art["title"]
            article_usage_summary[art_id]["url"]   = art["url"]

    # 2) 検索&ソートフォーム
    st.write("#### フィルタ・ソート設定")
    col_search1, col_search2, col_sort = st.columns([3,3,2])

    # (a) 記事タイトル検索
    with col_search1:
        article_search = st.text_input("記事タイトル検索").strip()

    # (b) 内部リンクキーワード検索
    with col_search2:
        kw_search = st.text_input("内部リンクキーワード検索").strip()

    # (c) ソート順
    with col_sort:
        sort_option = st.selectbox("ソート順", ["多い順", "少ない順", "記事ID昇順", "記事ID降順"])

    # 3) リスト化してフィルター & ソート
    summary_list = []
    for art_id, info in article_usage_summary.items():
        # 記事タイトルフィルタ
        title_ok = (article_search.lower() in info["title"].lower()) if article_search else True
        # キーワード検索 -> details のキーに kw_search が含まれればOK
        if kw_search:
            # "details" = { '暇つぶしゲームアプリ': 1, ...}
            kw_found = any(kw_search.lower() in k.lower()
                           for k in info["details"].keys())
        else:
            kw_found = True

        if title_ok and kw_found:
            summary_list.append( (art_id, info) )

    # ソート
    if sort_option == "多い順":
        summary_list.sort(key=lambda x: x[1]["total_link_count"], reverse=True)
    elif sort_option == "少ない順":
        summary_list.sort(key=lambda x: x[1]["total_link_count"])
    elif sort_option == "記事ID昇順":
        summary_list.sort(key=lambda x: int(x[0]))
    else:  # "記事ID降順"
        summary_list.sort(key=lambda x: int(x[0]), reverse=True)

    # 4) 表示
    st.write(f"#### 全 {len(summary_list)} 件の記事の内部リンク状況一覧 (絞り込み後)")

    for art_id, info in summary_list:
        art_title = info["title"]
        art_url   = info["url"]
        st.markdown(f"**[{art_title}]({art_url})**  (ID={art_id})")

        if info["total_link_count"] > 0:
            # details: {キーワード: count}
            details_str = ", ".join(
                f"{kw}({cnt}回)" for kw, cnt in info["details"].items()
            )
            st.write(f"- リンク挿入合計: {info['total_link_count']} ( {details_str} )")
        else:
            st.write("- 内部リンクはありません。")

    # GitHubコミットボタン (必要に応じて残す)
    if st.button("使用状況をGitHubへコミット"):
        usage_str = json.dumps(link_usage, ensure_ascii=False, indent=2)
        commit_to_github(usage_str, LINK_USAGE_FILE_PATH,
                         "Update linkUsage.json from Streamlit")


# ===================================
# タブ3: WordPress記事一覧管理
# ===================================
def articles_management():
    st.subheader("WordPress 記事一覧管理 (articles.json)")
    articles_data = load_json(ARTICLES_JSON_PATH)
    st.write(f"現在の登録件数: {len(articles_data)}")

    # 表示(折りたたみ)
    if articles_data:
        with st.expander("登録済み記事リストを表示"):
            for art in articles_data:
                st.markdown(f"- **ID**: {art['id']} | **Title**: {art['title']} | **URL**: {art['url']}")

    st.write("---")
    st.write("### WordPress REST APIから記事を取得 (手動)")

    base_api_url = st.text_input("WP REST APIエンドポイントURL",
                                 value="https://good-apps.jp/media/wp-json/wp/v2/posts")
    if st.button("記事を取得 (REST API)"):
        all_posts = []
        page = 1
        per_page = 50
        max_pages = 50

        while True:
            params = {"per_page": per_page, "page": page}
            resp = requests.get(base_api_url, headers=HEADERS, params=params)
            if resp.status_code != 200:
                st.warning(f"記事取得でHTTPエラー: {resp.status_code}")
                break

            data_posts = resp.json()
            if not isinstance(data_posts, list) or len(data_posts) == 0:
                break

            all_posts.extend(data_posts)
            total_pages = resp.headers.get("X-WP-TotalPages")
            if total_pages:
                if page >= int(total_pages):
                    break
            else:
                if len(data_posts) < per_page:
                    break

            page += 1
            if page > max_pages:
                st.warning(f"最大ページ数 {max_pages} に達したため中断")
                break

        # '/media/column/' を含む投稿のみ抽出
        column_posts = []
        for p in all_posts:
            link = p.get("link", "")
            if "/media/column/" in link:
                column_posts.append({
                    "id": str(p["id"]),
                    "title": p["title"]["rendered"],
                    "url": link
                })

        st.info(f"API取得: {len(all_posts)}件中、'/media/column/' 含む投稿 {len(column_posts)}件")
        articles_data = column_posts
        save_json_locally(articles_data, ARTICLES_JSON_PATH)
        st.success(f"{len(articles_data)}件を articles.json に上書き保存。")

    if st.button("articles.json をGitHubへコミット"):
        art_str = json.dumps(articles_data, ensure_ascii=False, indent=2)
        commit_to_github(art_str, ARTICLES_FILE_PATH,
                         "Update articles.json from WP REST API")


# ===================================
# タブ4: 記事別リンク管理（手動設定用）
# ===================================
def article_based_link_management():
    st.subheader("記事別リンク管理（手動設定用）")

    nested_link_mapping = load_json(LINK_MAPPING_JSON_PATH)
    link_mapping_flat   = flatten_link_mapping(nested_link_mapping)
    link_usage = load_json(LINK_USAGE_JSON_PATH)
    articles_data = load_json(ARTICLES_JSON_PATH)

    if not articles_data:
        st.warning("articles.json が空です。先に[WordPress記事一覧管理]タブで取得してください。")
        return

    # 検索
    search_term = st.text_input("記事タイトル検索 (一部一致)", "")
    if search_term.strip():
        filtered = [
            a for a in articles_data
            if search_term.lower() in a["title"].lower()
        ]
    else:
        filtered = articles_data

    if not filtered:
        st.warning("該当記事がありません。")
        return

    # 選択
    article_disp_list = [f"{a['id']} | {a['title']}" for a in filtered]
    selected_item = st.selectbox("記事を選択", article_disp_list)
    selected_index = article_disp_list.index(selected_item)
    selected_article = filtered[selected_index]
    selected_id = selected_article["id"]

    st.markdown(f"**選択中の記事:** ID={selected_id}, タイトル={selected_article['title']}")

    if not link_mapping_flat:
        st.warning("linkMapping.json が空です。")
        return

    changes_made = False
    for kw, url in link_mapping_flat.items():
        if kw not in link_usage:
            link_usage[kw] = {
                "url": url,
                "articles_used_in": {}
            }
        usage_info = link_usage[kw]
        articles_used_in = usage_info.setdefault("articles_used_in", {})

        current_count = articles_used_in.get(selected_id, 0)
        is_checked = (current_count > 0)

        new_checked = st.checkbox(f"{kw}", value=is_checked)
        if new_checked != is_checked:
            changes_made = True
            if new_checked:
                articles_used_in[selected_id] = 1
            else:
                articles_used_in.pop(selected_id, None)

    if changes_made:
        st.warning("リンク挿入設定に変更があります。下記ボタンで保存してください。")

    if st.button("保存 (この記事のON/OFF設定)"):
        save_json_locally(link_usage, LINK_USAGE_JSON_PATH)
        st.success("linkUsage.json を更新しました。")
        if st.checkbox("linkUsage.jsonをGitHubへコミット"):
            usage_str = json.dumps(link_usage, ensure_ascii=False, indent=2)
            commit_to_github(usage_str, LINK_USAGE_FILE_PATH,
                             f"Update linkUsage.json (Article ID={selected_id})")


# ===================================
# メインアプリ
# ===================================
def main():
    st.title("内部リンク管理ツール")

    tabs = st.tabs([
        "リンクマッピング管理",
        "リンク使用状況の確認",  # <= ここに「全記事の内部リンク状況一覧」だけ
        "WordPress記事一覧管理",
        "記事別リンク管理（手動）"
    ])

    with tabs[0]:
        link_mapping_management()

    with tabs[1]:
        link_usage_view()

    with tabs[2]:
        articles_management()

    with tabs[3]:
        article_based_link_management()


if __name__ == "__main__":
    main()
