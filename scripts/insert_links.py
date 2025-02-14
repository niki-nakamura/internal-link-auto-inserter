import os
import json
import requests
import re

def load_link_mapping(path='data/linkMapping.json'):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_post_content(post_id, wp_url, wp_username, wp_password):
    response = requests.get(
        f"{wp_url}/wp-json/wp/v2/posts/{post_id}",
        auth=(wp_username, wp_password)
    )
    data = response.json()
    # もし投稿が見つからないときなどエラーの場合は適宜対処
    return data.get('content', {}).get('rendered', '')

def insert_links_to_content(content, link_mapping, max_links_per_post=1):
    links_added = 0

    for keyword, url in link_mapping.items():
        if links_added >= max_links_per_post:
            break

        pattern = rf'(?<!<a[^>]*>)(?P<kw>{re.escape(keyword)})(?![^<]*<\/a>)'

        def replacement(match):
            nonlocal links_added
            if links_added < max_links_per_post:
                links_added += 1
                return f'<a href="{url}">{match.group("kw")}</a>'
            else:
                return match.group("kw")

        updated_content = re.sub(pattern, replacement, content, count=1)

        if links_added > 0:
            # 1回置換があったら、すぐ返す(1記事1リンクが要件ならこれで十分)
            return updated_content

    # 置換が起きなかった場合は元のcontentを返す
    return content

def update_post_content(post_id, new_content, wp_url, wp_username, wp_password):
    payload = {
        'content': new_content
    }
    response = requests.post(
        f"{wp_url}/wp-json/wp/v2/posts/{post_id}",
        json=payload,
        auth=(wp_username, wp_password)
    )
    return response.status_code, response.text

def main():
    # 1. JSONファイルからキーワード→URLマッピング取得
    link_mapping = load_link_mapping('data/linkMapping.json')

    # 2. GitHub ActionsのSecretsからWP接続情報を取得
    wp_url = os.environ.get("WP_URL")
    wp_username = os.environ.get("WP_USERNAME")
    wp_password = os.environ.get("WP_PASSWORD")

    # 3. 対象の投稿ID
    post_ids = [24823, 24862]  # テストID

    # 4. それぞれの記事を取得→置換→更新
    for pid in post_ids:
        original_content = get_post_content(pid, wp_url, wp_username, wp_password)
        updated_content = insert_links_to_content(original_content, link_mapping)

        status, res_text = update_post_content(pid, updated_content, wp_url, wp_username, wp_password)
        print(f"Updated post {pid}: status={status}")
        # デバッグ用: print(res_text) などで詳細確認可

if __name__ == "__main__":
    main()
