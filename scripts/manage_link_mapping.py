import streamlit as st
import json
import os
import base64
import requests

JSON_PATH = 'data/linkMapping.json'

GITHUB_REPO_OWNER = "niki-nakamura"
GITHUB_REPO_NAME = "internal-link-auto-inserter"
FILE_PATH = "data/linkMapping.json"
BRANCH = "main"

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
    st.secrets["secrets"]["GITHUB_TOKEN"] に PAT を入れておく(Contents Write権限必須)。
    """
    try:
        token = st.secrets["secrets"]["GITHUB_TOKEN"]
    except KeyError:
        st.error("[ERROR] GITHUB_TOKEN がStreamlit Secretsに設定されていません。")
        return

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
        st.error(f"[ERROR] Fetching file from GitHub: {get_res.status_code}, {get_res.text}")
        return

    # Base64エンコードしてPUT
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
    # デバッグ表示は不要なら削除してOK
    # st.write("DEBUG: st.secrets:", st.secrets)

    st.title("内部リンク マッピング管理ツール")
    st.write("キーワードとURLを追加・編集し、[保存]ボタンでローカルJSONへ書き込み→GitHubへコミットします。")

    # ローカルファイルをロード
    link_mapping = load_link_mapping()

    if not link_mapping:
        st.info("まだマッピングがありません。フォームから追加してください。")

    # 既存項目の表示・編集・削除
    # キーワードkwとURLurlを編集できるようにし、「削除」ボタンも配置
    for kw, url in list(link_mapping.items()):
        col1, col2, col3 = st.columns([3, 5, 1])

        # 入力欄（stripで前後空白除去しておくと混乱を防ぎやすい）
        new_kw = col1.text_input("キーワード", value=kw, key=f"kw_{kw}").strip()
        new_url = col2.text_input("URL", value=url, key=f"url_{kw}").strip()

        # 削除ボタン
        if col3.button("削除", key=f"delete_{kw}"):
            # link_mapping から完全削除
            del link_mapping[kw]
            # ローカルファイル保存 → 再描画
            save_link_mapping_locally(link_mapping)
            st.success(f"削除しました: {kw}")
            st.rerun()

        # キーワードやURLが変更されたかどうかを検知
        # キーが変わった場合は一旦削除＋新規キーを追加
        if new_kw != kw:
            del link_mapping[kw]
            link_mapping[new_kw] = new_url
        elif new_url != url:
            link_mapping[kw] = new_url

    # 新規追加フォーム
    st.subheader("新規追加")
    input_kw = st.text_input("新しいキーワード", key="new_kw").strip()
    input_url = st.text_input("新しいURL", key="new_url").strip()

    # 追加ボタン
    if st.button("追加"):
        if input_kw and input_url:
            link_mapping[input_kw] = input_url
            # ローカル保存 → 再描画
            save_link_mapping_locally(link_mapping)
            st.success(f"追加しました: {input_kw} => {input_url}")
            st.rerun()
        else:
            st.warning("キーワードとURLを両方入力してください。")

    # 保存ボタン (最終的にGitHubへコミット)
    if st.button("保存"):
        # 1. ローカルファイルを更新
        save_link_mapping_locally(link_mapping)
        st.success("ローカルJSONファイルを更新しました")

        # 2. GitHubコミット
        mapping_json_str = json.dumps(link_mapping, ensure_ascii=False, indent=2)
        commit_to_github(mapping_json_str)

if __name__ == "__main__":
    main()
