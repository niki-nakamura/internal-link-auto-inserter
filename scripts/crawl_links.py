#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry  # ← リトライ機能を使うために追加

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                  " (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

ARTICLES_JSON_PATH = os.path.join("data", "articles.json")
API_URL = "https://good-apps.jp/wp-json/wp/v2/posts"

def save_json(data, path: str):
    """JSONを指定パスに保存する"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def create_session_with_retries(
    total_retries=3,
    backoff_factor=1.0,
    status_forcelist=(500, 502, 503, 504),
    read_timeout=30,
):
    """
    requests用セッションを生成し、リトライとタイムアウトを設定する。
    """
    # リトライポリシーを定義
    retries = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        raise_on_status=False
    )
    # セッションを作成
    session = requests.Session()
    # HTTP(S)アダプタにリトライをセット
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    # タイムアウトを指定するためのラッパを定義
    # 例: session.get(url, timeout=(接続タイムアウト, 読み込みタイムアウト))
    session.request = lambda *args, **kwargs: requests.Session.request(
        session, *args, timeout=(5, read_timeout), **kwargs
    )
    return session

def fetch_all_wp_posts(base_url: str, per_page=50, max_pages=10):
    """
    WordPress REST APIから、複数ページにわたる投稿を全件取得する。
    per_page: 1ページあたりの取得数
    max_pages: 最大取得ページ数
    """
    # リトライ＆タイムアウト付きのセッションを用意
    session = create_session_with_retries(
        total_retries=3,    # 必要に応じて増やす
        backoff_factor=1.0, # リトライ時の待機時間増加係数
        read_timeout=30     # 読み込みタイムアウトを30秒に
    )

    all_posts = []
    page = 1
    while page <= max_pages:
        params = {
            "per_page": per_page,
            "page": page
        }

        try:
            resp = session.get(base_url, headers=HEADERS, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if not data:
                    break  # これ以上投稿がない
                all_posts.extend(data)
            else:
                print(f"[ERROR] Failed to fetch page={page}. HTTP {resp.status_code}")
                break
        except requests.exceptions.RequestException as e:
            # タイムアウト含む通信系エラー発生時
            print(f"[ERROR] Exception occurred while fetching page={page}: {e}")
            break

        page += 1

    return all_posts

def extract_column_articles(posts: list):
    """
    投稿リスト(posts)から、`link` に '/media/column/' を含むものだけ抽出し
    {'id': str, 'title': str, 'url': str} のリストに整形して返す。
    """
    extracted = []
    for p in posts:
        link = p.get("link", "")
        title_obj = p.get("title", {})
        title_text = title_obj.get("rendered", "")
        # '/media/column/' を含む投稿のみ対象
        if "/media/column/" in link:
            extracted.append({
                "id": str(p.get("id", "")),
                "title": title_text,
                "url": link
            })
    return extracted

def main():
    print("=== Start fetching WordPress posts via REST API ===")
    
    # 1) WordPress REST APIから投稿をすべて取得
    all_posts = fetch_all_wp_posts(API_URL, per_page=50, max_pages=10)
    print(f"Fetched {len(all_posts)} posts in total.")

    # 2) '/media/column/' を含む投稿のみ抽出
    column_posts = extract_column_articles(all_posts)
    print(f"Extracted {len(column_posts)} posts that match '/media/column/'.")

    # 3) data/articles.json に上書き保存
    save_json(column_posts, ARTICLES_JSON_PATH)
    print(f"Saved {len(column_posts)} posts into {ARTICLES_JSON_PATH}.")

if __name__ == "__main__":
    main()
