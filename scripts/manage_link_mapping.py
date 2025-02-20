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
    """
    GitHubのContents APIを使ってJSONファイルを更新する。
    st.secrets["secrets"]["GITHUB_TOKEN"] にPAT(Contents Write権限必須)を設定しておく。
    """
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


# ===================================
# WordPressから記事を取得する処理
# ===================================
def fetch_all_wp_posts(base_url: str, per_page=50, max_pages=50):
    all_posts = []
    page = 1
    while True:
        params = {"per_page": per_page, "page": page}
        res = requests.get(base_url, params=params)
        if res.status_code != 200:
            st.warning(f"記事取得でエラーが発生しました: HTTP {res.status_code}")
            break

        posts = res.json()
        if not isinstance(posts, list) or len(posts) == 0:
            break

        all_posts.extend(posts)

        total_pages = res.headers.get("X-WP-TotalPages")
        if total_pages:
            if page >= int(total_pages):
                break
        else:
            if len(posts) < per_page:
                break

        page += 1
        if page > max_pages:
            st.warning(f"最大ページ数 {max_pages} に達したため中断")
            break

    return all_posts

def extract_column_articles(posts):
    """
    全投稿の中から '/media/column/' が含まれているURLだけ抽出して返す。
    """
    article_list = []
    for p in posts:
        link = p.get("link", "")
        if "/media/column/" in link:
            article_list.append({
                "id": str(p["id"]),  # linkUsage.jsonとの整合性を取りやすいようstr化
                "title": p["title"]["rendered"],
                "url": link
            })
    return article_list


# ===================================
# カテゴリー構造をフラット化するヘルパー関数
# ===================================
def flatten_link_mapping(nested_map: dict) -> dict:
    """
    例:
      {
         "ゲーム": {
             "暇つぶしゲーム": "URL1",
             "カードゲーム": "URL2"
         },
         "交通": {
             "タクシー": "URL3"
         }
      }
    ⇒
      {
         "暇つぶしゲーム": "URL1",
         "カードゲーム": "URL2",
         "タクシー": "URL3"
      }
    """
    flat_map = {}
    for category, kw_dict in nested_map.items():
        flat_map.update(kw_dict)
    return flat_map


# ===================================
# UI: リンクマッピング管理 (カテゴリー対応)
# ===================================
def link_mapping_management():
    st.subheader("リンクマッピング管理 (linkMapping.json)")

    link_mapping_data = load_json(LINK_MAPPING_JSON_PATH)

    # 旧形式(フラット)を「Uncategorized」に移行する処理などは省略 or 必要に応じて追加
    if link_mapping_data and not all(isinstance(v, dict) for v in link_mapping_data.values()):
        st.warning("旧来のフラットな linkMapping.json を検出したため、'Uncategorized' に移行しました。")
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
                new_category_name = col_cat1.text_input(
                    "カテゴリー名を変更",
                    value=category_name,
                    key=f"cat_{category_name}"
                ).strip()

                if col_cat2.button("削除", key=f"delete_cat_{category_name}"):
                    del link_mapping_data[category_name]
                    save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                    st.success(f"削除しました: カテゴリー {category_name}")
                    st.info("ページを再読み込みすると反映されます。")
                    return

                # カテゴリー名変更
                if new_category_name and new_category_name != category_name:
                    if new_category_name in link_mapping_data:
                        st.error(f"カテゴリー名 '{new_category_name}' は既に存在します。")
                    else:
                        link_mapping_data[new_category_name] = cat_data
                        del link_mapping_data[category_name]
                        category_name = new_category_name

                # キーワード一覧
                for kw, url in list(cat_data.items()):
                    c1, c2, c3 = st.columns([3, 5, 1])
                    new_kw = c1.text_input("キーワード", value=kw, key=f"kw_{category_name}_{kw}").strip()
                    new_url = c2.text_input("URL", value=url, key=f"url_{category_name}_{kw}").strip()

                    if c3.button("削除", key=f"del_{category_name}_{kw}"):
                        del cat_data[kw]
                        save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                        st.success(f"削除しました: キーワード {kw} in カテゴリー {category_name}")
                        st.info("ページを再読み込みすると反映されます。")
                        return

                    # キー変更 or URL変更
                    if new_kw != kw:
                        if new_kw in cat_data:
                            st.error(f"既に存在するキーワード '{new_kw}' に上書きできません。")
                        else:
                            del cat_data[kw]
                            cat_data[new_kw] = new_url
                    elif new_url != url:
                        cat_data[kw] = new_url

                st.write("---")
                # 新規キーワード追加
                st.write(f"### 新規キーワード追加 (カテゴリー:{category_name})")
                add_kw = st.text_input(f"新しいキーワード ({category_name})", key=f"add_kw_{category_name}").strip()
                add_url = st.text_input(f"新しいURL ({category_name})", key=f"add_url_{category_name}").strip()
                if st.button(f"追加 (キーワード→URL) to {category_name}", key=f"btn_add_{category_name}"):
                    if add_kw and add_url:
                        if add_kw in cat_data:
                            st.warning(f"既に同じキーワードが存在します: {add_kw}")
                        else:
                            cat_data[add_kw] = add_url
                            save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                            st.success(f"追加しました: [{category_name}] {add_kw} => {add_url}")
                            st.info("ページを再読み込みすると反映されます。")
                            return
                    else:
                        st.warning("キーワードとURLの両方を入力してください。")

    st.write("---")
    # 新規カテゴリー追加
    st.write("### 新規カテゴリー追加")
    new_cat_name = st.text_input("カテゴリー名（例: '交通・移動'）").strip()
    if st.button("カテゴリーを追加"):
        if new_cat_name:
            if new_cat_name in link_mapping_data:
                st.warning(f"既に同名カテゴリーが存在します: {new_cat_name}")
            else:
                link_mapping_data[new_cat_name] = {}
                save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                st.success(f"新規カテゴリーを追加しました: {new_cat_name}")
                st.info("ページを再読み込みすると反映されます。")
                return
        else:
            st.warning("カテゴリー名を入力してください。")

    # GitHubコミット
    if st.button("保存（追加したら必ず押す!）"):
        save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
        st.success("ローカルファイル(linkMapping.json)更新完了")
        mapping_json_str = json.dumps(link_mapping_data, ensure_ascii=False, indent=2)
        commit_to_github(mapping_json_str, LINK_MAPPING_FILE_PATH,
                         "Update linkMapping.json (with categories) from Streamlit")


# ===================================
# UI: リンク使用状況の確認
# ===================================
def link_usage_view():
    st.subheader("リンク使用状況 (linkUsage.json)")
    link_usage = load_json(LINK_USAGE_JSON_PATH)
    if not link_usage:
        st.info("まだ使用状況が記録されていません。")
        return

    for kw, usage_info in link_usage.items():
        st.markdown(f"**キーワード:** {kw}")
        usage_url = usage_info.get("url", "")
        st.write(f"- 登録URL: {usage_url}")

        articles_dict = usage_info.get("articles_used_in", {})
        if articles_dict:
            st.write(f"- 使用記事数: {len(articles_dict)}")
            total_inserts = sum(articles_dict.values())
            st.write(f"- 合計挿入回数: {total_inserts}")
            with st.expander("使用内訳を表示"):
                for article_id, count in articles_dict.items():
                    st.write(f"  - 記事ID: {article_id} → {count}回 挿入")
        else:
            st.write("- まだ使用記録がありません。")

    if st.button("使用状況をGitHubへコミット"):
        usage_str = json.dumps(link_usage, ensure_ascii=False, indent=2)
        commit_to_github(usage_str, LINK_USAGE_FILE_PATH, "Update linkUsage.json from Streamlit")


# ===================================
# UI: WordPress記事一覧管理
# ===================================
def articles_management():
    st.subheader("WordPress 記事一覧管理 (articles.json)")
    articles_data = load_json(ARTICLES_JSON_PATH)

    st.write(f"現在の登録件数: {len(articles_data)}")
    if articles_data:
        with st.expander("登録済み記事リストを表示"):
            for art in articles_data:
                st.markdown(f"- **ID**: {art['id']} | **Title**: {art['title']} | **URL**: {art['url']}")

    st.write("---")
    st.write("### WordPress REST APIから記事を取得")
    base_api_url = st.text_input("WP REST APIエンドポイントURL", value="https://good-apps.jp/media/wp-json/wp/v2/posts")

    if st.button("記事を取得 (REST API)"):
        with st.spinner("記事を取得中..."):
            all_posts = fetch_all_wp_posts(base_api_url, per_page=50, max_pages=50)
            column_posts = extract_column_articles(all_posts)
            st.info(f"API取得: {len(all_posts)}件中、'/media/column/' を含む投稿 {len(column_posts)}件")

            articles_data = column_posts
            save_json_locally(articles_data, ARTICLES_JSON_PATH)
            st.success(f"articles.json に {len(articles_data)} 件のデータを保存しました。")
            # バージョンによっては experimental_rerun() が使えないことがあるのでコメントアウト
            # st.experimental_rerun()

    if st.button("articles.json をGitHubへコミット"):
        art_str = json.dumps(articles_data, ensure_ascii=False, indent=2)
        commit_to_github(art_str, ARTICLES_FILE_PATH, "Update articles.json from WP REST API")


# ===================================
# UI: 記事別リンク管理
#    → カテゴリー構造はフラット化して一括管理
#    → プルダウン + 検索フォームの追加
# ===================================
def article_based_link_management():
    st.subheader("記事別リンク管理")

    # データ読み込み
    nested_link_mapping = load_json(LINK_MAPPING_JSON_PATH)  # {category: {kw: url}}
    link_mapping_flat = flatten_link_mapping(nested_link_mapping)
    link_usage = load_json(LINK_USAGE_JSON_PATH)
    articles_data = load_json(ARTICLES_JSON_PATH)

    if not articles_data:
        st.warning("articles.json が空です。先に[WordPress記事一覧管理]タブで記事を取得してください。")
        return

    # ★ 検索フォームを追加
    search_term = st.text_input("記事タイトル検索", value="", help="一部一致でフィルタします")
    if search_term.strip():
        # 検索文字が入力されている場合は、タイトルにマッチする記事のみ表示
        filtered_articles = [
            a for a in articles_data
            if search_term.lower() in a["title"].lower()
        ]
    else:
        filtered_articles = articles_data

    if not filtered_articles:
        st.warning("検索に一致する記事がありません。")
        return

    # 記事を選択用のプルダウン
    article_disp_list = [f"{a['id']} | {a['title']}" for a in filtered_articles]
    selected_item = st.selectbox("記事を選択", article_disp_list)
    selected_index = article_disp_list.index(selected_item)
    selected_article = filtered_articles[selected_index]
    selected_article_id = selected_article["id"]

    st.markdown(f"**選択中の記事:** ID={selected_article_id}, タイトル={selected_article['title']}")
    st.write("---")

    if not link_mapping_flat:
        st.warning("linkMapping.json が空です。先に[リンクマッピング管理]タブでキーワードを追加してください。")
        return

    changes_made = False

    # キーワードごとにチェックボックスを設置
    for kw, url in link_mapping_flat.items():
        if kw not in link_usage:
            link_usage[kw] = {
                "url": url,
                "articles_used_in": {}
            }
        usage_info = link_usage[kw]
        articles_used_in = usage_info.setdefault("articles_used_in", {})

        current_count = articles_used_in.get(selected_article_id, 0)
        is_checked = (current_count > 0)

        new_checked = st.checkbox(f"「{kw}」にリンクを挿入", value=is_checked)
        if new_checked != is_checked:
            changes_made = True
            if new_checked:
                articles_used_in[selected_article_id] = 1
            else:
                articles_used_in.pop(selected_article_id, None)

    if changes_made:
        st.warning("変更がありました。下記ボタンで保存してください。")

    if st.button("保存 (この記事のリンクON/OFF設定)"):
        save_json_locally(link_usage, LINK_USAGE_JSON_PATH)
        st.success("linkUsage.json を更新しました。")

        if st.checkbox("linkUsage.jsonをGitHubへコミットする"):
            usage_str = json.dumps(link_usage, ensure_ascii=False, indent=2)
            commit_to_github(usage_str, LINK_USAGE_FILE_PATH,
                             f"Update linkUsage.json for article {selected_article_id}")


# ===================================
# メインアプリ
# ===================================
def main():
    st.title("内部リンク管理ツール")

    tabs = st.tabs([
        "リンクマッピング管理",
        "リンク使用状況の確認",
        "WordPress記事一覧管理",
        "記事別リンク管理"
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
