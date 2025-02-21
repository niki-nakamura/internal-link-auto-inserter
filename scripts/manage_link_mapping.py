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

# ===================================
# linkUsage表示 (「全記事の内部リンク状況一覧」のみ)
# ===================================
def link_usage_view():
    st.subheader("全記事の内部リンク状況一覧")

    link_usage = load_json(LINK_USAGE_JSON_PATH)
    articles_data = load_json(ARTICLES_JSON_PATH)

    if not link_usage or not articles_data:
        st.info("linkUsage.json または articles.json が空です。")
        return

    # 1) article_usage_summaryを作る (記事ID→{ 'title','url','total_link_count','details':{kw:count} })
    article_usage_summary = {}
    for kw, usage_info in link_usage.items():
        for art_id, count in usage_info.get("articles_used_in", {}).items():
            if art_id not in article_usage_summary:
                article_usage_summary[art_id] = {
                    "title": None,
                    "url": None,
                    "total_link_count": 0,
                    "details": {}
                }
            article_usage_summary[art_id]["total_link_count"] += count
            article_usage_summary[art_id]["details"].setdefault(kw, 0)
            article_usage_summary[art_id]["details"][kw] += count

    # articles.jsonをもとにタイトル/URLを補完
    for art in articles_data:
        art_id = art["id"]
        if art_id not in article_usage_summary:
            # この記事は内部リンク0回の可能性もある
            article_usage_summary[art_id] = {
                "title": art["title"],
                "url": art["url"],
                "total_link_count": 0,
                "details": {}
            }
        else:
            # 補完
            article_usage_summary[art_id]["title"] = art["title"]
            article_usage_summary[art_id]["url"]   = art["url"]

    # 2) 検索フォーム＆ソート
    st.write("#### フィルタ・ソート設定")
    # (a) 記事タイトル検索
    article_search = st.text_input("記事タイトル検索", value="").strip()
    # (b) 内部リンクキーワードの検索
    kw_search = st.text_input("内部リンクキーワード検索", value="").strip()
    # (c) ソート順選択
    sort_option = st.selectbox("ソート順", ["多い順", "少ない順", "記事ID昇順", "記事ID降順"])

    # 3) article_usage_summaryをリスト化して検索・ソート
    summary_list = []
    for art_id, info in article_usage_summary.items():
        # 記事タイトル or KW 検索フィルタ
        title_match = (article_search.lower() in info["title"].lower()) if article_search else True

        # キーワード検索にマッチするか（detailsのkeyにkw_searchが含まれるか）
        if kw_search:
            # いずれかのキーワードが部分一致すればOK
            kw_found = any(kw_search.lower() in kw.lower() for kw in info["details"].keys())
        else:
            kw_found = True

        if title_match and kw_found:
            summary_list.append((art_id, info))

    # ソート処理
    if sort_option == "多い順":
        summary_list.sort(key=lambda x: x[1]["total_link_count"], reverse=True)
    elif sort_option == "少ない順":
        summary_list.sort(key=lambda x: x[1]["total_link_count"])
    elif sort_option == "記事ID昇順":
        summary_list.sort(key=lambda x: int(x[0]))
    elif sort_option == "記事ID降順":
        summary_list.sort(key=lambda x: int(x[0]), reverse=True)

    st.write(f"#### 全 {len(summary_list)} 件の記事の内部リンク状況一覧 (絞り込み後)")

    # 4) 出力
    for (art_id, info) in summary_list:
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

# ===================================
# スタブ: 他のタブを消したい場合は以下を省略可
# （ここでは例示として最低限の構成に）
# ===================================
def main():
    st.title("内部リンク管理ツール")
    link_usage_view()

if __name__ == "__main__":
    main()
