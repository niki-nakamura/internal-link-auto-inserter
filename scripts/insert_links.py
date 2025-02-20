import os
import json
import requests
import re
import base64

def get_auth_headers(username, password):
    token = base64.b64encode(f"{username}:{password}".encode()).decode('utf-8')
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }

def load_link_mapping(path='data/linkMapping.json'):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_post_raw_content(post_id, wp_url, wp_username, wp_password):
    """
    ブロックコメント（<!-- wp:xxx -->）を含んだ raw データを取得するため、
    ?context=edit を付与して認証付きリクエストする。
    """
    headers = get_auth_headers(wp_username, wp_password)
    response = requests.get(
        f"{wp_url}/wp-json/wp/v2/posts/{post_id}?context=edit",  # ← context=edit
        headers=headers
    )
    print(f"get_post_content for {post_id}, status_code={response.status_code}")
    data = response.json()

    # 認証不足や権限がないと 'raw' が返らない場合もある
    raw_content = data.get('content', {}).get('raw', '')
    return raw_content

def insert_links_to_content(content, link_mapping, max_links_per_post=1):
    links_added = 0

    for keyword, url in link_mapping.items():
        if links_added >= max_links_per_post:
            break

        # 既にリンク化されている箇所を上書きしないためのパターン
        pattern = rf'(<a[^>]*>.*?</a>|{re.escape(keyword)})'

        def replacement(match):
            nonlocal links_added
            text = match.group(0)

            # 既にリンクがついている部分はそのまま
            if text.startswith('<a'):
                return text

            # まだ上限未満ならリンクを付与
            if links_added < max_links_per_post:
                links_added += 1
                return f'<a href="{url}">{text}</a>'
            else:
                return text

        updated_content = re.sub(pattern, replacement, content, count=1)

        # 1箇所でもリンクを挿入したら content を更新して次のキーワードへ
        if links_added > 0:
            content = updated_content

    return content

def update_post_content(post_id, new_content, wp_url, wp_username, wp_password):
    """
    WP の REST API で「content」に raw の文字列を渡すと、
    ブロックコメントを含んだまま更新される。
    """
    headers = get_auth_headers(wp_username, wp_password)
    payload = {
        'content': new_content  # rawな内容をそのまま渡す
    }
    response = requests.post(
        f"{wp_url}/wp-json/wp/v2/posts/{post_id}",
        json=payload,
        headers=headers
    )
    print(f"update_post_content for {post_id}, status_code={response.status_code}")
    return response.status_code, response.text

def main():
    link_mapping = load_link_mapping('data/linkMapping.json')

    wp_url = os.environ.get("WP_URL")
    wp_username = os.environ.get("WP_USERNAME")
    wp_password = os.environ.get("WP_PASSWORD")

    # 実際には更新対象の投稿IDを取得してループ
    post_ids = [5187]

    for pid in post_ids:
        original_content = get_post_raw_content(pid, wp_url, wp_username, wp_password)
        updated_content = insert_links_to_content(original_content, link_mapping)

        status, res_text = update_post_content(pid, updated_content, wp_url, wp_username, wp_password)
        print(f"Updated post {pid}: status={status}")
        print(f"response text: {res_text}")

if __name__ == "__main__":
    main()
