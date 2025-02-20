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

GITHUB_REPO_OWNER = "niki-nakamura"
GITHUB_REPO_NAME = "internal-link-auto-inserter"

# linkMapping.json 用
LINK_MAPPING_FILE_PATH = "data/linkMapping.json"
# linkUsage.json 用（必要に応じてコミット対応する場合は使う）
LINK_USAGE_FILE_PATH = "data/linkUsage.json"

BRANCH = "main"

# ===================================
# ユーティリティ関数
# ===================================

def load_json(path: str) -> dict:
    """指定パスのJSONを読み込んでdictで返す。存在しなければ空dict。"""
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json_locally(data: dict, path: str):
    """dictをJSONファイルへ保存(上書き)する。"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def commit_to_github(json_str: str, target_file_path: str, commit_message: str):
    """
    GitHubのContents APIを使ってJSONファイルを更新する。
    st.secrets["secrets"]["GITHUB_TOKEN"] にPAT(Contents Write権限必須)を設定しておくこと。
    """
    # トークンがSecretsに入っているか確認
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

    # 既存SHAの取得
    get_res = requests.get(url, headers=headers)
    if get_res.status_code == 200:
        sha = get_res.json().get("sha")
    elif get_res.status_code == 404:
        # ファイルが存在しない場合はNone
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
# メインアプリ
# ===================================
def main():
    st.title("内部リンク マッピング管理ツール")
    st.write("キーワードとURLを追加・編集し、[保存]ボタンでローカルJSONへ書き込み→GitHubへコミットします。")

    # -------------------------------
    # 1) linkMapping.json の編集UI
    # -------------------------------
    link_mapping = load_json(LINK_MAPPING_JSON_PATH)
    
    st.header("リンクマッピングの管理")
    if not link_mapping:
        st.info("まだリンクマッピングがありません。下記フォームから追加してください。")

    # 既存項目の表示・編集・削除
    # キーワード kw と URL を編集可能にし、「削除」ボタンも配置
    for kw, url in list(link_mapping.items()):
        col1, col2, col3 = st.columns([3, 5, 1])

        new_kw = col1.text_input("キーワード", value=kw, key=f"kw_{kw}").strip()
        new_url = col2.text_input("URL", value=url, key=f"url_{kw}").strip()

        # 削除ボタン
        if col3.button("削除", key=f"delete_{kw}"):
            # link_mapping から削除
            del link_mapping[kw]
            save_json_locally(link_mapping, LINK_MAPPING_JSON_PATH)
            st.success(f"削除しました: {kw}")
            st.rerun()

        # キーワード／URL が変更された場合の追従
        if new_kw != kw:
            # キー変更（＝実質、旧キー削除→新キー追加）
            del link_mapping[kw]
            link_mapping[new_kw] = new_url
        elif new_url != url:
            # URL変更
            link_mapping[kw] = new_url

    # 新規追加フォーム
    st.subheader("新規追加")
    input_kw = st.text_input("新しいキーワード", key="new_kw").strip()
    input_url = st.text_input("新しいURL", key="new_url").strip()

    if st.button("追加"):
        if input_kw and input_url:
            link_mapping[input_kw] = input_url
            save_json_locally(link_mapping, LINK_MAPPING_JSON_PATH)
            st.success(f"追加しました: {input_kw} => {input_url}")
            st.rerun()
        else:
            st.warning("キーワードとURLを両方入力してください。")

    # 保存ボタン (最終的にGitHubへコミット)
    if st.button("保存 (linkMapping.json)"):
        # ローカルファイルに保存
        save_json_locally(link_mapping, LINK_MAPPING_JSON_PATH)
        st.success("ローカルJSONファイル(linkMapping.json)を更新しました")

        # GitHubコミット
        mapping_json_str = json.dumps(link_mapping, ensure_ascii=False, indent=2)
        commit_to_github(
            json_str=mapping_json_str,
            target_file_path=LINK_MAPPING_FILE_PATH,
            commit_message="Update linkMapping.json from Streamlit"
        )

    # -------------------------------
    # 2) リンク使用状況 (linkUsage.json) の表示
    #    ※デフォルトは読み取り専用
    # -------------------------------
    st.header("リンク使用状況の確認")
    link_usage = load_json(LINK_USAGE_JSON_PATH)

    if not link_usage:
        st.info("まだ使用状況が記録されていません。")
    else:
        # 表示例: キーワードごとに記事数や挿入回数を表示
        for kw, usage_info in link_usage.items():
            st.markdown(f"**キーワード:** {kw}")
            url_in_usage = usage_info.get("url", "")
            st.write(f"- 登録URL: {url_in_usage}")

            articles_used = usage_info.get("articles_used_in", {})
            if articles_used:
                st.write(f"- 使用記事数: {len(articles_used)}")
                total_inserts = sum(articles_used.values())
                st.write(f"- 合計挿入回数: {total_inserts}")
                with st.expander("使用内訳を表示"):
                    for article_file, count in articles_used.items():
                        st.write(f"  - {article_file}: {count}回 挿入")
            else:
                st.write("- まだ使用記録がありません。")

    # （必要に応じて linkUsage.json をコミットするボタンを設置）
    # if st.button("使用状況をGitHubへコミット"):
    #     usage_json_str = json.dumps(link_usage, ensure_ascii=False, indent=2)
    #     commit_to_github(
    #         json_str=usage_json_str,
    #         target_file_path=LINK_USAGE_FILE_PATH,
    #         commit_message="Update linkUsage.json from Streamlit"
    #     )

if __name__ == "__main__":
    main()
