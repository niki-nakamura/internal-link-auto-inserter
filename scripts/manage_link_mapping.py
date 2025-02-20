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

# GitHub上でのファイルパス
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
        # articles.json はリスト想定、linkMapping/linkUsage はdict想定
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

    # Base64エンコードしてPUT
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
    """
    WordPressサイトのREST APIを用いて投稿を取得する。
    - base_url: WP REST APIのエンドポイント（例: "https://good-apps.jp/media/wp-json/wp/v2/posts"）
    - per_page: 1回に取得する記事数
    - max_pages: ページングの最大試行回数 (制限 or 異常ループ防止用)
    戻り値: postsのリスト（各要素はdict）
    """
    all_posts = []
    page = 1
    while True:
        params = {
            "per_page": per_page,
            "page": page
        }
        res = requests.get(base_url, params=params)
        if res.status_code != 200:
            st.warning(f"記事取得でエラーが発生しました: HTTP {res.status_code}")
            break

        posts = res.json()
        if not isinstance(posts, list) or len(posts) == 0:
            # データが空 or 配列じゃない場合は終了
            break

        all_posts.extend(posts)

        # ページング制御: X-WP-TotalPagesをチェックし、page < total_pages なら続行
        total_pages = res.headers.get("X-WP-TotalPages")
        if total_pages:
            if page >= int(total_pages):
                # 最終ページに達した
                break
        else:
            # total_pages不明だが、取得結果が増えなくなったら終了
            if len(posts) < per_page:
                break

        page += 1
        if page > max_pages:
            st.warning(f"最大ページ数 {max_pages} に達したため中断")
            break

    return all_posts

def extract_column_articles(posts):
    """
    全投稿一覧の中から、URLに `'/media/column/'` を含む記事だけ抽出し、
    `[{"id": int, "title": str, "url": str}, ...]` のリストを返す。
    """
    article_list = []
    for p in posts:
        link = p.get("link", "")
        # WordPressのレスポンスでタイトルは p["title"]["rendered"] に入ることが多い
        # IDは p["id"]
        # column URL判定: "https://good-apps.jp/media/column/" を含むかどうか
        if "/media/column/" in link:
            article_list.append({
                "id": str(p["id"]),  # linkUsage.jsonとの整合性を取りやすいようstr化
                "title": p["title"]["rendered"],
                "url": link
            })
    return article_list


# ===================================
# UI: リンクマッピング管理
# ===================================
def link_mapping_management():
    st.subheader("リンクマッピング管理 (linkMapping.json)")
    link_mapping = load_json(LINK_MAPPING_JSON_PATH)

    if not link_mapping:
        st.info("まだリンクマッピングがありません。フォームから追加してください。")

    # 既存表示
    for kw, url in list(link_mapping.items()):
        col1, col2, col3 = st.columns([3, 5, 1])
        new_kw = col1.text_input("キーワード", value=kw, key=f"kw_{kw}").strip()
        new_url = col2.text_input("URL", value=url, key=f"url_{kw}").strip()

        # 削除ボタン
        if col3.button("削除", key=f"delete_{kw}"):
            del link_mapping[kw]
            save_json_locally(link_mapping, LINK_MAPPING_JSON_PATH)
            st.success(f"削除しました: {kw}")
            st.experimental_rerun()

        # キー変更 or URL変更を反映
        if new_kw != kw:
            del link_mapping[kw]
            link_mapping[new_kw] = new_url
        elif new_url != url:
            link_mapping[kw] = new_url

    st.write("---")
    st.write("### 新規キーワード追加")
    input_kw = st.text_input("新しいキーワード").strip()
    input_url = st.text_input("新しいURL").strip()
    if st.button("追加 (キーワード→URL)"):
        if input_kw and input_url:
            link_mapping[input_kw] = input_url
            save_json_locally(link_mapping, LINK_MAPPING_JSON_PATH)
            st.success(f"追加しました: {input_kw} => {input_url}")
            st.experimental_rerun()
        else:
            st.warning("キーワードとURLの両方を入力してください。")

    # GitHubコミット
    if st.button("保存をGitHubへ (linkMapping.json)"):
        save_json_locally(link_mapping, LINK_MAPPING_JSON_PATH)
        st.success("ローカルファイル(linkMapping.json)更新完了")

        mapping_json_str = json.dumps(link_mapping, ensure_ascii=False, indent=2)
        commit_to_github(mapping_json_str, LINK_MAPPING_FILE_PATH, "Update linkMapping.json from Streamlit")


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

    # GitHubコミット
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

            # 既存データとのマージロジックなどは任意で拡張可
            # 今回は上書き保存
            articles_data = column_posts
            save_json_locally(articles_data, ARTICLES_JSON_PATH)
            st.success(f"articles.json に {len(articles_data)} 件のデータを保存しました。")
            st.experimental_rerun()

    if st.button("articles.json をGitHubへコミット"):
        art_str = json.dumps(articles_data, ensure_ascii=False, indent=2)
        commit_to_github(art_str, ARTICLES_FILE_PATH, "Update articles.json from WP REST API")


# ===================================
# UI: 記事別リンク管理
#   記事ごとに「どのキーワードを挿入するか？」をチェックボックスで設定
#   linkUsage.json に反映
# ===================================
def article_based_link_management():
    st.subheader("記事別リンク管理")

    # データ読み込み
    link_mapping = load_json(LINK_MAPPING_JSON_PATH)  # {kw: url}
    link_usage = load_json(LINK_USAGE_JSON_PATH)      # {kw: {"url":..., "articles_used_in":{...}}}
    articles_data = load_json(ARTICLES_JSON_PATH)     # [{"id":"...", "title":"...", "url":"..."}]

    if not articles_data:
        st.warning("articles.json が空です。先に[WordPress記事一覧管理]タブで記事を取得してください。")
        return

    # 記事選択用のセレクトボックス
    # 表示は 「ID | タイトル」形式
    article_disp_list = [f"{a['id']} | {a['title']}" for a in articles_data]
    selected_item = st.selectbox("記事を選択", article_disp_list)
    selected_index = article_disp_list.index(selected_item)
    selected_article = articles_data[selected_index]
    selected_article_id = selected_article["id"]

    st.markdown(f"**選択中の記事:** ID={selected_article_id}, タイトル={selected_article['title']}")
    st.write("---")

    if not link_mapping:
        st.warning("linkMapping.json が空です。先に[リンクマッピング管理]タブでキーワードを追加してください。")
        return

    changes_made = False

    # キーワードごとにチェックボックスを設置
    for kw, url in link_mapping.items():
        # linkUsage に未登録の場合は初期化
        if kw not in link_usage:
            link_usage[kw] = {
                "url": url,
                "articles_used_in": {}
            }
        usage_info = link_usage[kw]
        articles_used_in = usage_info.setdefault("articles_used_in", {})

        # 現在の挿入回数 (0なら未挿入)
        current_count = articles_used_in.get(selected_article_id, 0)
        is_checked = (current_count > 0)

        new_checked = st.checkbox(f"【{kw}】にリンクを挿入", value=is_checked)
        if new_checked != is_checked:
            changes_made = True
            if new_checked:
                # ONになった → 初期値1回としてセット
                articles_used_in[selected_article_id] = 1
            else:
                # OFFになった → 削除
                if selected_article_id in articles_used_in:
                    del articles_used_in[selected_article_id]

    if changes_made:
        st.warning("変更がありました。下記ボタンで保存してください。")

    if st.button("保存 (この記事のリンクON/OFF設定)"):
        # 保存
        save_json_locally(link_usage, LINK_USAGE_JSON_PATH)
        st.success("linkUsage.json を更新しました。")

        # コミットするかどうか
        if st.checkbox("linkUsage.jsonをGitHubへコミットする"):
            usage_str = json.dumps(link_usage, ensure_ascii=False, indent=2)
            commit_to_github(usage_str, LINK_USAGE_FILE_PATH, f"Update linkUsage.json for article {selected_article_id}")


# ===================================
# メインアプリ
# ===================================
def main():
    st.title("内部リンク管理ツール")

    # 4つのタブに分割
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
