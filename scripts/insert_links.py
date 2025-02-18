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
    return data.get('content', {}).get('rendered', '')

def insert_links_to_content(content, link_mapping, max_links_per_post=1):
    links_added = 0

    for keyword, url in link_mapping.items():
        if links_added >= max_links_per_post:
            break

        # <a>タグで囲まれた部分とキーワードをまとめて捕捉
        pattern = rf'(<a[^>]*>.*?</a>|{re.escape(keyword)})'

        def replacement(match):
            nonlocal links_added
            text = match.group(0)

            # 既に <a ...> で始まる場合は既存リンクなのでそのまま返す
            if text.startswith('<a'):
                return text

            # それ以外はキーワードだけがマッチした場合なので、リンクを付与
            if links_added < max_links_per_post:
                links_added += 1
                return f'<a href="{url}">{text}</a>'
            else:
                return text

        # 1回だけ置換してテキストを更新
        updated_content = re.sub(pattern, replacement, content, count=1)

        # 実際にリンクを1つ追加できたらbreakする
        if links_added > 0:
            return updated_content

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
    link_mapping = load_link_mapping('data/linkMapping.json')

    wp_url = os.environ.get("WP_URL")
    wp_username = os.environ.get("WP_USERNAME")
    wp_password = os.environ.get("WP_PASSWORD")

    # テスト用の投稿IDリスト
    post_ids = [5187]

    for pid in post_ids:
        original_content = get_post_content(pid, wp_url, wp_username, wp_password)
        updated_content = insert_links_to_content(original_content, link_mapping)

        status, res_text = update_post_content(pid, updated_content, wp_url, wp_username, wp_password)
        print(f"Updated post {pid}: status={status}")

if __name__ == "__main__":
    main()
