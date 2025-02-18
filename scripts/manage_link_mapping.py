import streamlit as st
import json
import os
import base64
import requests

JSON_PATH = 'data/linkMapping.json'

# リポジトリ情報(ユーザー名・リポ名・対象ファイル・ブランチ)
GITHUB_REPO_OWNER = "niki-nakamura"
GITHUB_REPO_NAME = "internal-link-auto-inserter"
FILE_PATH = "data/linkMapping.json"
BRANCH = "main"  # 通常"main"

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
    st.secrets["GITHUB_TOKEN"] に PATを入れておく(Contents Write権限必須)。
    """
    # もし "GITHUB_TOKEN" が設定されていない場合はKeyErrorになるのでtry～exceptする
    try:
        token = st.secrets["GITHUB_TOKEN"]
    except KeyError:
        st.error("[ERROR] GITHUB_TOKEN がStreamlit Secretsに設定されていません。")
        return

    # GETで現在のファイルSHAを取得
    url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{FILE_PATH}?ref={BRANCH}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    get_res = requests.get(url, headers=headers)
    if get_res.status_code == 200:
        sha = get_res.json().get("sha")
    elif get_res.status_code == 404:
        sha = None  # ファイルが存在しない
    else:
        st.error(f"[ERROR] Fetching file from GitHub: {get_res.status_code}, {get_res.text}")
        return

    # PUT で更新（Base64エンコードしたcontent）
    content_b64 = base64.b64encode(mapping_json_str.encode("utf-8")).decode("utf-8")
    put_data = {
        "message": "Update linkMapping.json from Streamlit",
        "content": content_b64,
        "branch": BRANCH
    }
    if sha:
        put_data["sha"] = sha

    put_res = requests.put(url, headers=headers, json=put_data)
    if put_res.status_code in [200, 201]:
        st.success("GitHubへのコミットに成功しました！")
    else:
        st.error(f"[ERROR] GitHubへのコミットに失敗: {put_res.status_code} / {put_res.text}")

def main():
    # デバッグ用: Secretsの中身を一時的に表示（あとで削除）
    st.write("DEBUG: st.secrets:", st.secrets)

    # タイトル＆説明は1回だけにする
    st.title("内部リンク マッピング管理ツール")
    st.write("キーワードとURLを追加・編集し、[保存]ボタンでローカルJSONへ書き込み、GitHubへコミットします。")

    link_mapping = load_link_mapping()

    if not link_mapping:
        st.info("まだマッピングがありません。フォームから追加してください。")

    # 既存の項目表示・編集・削除
    for kw, url in list(link_mapping.items()):
        col1, col2, col3 = st.columns([3, 5, 1])
        with col1:
            new_kw = st.text_input("キーワード", value=kw, key=f"kw_{kw}")
        with col2:
            new_url = st.text_input("URL", value=url, key=f"url_{kw}")
        with col3:
            if st.button("削除", key=f"delete_{kw}"):
                del link_mapping[kw]
                # ▼ 修正箇所: experimental_rerun → rerun
                st.rerun()

        # キーワードやURLが変更されたときの処理
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
            # ▼ 修正箇所: experimental_rerun → rerun
            st.rerun()
        else:
            st.warning("キーワードとURLを両方入力してください。")

    # 保存ボタン（ローカル書き込み→GitHubコミット）
    if st.button("保存"):
        # 1. ローカル保存
        save_link_mapping_locally(link_mapping)
        st.success("ローカルJSONファイル更新OK")

        # 2. GitHubコミット
        mapping_json_str = json.dumps(link_mapping, ensure_ascii=False, indent=2)
        commit_to_github(mapping_json_str)

if __name__ == "__main__":
    main()
