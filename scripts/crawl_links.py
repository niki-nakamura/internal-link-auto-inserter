#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import os
from collections import deque

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

# クロール開始URL: column配下
ALLOWED_SOURCE_PREFIXES = [
    "https://good-apps.jp/media/column/"
]

BASE_DOMAIN = "good-apps.jp"
CRAWL_LIMIT = 10  # 10件だけで終了
ARTICLES_JSON_PATH = os.path.join("data", "articles.json")

def is_internal_link(url: str) -> bool:
    """good-apps.jp ドメインかどうかを判定"""
    parsed = urlparse(url)
    return (parsed.netloc == "" or parsed.netloc.endswith(BASE_DOMAIN))

def is_allowed_source(url: str) -> bool:
    """URLが /media/column/ を含むならクロール対象"""
    return any(url.startswith(prefix) for prefix in ALLOWED_SOURCE_PREFIXES)

def save_json(data, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def crawl_for_titles():
    """幅優先で /media/column/ をたどり、10件だけタイトル取得。"""
    visited = set()
    articles = []  # [{"url": "...", "title": "..."}]
    queue = deque(ALLOWED_SOURCE_PREFIXES)

    while queue and len(articles) < CRAWL_LIMIT:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        try:
            resp = requests.get(current, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                print(f"[SKIP] {current} returned status {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            title_tag = soup.find("title")
            page_title = title_tag.get_text(strip=True) if title_tag else "(No Title)"

            # 取得したURL & タイトルをarticlesへ追加
            articles.append({
                "url": current,
                "title": page_title
            })
            print(f"[OK] {current} -> '{page_title}'")

            # ページ内リンクを探索
            for a in soup.find_all("a", href=True):
                link = urljoin(current, a["href"])
                # #以下除外
                link = urlparse(link)._replace(fragment="").geturl()
                if is_internal_link(link) and is_allowed_source(link):
                    if link not in visited:
                        queue.append(link)

            # 10件に達したら終了
            if len(articles) >= CRAWL_LIMIT:
                print("[INFO] Reached 10 articles. Stopping crawl.")
                break

        except Exception as e:
            print(f"[ERROR] {current} -> {e}")

    return articles

def main():
    print("=== Start crawling for up to 10 articles under /media/column/ ===")
    results = crawl_for_titles()
    print(f"=== Found {len(results)} articles ===")

    # 重複を除去したければ下記のように実装。ここでは簡易的に通過順に並べるだけ
    # たとえば URL をキーに辞書でユニーク化するなど:
    # unique_map = {}
    # for r in results:
    #     unique_map[r["url"]] = r["title"]
    # final_list = [{"url":u, "title":t} for u,t in unique_map.items()]

    # 今回は重複除去せず results をそのまま書き込み
    save_json(results, ARTICLES_JSON_PATH)
    print(f"[INFO] Saved to {ARTICLES_JSON_PATH}")

if __name__ == "__main__":
    main()
