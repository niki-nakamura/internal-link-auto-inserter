# manage_link_mapping.py
import streamlit as st
import json
import os

JSON_PATH = 'data/linkMapping.json'

def load_link_mapping(path=JSON_PATH):
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_link_mapping(mapping, path=JSON_PATH):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

def main():
    st.title("内部リンク マッピング管理ツール")

    st.write("キーワードとリンク先URLを追加・編集して、[保存]ボタンでJSONに書き込みます。")

    link_mapping = load_link_mapping()

    # テーブル形式で一覧表示
    if not link_mapping:
        st.info("現在、マッピングは空です。下のフォームから新規追加してください。")

    for kw, url in list(link_mapping.items()):
        col1, col2, col3 = st.columns([3, 5, 1])
        with col1:
            new_kw = st.text_input("キーワード", value=kw, key=f"kw_{kw}")
        with col2:
            new_url = st.text_input("URL", value=url, key=f"url_{kw}")
        with col3:
            if st.button("削除", key=f"delete_{kw}"):
                del link_mapping[kw]
                st.experimental_rerun()

        # キーが変更された場合（kwが書き換わった）→古いキーを消して新しいキーを追加
        if new_kw != kw:
            del link_mapping[kw]
            link_mapping[new_kw] = new_url
        elif new_url != url:
            link_mapping[kw] = new_url

    st.subheader("新規追加")
    new_keyword = st.text_input("新しいキーワードを入力", key="new_keyword")
    new_url = st.text_input("新しいURLを入力", key="new_url")
    if st.button("追加"):
        if new_keyword and new_url:
            link_mapping[new_keyword] = new_url
            st.success(f"追加しました: {new_keyword} => {new_url}")
            st.experimental_rerun()
        else:
            st.warning("キーワードとURLを両方入力してください。")

    if st.button("保存"):
        save_link_mapping(link_mapping)
        st.success("JSONファイルに保存しました。GitHubにコミットしてください。")

if __name__ == "__main__":
    main()
