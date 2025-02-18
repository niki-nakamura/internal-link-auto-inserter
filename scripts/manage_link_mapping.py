import streamlit as st
import json
import os
import base64
import requests

JSON_PATH = 'data/linkMapping.json'

# ★★ 以下を自分のリポジトリ情報に合わせて書き換えてください ★★
GITHUB_REPO_OWNER = "niki-nakamura"
GITHUB_REPO_NAME = "internal-link-auto-inserter"
FILE_PATH = "data/linkMapping.json"
BRANCH = "main"  # メインブランチ名
# ↑ 例示用。実際には「devブランチ」等でもOK

def load_link_mapping(path=JSON_PATH):
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_link_mapping_locally(mapping, path=JSON_PATH):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

def commit_to_github(mapping_json_str):
    """
    GitHubの contents API を使って data/linkMapping.json を更新する。
    secrets["GITHUB_TOKEN"] に PAT を入れておく。
    """
    token = st.secrets["GITHUB_TOKEN"]  # Streamlit CloudのSecretsにPATを保存
    if not token:
        st.error("GITHUB_TOKEN が設定されていません。")
        return

    # 1. 既存ファイルのSHAを取得
    url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{FILE_PATH}?ref={BRANCH}"
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
        st.error(f"Error fetching file from GitHub: {get_res.text}")
        return

    # 2. PUTで更新
    #   mapping_json_strをBase64エンコード
    content_b64 = base64.b64encode(mapping_json_str.encode("utf-8")).decode("utf-8")

    data = {
        "message": "Update linkMapping.json from Streamlit",
        "content": content_b64,
        "branch": BRANCH
    }
    if sha:
        data["sha"] = sha

    put_res = requests.put(url, headers=headers, json=data)
    if put_res.status_code in [200, 201]:
        st.success("GitHubへのコミットに成功しました！")
    else:
        st.error(f"GitHubへのコミットに失敗: {put_res.status_code} / {put_res.text}")

def main():
    st.title("内部リンク マッピング管理ツール")
    st.write("キーワードとリンク先URLを追加・編集して、[保存]ボタンでJSONに書き込み、さらにGitHubにもコミットします。")

    link_mapping = load_link_mapping()

    if not link_mapping:
        st.info("現在マッピングは空です。フォームから新規追加してください。")

    # 既存項目の表示・編集・削除
    for kw, url in list(link_mapping.items()):
        col1, col2, col3 = st.columns([3, 5, 1])
        with col1:
            new_kw = st.text_input("キーワード", value=kw, key=f"kw_{kw}")
        with col2:
            new_url = st.text_input("URL", value=url, key=f"url_{kw}")
        with col3:
            if st.button("削除", key=f"delete_{kw}"):
                del link_mapping[kw]
                st.rerun()

        if new_kw != kw:
            del link_mapping[kw]
            link_mapping[new_kw] = new_url
        elif new_url != url:
            link_mapping[kw] = new_url

    # 新規追加フォーム
    st.subheader("新規追加")
    new_kw = st.text_input("新しいキーワード", key="new_kw")
    new_url = st.text_input("新しいURL", key="new_url")
    if st.button("追加"):
        if new_kw and new_url:
            link_mapping[new_kw] = new_url
            st.success(f"追加しました: {new_kw} => {new_url}")
            st.rerun()
        else:
            st.warning("キーワードとURLを入力してください。")

    if st.button("保存 (ローカルのみ)"):
        # ローカルへの書き込み
        save_link_mapping_locally(link_mapping)
        st.success("JSONファイルにローカル保存しました。")

    # GitHubコミット用ボタン
    if st.button("保存 & GitHubに反映"):
        # ローカル書き込み
        save_link_mapping_locally(link_mapping)
        # GitHubコミット
        mapping_json_str = json.dumps(link_mapping, ensure_ascii=False, indent=2)
        commit_to_github(mapping_json_str)

if __name__ == "__main__":
    main()
