#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import requests

# データファイルのパス
LINK_MAPPING_JSON = os.path.join("data", "linkMapping.json")
LINK_USAGE_JSON = os.path.join("data", "linkUsage.json")
ARTICLES_JSON = os.path.join("data", "articles.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                  " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

def load_json(path):
    if not os.path.exists(path):
        # articles.jsonは空リスト、他は空dictを返す
        if "articles" in path:
            return []
        else:
            return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def flatten_link_mapping(nested_map: dict) -> dict:
    """
    linkMapping.json が
      {
         "カテゴリA": {"キーワード1": "URL", "キーワード2": "URL2"},
         "カテゴリB": {"キーワード3": "URL3"}
      }
    のようになっている場合に、平坦化して
      {"キーワード1": "URL", "キーワード2": "URL2", "キーワード3": "URL3"}
    を返す
    """
    flat_map = {}
    for category, kw_dict in nested_map.items():
        flat_map.update(kw_dict)
    return flat_map

def main():
    # 1) JSONファイル読み込み
    articles = load_json(ARTICLES_JSON)         # 公開済み記事一覧
    link_mapping_nested = load_json(LINK_MAPPING_JSON)  # カテゴリ階層つきキーワード→URL
    link_mapping = flatten_link_mapping(link_mapping_nested)

    # 新しい linkUsage を作成する
    new_usage = {}
    for kw, url in link_mapping.items():
        new_usage[kw] = {
            "url": url,
            "articles_used_in": {}
        }

    # 2) 各記事URLをクロール
    for art in articles:
        art_id = art["id"]
        art_url = art["url"]
        try:
            resp = requests.get(art_url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                html = resp.text
            else:
                print(f"[WARN] Article {art_id} returned HTTP {resp.status_code}")
                continue
        except Exception as e:
            print(f"[ERROR] Failed to fetch {art_id}: {e}")
            continue

        # 3) HTML内に <a href="(リンクマッピングのURL)"> が何回登場するかをカウント
        #    ※href='...' や追加パラメータ付きなど厳密化したい場合は正規表現を利用
        for kw, usage_info in new_usage.items():
            target_url = usage_info["url"]
            count = html.count(f'href="{target_url}"')
            if count > 0:
                usage_info["articles_used_in"][art_id] = count

    # 4) 結果を保存
    save_json(new_usage, LINK_USAGE_JSON)
    print(f"[INFO] linkUsage.json updated with {len(articles)} articles scanned.")


if __name__ == "__main__":
    main()
