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
ARTICLES_JSON_PATH = 'data/articles.json'  # WordPressから取得した記事を保存

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
    if not os.path.exists(path):
        if "articles" in path:
            return []
        else:
            return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json_locally(data, path: str):
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
    """ 
    カテゴリ階層つきの linkMapping.json をフラット化 
    { "カテゴリ": {"KW1":"URL1",...}, ...} -> {"KW1":"URL1",...}
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
        st.warning("旧来のフラットlinkMapping.json を検出→'Uncategorized'へ移行しました。")
        link_mapping_data = {"Uncategorized": link_mapping_data}
        save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)

    if not link_mapping_data:
        link_mapping_data = {}

    if not link_mapping_data:
        st.info("まだカテゴリーがありません。下記フォームで追加してください。")
    else:
        category_list = sorted(link_mapping_data.keys())
        for category_name in category_list:
            with st.expander(f"カテゴリー: {category_name}", expanded=False):
                cat_data = link_mapping_data[category_name]

                col1, col2 = st.columns([3,1])
                new_cat_name = col1.text_input("カテゴリー名を変更", value=category_name,
                                               key=f"cat_{category_name}").strip()

                if col2.button("削除", key=f"delete_cat_{category_name}"):
                    del link_mapping_data[category_name]
                    save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                    st.success(f"カテゴリー {category_name} を削除しました。")
                    return

                # カテゴリー名変更
                if new_cat_name and new_cat_name != category_name:
                    if new_cat_name in link_mapping_data:
                        st.error(f"既に同名のカテゴリー '{new_cat_name}' が存在します。")
                    else:
                        link_mapping_data[new_cat_name] = cat_data
                        del link_mapping_data[category_name]
                        category_name = new_cat_name

                # キーワード一覧
                for kw, url in list(cat_data.items()):
                    c1, c2, c3 = st.columns([3,5,1])
                    new_kw  = c1.text_input("キーワード", value=kw,
                                            key=f"kw_{category_name}_{kw}").strip()
                    new_url = c2.text_input("URL", value=url,
                                            key=f"url_{category_name}_{kw}").strip()

                    if c3.button("削除", key=f"del_{category_name}_{kw}"):
                        del cat_data[kw]
                        save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                        st.success(f"キーワード '{kw}' 削除済み。")
                        return

                    # キー or URL変更
                    if new_kw != kw:
                        if new_kw in cat_data:
                            st.error(f"既に同じキーワード '{new_kw}' が存在します。")
                        else:
                            del cat_data[kw]
                            cat_data[new_kw] = new_url
                    elif new_url != url:
                        cat_data[kw] = new_url

                st.write("------")
                st.write(f"### 新規キーワード追加 (カテゴリー:{category_name})")
                add_kw  = st.text_input(f"新規キーワード: {category_name}",
                                        key=f"addkw_{category_name}").strip()
                add_url = st.text_input(f"新規URL: {category_name}",
                                        key=f"addurl_{category_name}").strip()
                if st.button(f"追加: {category_name}", key=f"btn_addkw_{category_name}"):
                    if add_kw and add_url:
                        if add_kw in cat_data:
                            st.warning(f"キーワード '{add_kw}' は既に存在します。")
                        else:
                            cat_data[add_kw] = add_url
                            save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                            st.success(f"[{category_name}] {add_kw} => {add_url} を追加しました。")
                            return
                    else:
                        st.warning("キーワード・URLを両方入力してください。")

    st.write("-----")
    st.write("### 新規カテゴリー追加")
    new_cat = st.text_input("カテゴリー名（例：ゲーム系）").strip()
    if st.button("カテゴリー追加"):
        if new_cat:
            if new_cat in link_mapping_data:
                st.warning(f"同名カテゴリー '{new_cat}' は既に存在します。")
            else:
                link_mapping_data[new_cat] = {}
                save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
                st.success(f"カテゴリー '{new_cat}' を追加しました。")
                return
        else:
            st.warning("カテゴリー名が空です。")

    if st.button("保存（追加・編集後は必ず押す）"):
        save_json_locally(link_mapping_data, LINK_MAPPING_JSON_PATH)
        st.success("linkMapping.json を更新しました。")
        mapping_str = json.dumps(link_mapping_data, ensure_ascii=False, indent=2)
        commit_to_github(mapping_str, LINK_MAPPING_FILE_PATH,
                         "Update linkMapping.json from Streamlit")


# ===================================
# タブ2: リンク使用状況の確認
# ===================================
def link_usage_view():
    st.subheader("全記事の内部リンク状況一覧")

    link_usage = load_json(LINK_USAGE_JSON_PATH)
    articles_data = load_json(ARTICLES_JSON_PATH)

    if not link_usage:
        st.info("linkUsage.json が空です。GitHub Actionsでの自動検出後にご利用ください。")
        return
    if not articles_data:
        st.info("articles.json が空です。WordPress記事一覧管理タブで取得してください。")
        return

    # 1) 記事別サマリーを作成
    article_usage_summary = {}
    for kw, usage_info in link_usage.items():
        for art_id, c in usage_info.get("articles_used_in", {}).items():
            if art_id not in article_usage_summary:
                article_usage_summary[art_id] = {
                    "title": None,
                    "url": None,
                    "total_link_count": 0,
                    "details": {}
                }
            article_usage_summary[art_id]["total_link_count"] += c
            article_usage_summary[art_id]["details"].setdefault(kw, 0)
            article_usage_summary[art_id]["details"][kw] += c

    # 全記事に対してtitle/urlを補完 (内部リンク0でもエントリあり)
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
            article_usage_summary[art_id]["title"] = art["title"]
            article_usage_summary[art_id]["url"]   = art["url"]

    # フィルタ・ソートUI
    st.write("#### フィルタ・ソート設定")
    col1, col2, col3 = st.columns([3,3,2])

    with col1:
        article_search = st.text_input("記事タイトル検索 (一部一致)").strip()
    with col2:
        kw_search = st.text_input("内部リンクキーワード検索 (一部一致)").strip()
    with col3:
        sort_option = st.selectbox("ソート順",
                                   ["多い順", "少ない順", "記事ID昇順", "記事ID降順"])

    # フィルタ
    summary_list = []
    for art_id, info in article_usage_summary.items():
        # (1) 記事タイトルフィルタ
        if article_search:
            if article_search.lower() not in info["title"].lower():
                continue
        # (2) キーワード検索 (details.keys)
        if kw_search:
            kw_found = any(kw_search.lower() in k.lower()
                           for k in info["details"].keys())
            if not kw_found:
                continue

        summary_list.append((art_id, info))

    # ソート
    if sort_option == "多い順":
        summary_list.sort(key=lambda x: x[1]["total_link_count"], reverse=True)
    elif sort_option == "少ない順":
        summary_list.sort(key=lambda x: x[1]["total_link_count"])
    elif sort_option == "記事ID昇順":
        summary_list.sort(key=lambda x: int(x[0]))
    else:  # "記事ID降順"
        summary_list.sort(key=lambda x: int(x[0]), reverse=True)

    st.write(f"#### 全 {len(summary_list)} 件の記事の内部リンク状況一覧 (絞り込み後)")

    for art_id, info in summary_list:
        art_title = info["title"]
        art_url   = info["url"]
        st.markdown(f"**[{art_title}]({art_url})** (ID={art_id})")
        if info["total_link_count"] > 0:
            details_str = ", ".join(
                f"{kw}({cnt}回)" for kw, cnt in info["details"].items()
            )
            st.write(f"- リンク挿入合計: {info['total_link_count']}  ( {details_str} )")
        else:
            st.write("- 内部リンクはありません。")

    # 任意：linkUsage.json コミットボタン
    if st.button("使用状況をGitHubへコミット"):
        usage_str = json.dumps(link_usage, ensure_ascii=False, indent=2)
        commit_to_github(usage_str, LINK_USAGE_FILE_PATH,
                         "Update linkUsage.json from Streamlit")


# ===================================
# タブ3: 記事別リンク管理（手動設定用）
#    （複数記事を同時に選択できるように改良）
# ===================================
def article_based_link_management():
    st.subheader("記事別リンク管理（手動設定用）")

    """
    [仕組み解説]
      - Streamlit上で「複数の記事」をマルチセレクトし、
      - それらの記事に対して「キーワードのリンクON/OFFチェックボックス」をまとめて設定。
      - 保存ボタンを押すと linkUsage.json に反映される。
        具体的には:
          link_usage[<キーワード>]['articles_used_in'][<article_id>] = 1 
          ... をセット、または削除する。
    """

    nested_link_mapping = load_json(LINK_MAPPING_JSON_PATH)
    link_mapping_flat   = flatten_link_mapping(nested_link_mapping)
    link_usage = load_json(LINK_USAGE_JSON_PATH)
    articles_data = load_json(ARTICLES_JSON_PATH)

    if not articles_data:
        st.warning("articles.json が空です。WordPress記事一覧管理で取得してください。")
        return
    if not link_mapping_flat:
        st.warning("linkMapping.json が空です。リンクマッピング管理でキーワードを追加してください。")
        return

    # 1) 記事検索
    search_term = st.text_input("記事タイトル検索 (一部一致)", "")
    if search_term.strip():
        filtered_articles = [
            a for a in articles_data
            if search_term.lower() in a["title"].lower()
        ]
    else:
        filtered_articles = articles_data

    # 2) 複数選択 (マルチセレクト)
    if not filtered_articles:
        st.warning("該当記事がありません。")
        return

    article_choices = [f"{a['id']} | {a['title']}" for a in filtered_articles]
    selected_items = st.multiselect("記事を選択 (複数可)", article_choices)

    # 選択された記事のリスト
    selected_articles = []
    for item in selected_items:
        # item = "25268 | [Y] デジタルならでは～..."
        # IDを取り出す (splitして [0], or rsplit with maxsplit=1, etc.)
        art_id_str = item.split("|")[0].strip()
        found = next((a for a in filtered_articles if a["id"] == art_id_str), None)
        if found:
            selected_articles.append(found)

    if not selected_articles:
        st.write("※記事が選択されていません。")
        return

    st.write("### 選択中の記事一覧")
    for art in selected_articles:
        st.markdown(f"- ID={art['id']}, タイトル={art['title']}")

    st.write("---")
    st.write("### キーワードのリンクON/OFF設定 (複数記事に対して一括操作)")

    # 3) キーワードON/OFFチェック
    #    UIとしては「キーワードごとにcheckboxを表示」する
    #    → ONなら、選択された全記事の linkUsage.json に記事IDを追加
    #    → OFFなら、選択された全記事のIDを削除
    changes_made = False

    for kw, url in link_mapping_flat.items():
        # いまキーワードが使われている記事一覧 (articles_used_in)
        if kw not in link_usage:
            link_usage[kw] = {"url": url, "articles_used_in": {}}
        usage_info = link_usage[kw]
        used_in = usage_info["articles_used_in"]

        # 「選択された記事すべて」がONになっているかどうかを判定
        # → 全部のselected_articlesが linkUsage に含まれているかどうか
        #   ※ もし一部だけON/OFF異なる場合、どうするか？
        #   とりあえず「全て含まれているときだけTrue、それ以外はFalse」にしてみる
        all_selected_on = all(art["id"] in used_in for art in selected_articles)

        # checkbox: 「このキーワードを(すべての選択記事)に挿入するか？」
        new_checked = st.checkbox(f"{kw}", value=all_selected_on)
        if new_checked != all_selected_on:
            # 変更された
            changes_made = True
            if new_checked:
                # ON → 選択記事すべて usage_info['articles_used_in'][art_id] = 1
                for art in selected_articles:
                    usage_info["articles_used_in"][art["id"]] = 1
            else:
                # OFF → 選択記事すべて usage_info から削除
                for art in selected_articles:
                    usage_info["articles_used_in"].pop(art["id"], None)

    if changes_made:
        st.warning("チェック状態に変更がありました。下記保存ボタンで確定してください。")

    # 4) 保存ボタン
    if st.button("保存 (選択記事のON/OFF設定)"):
        # linkUsage.json に反映
        save_json_locally(link_usage, LINK_USAGE_JSON_PATH)
        st.success("linkUsage.json に保存しました。")

        # どこにどんな情報が入るか？
        #  → linkUsage[キーワード]['articles_used_in'][記事ID] = 1 
        #     or 削除、という形で記録されます。

        # GitHubへコミットするか選択
        if st.checkbox("linkUsage.jsonをGitHubへコミットする"):
            usage_str = json.dumps(link_usage, ensure_ascii=False, indent=2)
            commit_to_github(usage_str, LINK_USAGE_FILE_PATH,
                             "Update linkUsage.json with multi-article operation")


# ===================================
# タブ4: WordPress記事一覧管理
# ===================================
def articles_management():
    st.subheader("WordPress 記事一覧管理 (articles.json)")
    articles_data = load_json(ARTICLES_JSON_PATH)
    st.write(f"現在の登録件数: {len(articles_data)}")

    if articles_data:
        with st.expander("登録済み記事リストを表示"):
            for art in articles_data:
                st.markdown(f"- ID={art['id']} | Title={art['title']} | URL={art['url']}")

    st.write("---")
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
                st.warning(f"記事取得失敗: HTTP {resp.status_code}")
                break

            items = resp.json()
            if not isinstance(items, list) or not items:
                break

            all_posts.extend(items)
            total_pages = resp.headers.get("X-WP-TotalPages")
            if total_pages:
                if page >= int(total_pages):
                    break
            else:
                if len(items) < per_page:
                    break

            page += 1
            if page > max_pages:
                st.warning(f"最大ページ {max_pages} 到達のため中断。")
                break

        # /media/column/ を含む投稿だけ抽出
        column_posts = []
        for p in all_posts:
            link = p.get("link","")
            if "/media/column/" in link:
                column_posts.append({
                    "id": str(p["id"]),
                    "title": p["title"]["rendered"],
                    "url": link
                })

        st.info(f"API取得: {len(all_posts)}件中、'/media/column/'含む {len(column_posts)}件を抽出")
        articles_data = column_posts
        save_json_locally(articles_data, ARTICLES_JSON_PATH)
        st.success(f"articles.json に {len(articles_data)}件上書き保存。")

    if st.button("articles.jsonをGitHubコミット"):
        js = json.dumps(articles_data, ensure_ascii=False, indent=2)
        commit_to_github(js, ARTICLES_FILE_PATH, "Update articles.json from WP REST API")


# ===================================
# メイン
# ===================================
def main():
    st.title("内部リンク管理ツール")

    # タブ順: 
    #   1) link_mapping_management
    #   2) link_usage_view
    #   3) article_based_link_management (手動)
    #   4) articles_management (WP記事一覧)
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
