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

# クロール開始URL: column 配下を対象とする
ALLOWED_SOURCE_PREFIXES = [
    "https://good-apps.jp/media/column/"
]

BASE_DOMAIN = "good-apps.jp"  # 内部リンク判定用
CRAWL_LIMIT = 1000            # クロールする最大ページ数など

ARTICLES_JSON_PATH = os.path.join("data", "articles.json")

def is_internal_link(url: str) -> bool:
    """good-apps.jp ドメイン内かどうかを判定"""
    parsed = urlparse(url)
    return (parsed.netloc == "" or parsed.netloc.endswith(BASE_DOMAIN))

def is_allowed_source(url: str) -> bool:
    """クロール対象とするURLかどうかを判定（/media/column/ を含むか）"""
    return any(url.startswith(prefix) for prefix in ALLOWED_SOURCE_PREFIXES)

def save_json(data, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def crawl_for_titles():
    """
    BFS形式で /media/column/ 以下をたどり、各ページのURLと<title>を取得。
    結果を articles.json に書き出す。
    """
    visited = set()
    articles = []  # [{ "url": "...", "title": "..." }, ...]

    queue = deque(ALLOWED_SOURCE_PREFIXES)
    while queue and len(visited) < CRAWL_LIMIT:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        try:
            resp = requests.get(current, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                # 200でなければスキップ
                print(f"[SKIP] {current} returned status {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            title_tag = soup.find("title")
            page_title = title_tag.get_text(strip=True) if title_tag else "(No Title)"

            print(f"[OK] {current} -> '{page_title}'")

            # 記事一覧に追加 (URL重複チェックしたい場合はここで検索)
            articles.append({
                "url": current,
                "title": page_title
            })

            # ページ内のリンクを探す
            for a in soup.find_all("a", href=True):
                link = urljoin(current, a["href"])
                # #以下のフラグメントは除外
                link = urlparse(link)._replace(fragment="").geturl()

                # 内部リンクかつ /media/column/ 以下であればキューへ
                if is_internal_link(link) and is_allowed_source(link):
                    if link not in visited:
                        queue.append(link)

        except Exception as e:
            print(f"[ERROR] {current} -> {e}")

    return articles

def main():
    print("=== Start crawling for titles under /media/column/ ===")
    articles = crawl_for_titles()
    print(f"=== Found {len(articles)} articles ===")

    # 重複URLの除去・整形など必要ならここで行う
    # 例：URLをキーにした辞書でユニーク化
    unique_map = {}
    for art in articles:
        unique_map[art["url"]] = art["title"]
    final_list = [{"url": u, "title": t} for u, t in unique_map.items()]

    print(f"=== After dedup, {len(final_list)} unique articles ===")

    # JSONへ書き込み
    save_json(final_list, ARTICLES_JSON_PATH)
    print(f"[INFO] Saved to {ARTICLES_JSON_PATH}")

if __name__ == "__main__":
    main()
