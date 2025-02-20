#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
import json
import os

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

ARTICLES_JSON_PATH = os.path.join("data", "articles.json")

# 記事をいくつ見つけたら終了するか
CRAWL_LIMIT = 10
# 連番をどこまで試すか（大きすぎると負荷が高いので注意）
MAX_ID = 30000

def save_json(data, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def fetch_title(url: str) -> str:
    """
    GETして200ならtitleを返し、それ以外は空文字を返す。
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            title_tag = soup.find("title")
            return title_tag.get_text(strip=True) if title_tag else "(No Title)"
        else:
            return ""
    except Exception as e:
        print(f"[ERROR] {url} -> {e}")
        return ""

def main():
    print("=== Start enumerating /media/column/<id> for up to 10 articles ===")
    articles = []
    found_count = 0

    for i in range(1, MAX_ID+1):
        if found_count >= CRAWL_LIMIT:
            break

        url = f"https://good-apps.jp/media/column/{i}"
        title = fetch_title(url)
        if title:
            # title が空でなければ 200 だったとみなす
            articles.append({
                "url": url,
                "title": title
            })
            print(f"[OK] {url} -> '{title}'")
            found_count += 1

    print(f"=== Found {len(articles)} articles ===")

    # 取得したarticlesを保存
    save_json(articles, ARTICLES_JSON_PATH)
    print(f"[INFO] Saved to {ARTICLES_JSON_PATH}")

if __name__ == "__main__":
    main()
