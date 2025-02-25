import streamlit as st
import json
import os
import base64
import requests
import re

# ===================================
# 設定・定数
# ===================================
LINK_MAPPING_FILE_PATH = "data/linkMapping.json"
LINK_USAGE_FILE_PATH   = "data/linkUsage.json"
ARTICLES_FILE_PATH     = "data/articles.json"

GITHUB_REPO_OWNER = "niki-nakamura"
GITHUB_REPO_NAME  = "internal-link-auto-inserter"
BRANCH            = "main"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

# ===================================
# ヘルパー関数 (JSON読み書き, GitHubコミット等)
# ===================================
def load_json(path: str):
    if not os.path.exists(path):
        # articles.json は [] で初期化、それ以外は {}
        return [] if "articles" in path else {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json_locally(data, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def commit_to_github(json_str: str, target_file_path: str, commit_message: str):
    """GitHub上のファイルにコミットする"""
    import os
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        st.error("[ERROR] GITHUB_TOKEN が環境変数に設定されていません。GitHubへのコミットは実行できません。")
        return

    url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{target_file_path}?ref={BRANCH}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    # 既存ファイルのSHA取得
    get_res = requests.get(url, headers=headers)
    if get_res.status_code == 200:
        sha = get_res.json().get("sha")
    elif get_res.status_code == 404:
        sha = None
    else:
        st.error(f"[ERROR] Fetch file from GitHub: status={get_res.status_code}, msg={get_res.text}")
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
        st.success(f"GitHubへのコミット成功: {target_file_path}")
    else:
        st.error(f"[ERROR] GitHubコミット失敗: {put_res.status_code}, {put_res.text}")

def flatten_link_mapping(nested_map: dict) -> dict:
    """
    linkMapping.jsonの階層
      {
        "カテゴリA": {"キーワード1": "URL1", ...},
        "カテゴリB": {"キーワード2": "URL2", ...}
      }
    をフラットな
      {
        "キーワード1": "URL1",
        "キーワード2": "URL2",
        ...
      }
    に変換する
    """
    flat_map = {}
    for cat, kvdict in nested_map.items():
        flat_map.update(kvdict)
    return flat_map

# ===================================
# WordPress関連 (記事更新)
# ===================================
def get_auth_headers(username, password):
    token = base64.b64encode(f"{username}:{password}".encode()).decode("utf-8")
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }

def get_post_raw_content(post_id, WP_URL, WP_USERNAME, WP_PASSWORD):
    headers = get_auth_headers(WP_USERNAME, WP_PASSWORD)
    resp = requests.get(
        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}?context=edit",
        headers=headers
    )
    if resp.status_code != 200:
        print(f"[WARN] get_post_raw_content: status={resp.status_code}, post_id={post_id}")
        return ""
    data = resp.json()
    return data.get("content", {}).get("raw", "")

def insert_links_to_content(content, link_mapping, max_links_per_post=3):
    """
    link_mapping: { キーワード: URL, ... }
    キーワードが文章中に出現したら最初の1回だけアンカータグ化。
    既にリンクがある箇所はスキップ。
    ショートコード([...])は一時置換で回避。
    """
    links_added = 0

    # ショートコード除外用
    shortcode_pattern = r"(\[.*?\])"
    shortcodes = []
    def shortcode_replacer(m):
        shortcodes.append(m.group(0))
        return f"__SHORTCODE_{len(shortcodes)-1}__"

    content = re.sub(shortcode_pattern, shortcode_replacer, content)

    # キーワードごとに検索してリンク挿入
    for kw, url in link_mapping.items():
        if links_added >= max_links_per_post:
            break
        pattern = rf'(<a[^>]*>.*?</a>|{re.escape(kw)})'

        def replacement(m):
            nonlocal links_added
            text = m.group(0)
            # 既にリンクのタグ内ならそのまま
            if text.lower().startswith("<a"):
                return text
            # ここでリンク化
            links_added += 1
            return f'<a href="{url}">{text}</a>'

        updated = re.sub(pattern, replacement, content, count=1)
        if updated != content:
            content = updated

    # ショートコード復元
    def shortcode_restore(m):
        idx = int(m.group(1).split("_")[-1])
        return shortcodes[idx]

    content = re.sub(r"__SHORTCODE_(\d+)__", shortcode_restore, content)
    return content

def update_post_content(post_id, new_content, WP_URL, WP_USERNAME, WP_PASSWORD):
    headers = get_auth_headers(WP_USERNAME, WP_PASSWORD)
    payload = {"content": new_content}
    resp = requests.post(
        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
        json=payload,
        headers=headers
    )
    return resp.status_code, resp.text

def run_insert_links(articles_data, link_usage, WP_URL, WP_USERNAME, WP_PASSWORD):
    """
    link_usage:
      {
        "キーワードA": {
          "url": "https://...",
          "articles_used_in": {
             "1234": 回数, "5678": 回数
          }
        },
        ...
      }

    上記に基づき、(articles_used_in に1回以上設定されている)記事へリンク挿入。
    """
    # 記事ID -> {キーワード:URL} の辞書を作る
    article_to_kws = {}
    for kw, usage_info in link_usage.items():
        link_url = usage_info.get("url", "")
        for art_id_str in usage_info.get("articles_used_in", {}):
            article_to_kws.setdefault(art_id_str, {})[kw] = link_url

    # 各記事に対してリンクを挿入
    for art_id_str, kw_map in article_to_kws.items():
        post_id = int(art_id_str)
        found_article = next((a for a in articles_data if a["id"] == art_id_str), None)
        art_title = found_article["title"] if found_article else "(不明)"

        raw_content = get_post_raw_content(post_id, WP_URL, WP_USERNAME, WP_PASSWORD)
        if not raw_content:
            print(f"[WARN] No content for {post_id} ({art_title}), skip.")
            continue

        updated_content = insert_links_to_content(raw_content, kw_map, max_links_per_post=3)
        if updated_content != raw_content:
            status, txt = update_post_content(post_id, updated_content, WP_URL, WP_USERNAME, WP_PASSWORD)
            print(f"Updated post {post_id} ({art_title}), status={status}")
        else:
            print(f"No changes for post {post_id} ({art_title}).")

# ===================================
# タブ1: リンクマッピング管理
# ===================================
def link_mapping_management():
    st.subheader("リンクマッピング管理 (linkMapping.json)")

    link_mapping_data = load_json(LINK_MAPPING_FILE_PATH)

    # もし旧フラット形式ならUncategorizedへ移行する例
    if link_mapping_data and not all(isinstance(v, dict) for v in link_mapping_data.values()):
        st.warning("旧来のフラット構造を検出。'Uncategorized' カテゴリに移行します。")
        link_mapping_data = {"Uncategorized": link_mapping_data}
        save_json_locally(link_mapping_data, LINK_MAPPING_FILE_PATH)

    if not link_mapping_data:
        link_mapping_data = {}

    # カテゴリ一覧の表示・編集
    st.write("## カテゴリ一覧")
    if not link_mapping_data:
        st.info("まだカテゴリーがありません。")
    else:
        category_list = sorted(link_mapping_data.keys())
        for category_name in category_list:
            with st.expander(f"カテゴリー: {category_name}", expanded=False):
                cat_data = link_mapping_data[category_name]

                # カテゴリ名を変更 or 削除
                col1, col2 = st.columns([3,1])
                new_cat_name = col1.text_input(
                    "カテゴリー名",
                    value=category_name,
                    key=f"txt_cat_{category_name}"
                ).strip()
                if col2.button("削除", key=f"del_cat_{category_name}"):
                    del link_mapping_data[category_name]
                    save_json_locally(link_mapping_data, LINK_MAPPING_FILE_PATH)
                    st.success(f"カテゴリー '{category_name}' を削除しました。")
                    st.experimental_rerun()
                if new_cat_name and new_cat_name != category_name:
                    if new_cat_name in link_mapping_data:
                        st.error(f"既に同名カテゴリ '{new_cat_name}' が存在します。")
                    else:
                        link_mapping_data[new_cat_name] = cat_data
                        del link_mapping_data[category_name]
                        save_json_locally(link_mapping_data, LINK_MAPPING_FILE_PATH)
                        st.success(f"カテゴリー名を '{new_cat_name}' に変更しました。")
                        st.experimental_rerun()

                st.write("### キーワード/URL の一覧")
                for kw, url in list(cat_data.items()):
                    c1, c2, c3 = st.columns([3,6,1])
                    new_kw = c1.text_input("キーワード", value=kw, key=f"kw_{category_name}_{kw}").strip()
                    new_url = c2.text_input("URL", value=url, key=f"url_{category_name}_{kw}").strip()
                    # 削除ボタン
                    if c3.button("削除", key=f"del_{category_name}_{kw}"):
                        del cat_data[kw]
                        save_json_locally(link_mapping_data, LINK_MAPPING_FILE_PATH)
                        st.success(f"キーワード '{kw}' を削除しました。")
                        st.experimental_rerun()
                    # 更新
                    if new_kw != kw:
                        if new_kw in cat_data:
                            st.error(f"既にキーワード '{new_kw}' が存在します。")
                        else:
                            del cat_data[kw]
                            cat_data[new_kw] = new_url
                            save_json_locally(link_mapping_data, LINK_MAPPING_FILE_PATH)
                            st.success(f"キーワード名を '{new_kw}' に変更しました。")
                            st.experimental_rerun()
                    elif new_url != url:
                        cat_data[kw] = new_url
                        save_json_locally(link_mapping_data, LINK_MAPPING_FILE_PATH)
                        st.success(f"URLを更新しました。(キーワード={kw})")
                        st.experimental_rerun()

                st.write("### 新規キーワード追加")
                new_kw_add = st.text_input("キーワード", key=f"add_kw_{category_name}").strip()
                new_url_add = st.text_input("URL", key=f"add_url_{category_name}").strip()
                if st.button("追加", key=f"add_btn_{category_name}"):
                    if new_kw_add and new_url_add:
                        if new_kw_add in cat_data:
                            st.warning(f"キーワード '{new_kw_add}' は既に存在します。")
                        else:
                            cat_data[new_kw_add] = new_url_add
                            save_json_locally(link_mapping_data, LINK_MAPPING_FILE_PATH)
                            st.success(f"新規キーワード '{new_kw_add}' を追加しました。")
                            st.experimental_rerun()
                    else:
                        st.warning("キーワードとURLを入力してください。")

    st.write("## 新規カテゴリー追加")
    new_cat = st.text_input("カテゴリー名を入力", key="input_new_cat").strip()
    if st.button("新規カテゴリー作成"):
        if new_cat:
            if new_cat in link_mapping_data:
                st.warning(f"カテゴリ '{new_cat}' は既に存在します。")
            else:
                link_mapping_data[new_cat] = {}
                save_json_locally(link_mapping_data, LINK_MAPPING_FILE_PATH)
                st.success(f"新規カテゴリー '{new_cat}' を追加しました。")
                st.experimental_rerun()
        else:
            st.warning("カテゴリー名を入力してください。")

    # GitHubコミットボタン
    if st.button("linkMapping.json をGitHubへコミット"):
        js_str = json.dumps(link_mapping_data, ensure_ascii=False, indent=2)
        commit_to_github(js_str, LINK_MAPPING_FILE_PATH, "Update linkMapping.json from Streamlit")

# ===================================
# タブ2: 全記事リンク管理 (使用状況とON/OFF一括設定)
# ===================================
def all_articles_link_management():
    st.subheader("全記事リンク管理：使用状況の確認＆ON/OFF一括設定")

    # WordPress認証情報
    WP_URL      = os.environ.get("WP_URL", "")
    WP_USERNAME = os.environ.get("WP_USERNAME", "")
    WP_PASSWORD = os.environ.get("WP_PASSWORD", "")

    # データ読み込み
    nested_mapping = load_json(LINK_MAPPING_FILE_PATH)
    link_usage     = load_json(LINK_USAGE_FILE_PATH)
    articles_data  = load_json(ARTICLES_FILE_PATH)

    # linkMappingが空の場合
    if not nested_mapping:
        st.warning("linkMapping.json が空です。先に「リンクマッピング管理」でキーワードとURLを設定してください。")
        return
    # articlesが空の場合
    if not articles_data:
        st.warning("articles.json が空です。先に「WordPress記事一覧管理」で記事を取得してください。")
        return

    # フラット化した {kw: url} を取得
    link_mapping_flat = flatten_link_mapping(nested_mapping)

    # linkUsage.json が未初期化の場合は、link_mapping_flat構造に応じて空テンプレを作る
    if not link_usage:
        link_usage = {}
        for kw, url in link_mapping_flat.items():
            link_usage[kw] = {
                "url": url,
                "articles_used_in": {}
            }

    # urlが変わっている可能性を同期
    for kw, url in link_mapping_flat.items():
        if kw not in link_usage:
            link_usage[kw] = {"url": url, "articles_used_in": {}}
        else:
            if link_usage[kw].get("url") != url:
                link_usage[kw]["url"] = url

    # まず記事ごとの「リンク使用合計」を一覧表示
    # （記事タイトル検索やキーワード検索のフィルタ）
    st.write("### フィルタ・ソート")
    col1, col2, col3 = st.columns([3,3,2])
    f_article = col1.text_input("記事タイトル検索(一部一致)", key="usage_search_title").strip()
    f_kw      = col2.text_input("キーワード検索(一部一致)", key="usage_search_kw").strip()
    sort_opt  = col3.selectbox("ソート順", ["多い順", "少ない順", "記事ID昇順", "記事ID降順"], key="usage_sort")

    # 記事ID -> 合計リンク数, 内訳
    article_usage_summary = {}
    for art in articles_data:
        art_id = art["id"]
        article_usage_summary[art_id] = {
            "title": art["title"],
            "url": art["url"],
            "total_link_count": 0,
            "details": {}
        }

    # linkUsageから記事別リンク数を集計
    for kw, usage_info in link_usage.items():
        used_in = usage_info.get("articles_used_in", {})
        for art_id, cnt in used_in.items():
            if art_id not in article_usage_summary:
                # もしarticles.jsonに未登録のIDがあってもスキップ
                continue
            article_usage_summary[art_id]["total_link_count"] += cnt
            article_usage_summary[art_id]["details"].setdefault(kw, 0)
            article_usage_summary[art_id]["details"][kw] += cnt

    # フィルタに応じてサマリを抽出
    filtered_list = []
    for art_id, info in article_usage_summary.items():
        # 記事タイトルにフィルタ
        if f_article:
            if f_article.lower() not in info["title"].lower():
                continue
        # キーワードフィルタ
        if f_kw:
            # detailsにf_kwを含むkwがなければ除外
            matched_kws = [kw for kw in info["details"].keys() if f_kw.lower() in kw.lower()]
            if not matched_kws:
                continue
        filtered_list.append((art_id, info))

    # ソート
    if sort_opt == "多い順":
        filtered_list.sort(key=lambda x: x[1]["total_link_count"], reverse=True)
    elif sort_opt == "少ない順":
        filtered_list.sort(key=lambda x: x[1]["total_link_count"])
    elif sort_opt == "記事ID昇順":
        filtered_list.sort(key=lambda x: int(x[0]))
    else:
        filtered_list.sort(key=lambda x: int(x[0]), reverse=True)

    st.write(f"#### 該当記事数: {len(filtered_list)}")

    # マルチ選択 (一括操作したい記事)
    display_options = [f"{art_id} | {info['title']}" for (art_id, info) in filtered_list]
    selected_articles_disp = st.multiselect("一括操作する記事を選択（複数可）", display_options)
    selected_articles = []
    for disp in selected_articles_disp:
        _id = disp.split("|")[0].strip()
        selected_articles.append(_id)

    # 記事一覧表示 (参考用)
    for art_id, info in filtered_list:
        st.markdown(f"**{info['title']}** (ID={art_id}) [ [記事URL]({info['url']}) ]")
        if info["total_link_count"] == 0:
            st.write("- 内部リンクはありません。")
        else:
            detail_txt = ", ".join([f"{k}({c}回)" for k,c in info["details"].items()])
            st.write(f"- リンク挿入合計: {info['total_link_count']} ( {detail_txt} )")

    # --- キーワードのON/OFF切替 ---
    st.write("---")
    st.write("### 選択した記事に対してキーワードのリンクON/OFF設定")
    if not selected_articles:
        st.info("記事が選択されていません。上の一覧から操作対象の記事を選んでください。")
        return

    changed = False
    # link_mapping_flat のキーワード一覧をチェックボックスでON/OFF
    for kw, url in link_mapping_flat.items():
        usage_info = link_usage.setdefault(kw, {"url": url, "articles_used_in": {}})
        used_in = usage_info["articles_used_in"]
        # 選択記事が全てONかどうか
        all_on = all(art_id in used_in for art_id in selected_articles)
        new_val = st.checkbox(f"{kw}", value=all_on, key=f"chk_{kw}")
        if new_val != all_on:
            changed = True
            if new_val:
                # ON
                for art_id in selected_articles:
                    used_in[art_id] = 1  # 回数は仮に1
            else:
                # OFF
                for art_id in selected_articles:
                    used_in.pop(art_id, None)

    if changed:
        st.warning("キーワードのON/OFF変更がありました。まだ保存されていません。")

    if st.button("変更を保存 & WordPress更新"):
        # 1) linkUsage.jsonに保存
        save_json_locally(link_usage, LINK_USAGE_FILE_PATH)
        st.success("linkUsage.json を保存しました。")

        # 2) WP更新 (選択記事に対してリンク挿入)
        if not (WP_URL and WP_USERNAME and WP_PASSWORD):
            st.error("環境変数 WP_URL / WP_USERNAME / WP_PASSWORD が設定されていません。WP更新はスキップします。")
            return

        run_insert_links(articles_data, link_usage, WP_URL, WP_USERNAME, WP_PASSWORD)
        st.success("選択記事へのリンク挿入（WP更新）を完了しました。")

        # 3) GitHubコミット (必要に応じて)
        if st.checkbox("linkUsage.json をGitHubへコミットする", value=False):
            usage_str = json.dumps(link_usage, ensure_ascii=False, indent=2)
            commit_to_github(usage_str, LINK_USAGE_FILE_PATH, "Update linkUsage.json & WP updated")

# ===================================
# タブ3: WordPress記事一覧管理
# ===================================
def articles_management():
    st.subheader("WordPress記事一覧管理 (articles.json)")

    articles_data = load_json(ARTICLES_FILE_PATH)
    st.write(f"登録済み記事数: {len(articles_data)}")

    if articles_data:
        with st.expander("▼ 登録済みの記事一覧"):
            for a in articles_data:
                st.write(f"- ID={a['id']}, {a['title']}, {a['url']}")

    # WordPressから記事を取得
    st.write("---")
    base_url = st.text_input("WP REST APIエンドポイントURL",
                             value="https://good-apps.jp/wp-json/wp/v2/posts",
                             key="txt_wp_rest_url")
    if st.button("WordPress記事を取得 (REST API)"):
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
                st.warning(f"最大ページ {max_pages} に達したので打ち切りました。")
                break

        # '/media/column/' を含む投稿のみ抽出する例
        filtered = []
        for p in all_posts:
            link = p.get("link", "")
            if "/media/column/" in link:
                filtered.append({
                    "id": str(p["id"]),
                    "title": p["title"]["rendered"],
                    "url": link
                })

        st.info(f"REST取得: 全{len(all_posts)}件 → '/media/column/'含む {len(filtered)}件をarticles.jsonへ保存")
        articles_data = filtered
        save_json_locally(articles_data, ARTICLES_FILE_PATH)
        st.success(f"articles.json を更新しました（{len(filtered)}件）。")

    # GitHubコミット
    if st.button("articles.json をGitHubへコミット"):
        js = json.dumps(articles_data, ensure_ascii=False, indent=2)
        commit_to_github(js, ARTICLES_FILE_PATH, "Update articles.json from WP REST API")

# ===================================
# メイン: Streamlitアプリ
# ===================================
def main():
    st.title("内部リンク管理ツール")

    tabs = st.tabs([
        "リンクマッピング管理",
        "全記事リンク管理",
        "WordPress記事一覧管理"
    ])

    with tabs[0]:
        link_mapping_management()

    with tabs[1]:
        all_articles_link_management()

    with tabs[2]:
        articles_management()

if __name__ == "__main__":
    main()
