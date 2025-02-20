import streamlit as st
import json
import os
import base64
import requests

# ============================
# ファイルパスやGitHub設定
# ============================
LINK_MAPPING_JSON_PATH = 'data/linkMapping.json'
LINK_USAGE_JSON_PATH = 'data/linkUsage.json'

GITHUB_REPO_OWNER = "niki-nakamura"
GITHUB_REPO_NAME = "internal-link-auto-inserter"

LINK_MAPPING_FILE_PATH = "data/linkMapping.json"
LINK_USAGE_FILE_PATH = "data/linkUsage.json"

BRANCH = "main"


# ============================
# ユーティリティ関数
# ============================
def load_json(path: str) -> dict:
    """指定パスのJSONを読み込みdictで返す。存在しない場合は空dict"""
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json_locally(data: dict, path: str):
    """辞書をJSONにして上書き保存"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def commit_to_github(json_str: str, target_file_path: str, commit_message: str):
    """GitHubのContents APIを使ってファイルをコミット"""
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

    # 既存ファイルのSHAを取得
    get_res = requests.get(url, headers=headers)
    if get_res.status_code == 200:
        sha = get_res.json().get("sha")
    elif get_res.status_code == 404:
        sha = None  # ファイルがない場合
    else:
        st.error(f"[ERROR] Fetching file from GitHub: {get_res.status_code}, {get_res.text}")
        return

    # base64エンコード
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
        st.success(f"GitHubへのコミットに成功: {target_file_path}")
    else:
        st.error(f"[ERROR] GitHubコミット失敗: {put_res.status_code} / {put_res.text}")


# ============================
# 1) リンクマッピング管理UI
# ============================
def link_mapping_management():
    st.subheader("リンクマッピングの管理 (linkMapping.json)")
    link_mapping = load_json(LINK_MAPPING_JSON_PATH)

    if not link_mapping:
        st.info("まだマッピングがありません。下記フォームから追加してください。")

    # 既存項目を一覧表示・編集
    for kw, url in list(link_mapping.items()):
        col1, col2, col3 = st.columns([3, 5, 1])
        new_kw = col1.text_input("キーワード", value=kw, key=f"kw_{kw}").strip()
        new_url = col2.text_input("URL", value=url, key=f"url_{kw}").strip()

        # 削除ボタン
        if col3.button("削除", key=f"delete_{kw}"):
            del link_mapping[kw]
            save_json_locally(link_mapping, LINK_MAPPING_JSON_PATH)
            st.success(f"削除しました: {kw}")
            st.rerun()

        # キーワード or URL が変更された場合の処理
        if new_kw != kw:
            # キー変更は「旧キー削除→新キー追加」
            del link_mapping[kw]
            link_mapping[new_kw] = new_url
        elif new_url != url:
            link_mapping[kw] = new_url

    # 新規追加フォーム
    st.markdown("---")
    st.markdown("**新規追加**")
    input_kw = st.text_input("新しいキーワード", key="new_kw").strip()
    input_url = st.text_input("新しいURL", key="new_url").strip()

    if st.button("追加 (linkMapping)"):
        if input_kw and input_url:
            link_mapping[input_kw] = input_url
            save_json_locally(link_mapping, LINK_MAPPING_JSON_PATH)
            st.success(f"追加しました: {input_kw} => {input_url}")
            st.rerun()
        else:
            st.warning("キーワードとURLを両方入力してください。")

    # 保存ボタン (GitHubコミット)
    if st.button("保存 (linkMapping.json をGitHubへ)"):
        # ローカル保存
        save_json_locally(link_mapping, LINK_MAPPING_JSON_PATH)
        st.success("ローカルファイル(linkMapping.json)を更新しました。")

        # GitHubへコミット
        mapping_json_str = json.dumps(link_mapping, ensure_ascii=False, indent=2)
        commit_to_github(
            json_str=mapping_json_str,
            target_file_path=LINK_MAPPING_FILE_PATH,
            commit_message="Update linkMapping.json from Streamlit"
        )


# ============================
# 2) リンク使用状況の確認UI
# ============================
def link_usage_view():
    st.subheader("リンク使用状況の確認 (linkUsage.json)")
    link_usage = load_json(LINK_USAGE_JSON_PATH)
    
    if not link_usage:
        st.info("まだ使用状況の記録がありません。")
        return
    
    for kw, usage_info in link_usage.items():
        st.markdown(f"**キーワード:** {kw}")
        # usage_info 例: { "url": "...", "articles_used_in": {"article1.md": 2, ...} }
        registered_url = usage_info.get("url", "")
        st.write(f"・登録URL: {registered_url}")

        articles_used_in = usage_info.get("articles_used_in", {})
        if articles_used_in:
            st.write(f"・使用記事数: {len(articles_used_in)}")
            total_inserts = sum(articles_used_in.values())
            st.write(f"・合計挿入回数: {total_inserts}")
            with st.expander("内訳を表示"):
                for article_file, count in articles_used_in.items():
                    st.write(f" - {article_file}: {count}回 挿入")
        else:
            st.write("・まだ記事への使用記録はありません。")

    # 必要があれば usage.json をコミットするボタンも用意
    if st.button("使用状況をGitHubへコミット"):
        usage_json_str = json.dumps(link_usage, ensure_ascii=False, indent=2)
        commit_to_github(
            json_str=usage_json_str,
            target_file_path=LINK_USAGE_FILE_PATH,
            commit_message="Update linkUsage.json from Streamlit"
        )


# ============================
# 3) 記事別リンク管理UI
#    - プルダウンで記事を選び、
#      キーワードごとに挿入する/しないをチェックボックスで管理
# ============================
def article_based_management():
    st.subheader("記事別リンク管理")
    link_mapping = load_json(LINK_MAPPING_JSON_PATH)
    link_usage = load_json(LINK_USAGE_JSON_PATH)

    # 全記事のリストアップ方法 (例: linkUsage.json の全記事名を集計 or 手動管理)
    # 今回は、usageに記録済みのすべての記事 + 任意で追加したものを統合してセレクトボックスにする例
    articles_set = set()
    for kw, usage_info in link_usage.items():
        for article_name in usage_info.get("articles_used_in", {}):
            articles_set.add(article_name)
    articles_list = sorted(list(articles_set))

    st.write("#### 1) 記事を選択 or 追加")

    # 新規記事追加フォーム
    new_article = st.text_input("新規記事名（例: article5.md）").strip()
    if st.button("記事を追加"):
        if new_article and new_article not in articles_list:
            articles_list.append(new_article)
            articles_list.sort()
            st.success(f"記事 '{new_article}' を追加しました。")
            st.experimental_rerun()
        else:
            st.warning("記事名が空か、既に存在しています。")

    # 記事選択
    if len(articles_list) == 0:
        st.info("まだ記事がありません。上記フォームで記事を追加してください。")
        return
    selected_article = st.selectbox("記事を選択", articles_list)

    st.markdown("---")
    st.write(f"#### 2) `{selected_article}` のリンク挿入を管理")

    # キーワード一覧に対して、チェックボックスで「挿入するかどうか」をON/OFF
    # linkUsage[kw]["articles_used_in"][selected_article] が 1以上ならチェックON、なければOFF
    # (※回数管理ではなくON/OFF管理にする例では 1 or 0 にしてもOK)
    # 下記では回数管理を踏襲し、0 or 1で扱うサンプル
    usage_changed = False

    for kw in link_mapping.keys():
        # linkUsage に存在しない場合は初期化
        if kw not in link_usage:
            link_usage[kw] = {
                "url": link_mapping[kw],
                "articles_used_in": {}
            }

        # articles_used_in を取り出し
        articles_dict = link_usage[kw].setdefault("articles_used_in", {})

        current_count = articles_dict.get(selected_article, 0)
        is_checked = (current_count > 0)  # 1以上ならON

        # チェックボックス
        new_checked = st.checkbox(f"【{kw}】にリンクを挿入", value=is_checked)

        if new_checked != is_checked:
            usage_changed = True
            # チェックONになった→挿入回数を1回としてセット
            if new_checked:
                articles_dict[selected_article] = 1
            else:
                # チェックOFFになった→削除 or 0にする
                if selected_article in articles_dict:
                    del articles_dict[selected_article]

    # 変更があった場合、保存ボタンを表示
    if usage_changed:
        st.warning("チェック変更がありました。下記ボタンで保存してください。")

    if st.button("保存 (この記事のリンクON/OFF設定)"):
        # link_usage を保存
        save_json_locally(link_usage, LINK_USAGE_JSON_PATH)
        st.success(f"linkUsage.json を更新しました。'{selected_article}'の設定を反映。")

        # （必要ならGitHubへコミット）
        if st.checkbox("linkUsage.json をGitHubにコミットする"):
            usage_json_str = json.dumps(link_usage, ensure_ascii=False, indent=2)
            commit_to_github(
                json_str=usage_json_str,
                target_file_path=LINK_USAGE_FILE_PATH,
                commit_message=f"Update linkUsage.json for article: {selected_article}"
            )


# ============================
# メイン関数
# ============================
def main():
    st.title("内部リンク管理ツール")
    tabs = st.tabs(["リンクマッピング管理", "リンク使用状況の確認", "記事別リンク管理"])

    with tabs[0]:
        link_mapping_management()

    with tabs[1]:
        link_usage_view()

    with tabs[2]:
        article_based_management()


if __name__ == "__main__":
    main()
