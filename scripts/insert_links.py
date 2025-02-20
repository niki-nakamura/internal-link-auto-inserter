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
    """
    差し込みたいキーワードとリンク先(URL)を対応させたJSONをロード
    {
      "キーワードA": "https://example.com",
      "キーワードB": "https://example.org",
      ...
    }
    """
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_post_raw_content(post_id, wp_url, wp_username, wp_password):
    """
    ブロックコメント（<!-- wp:xxx -->）含む “raw” な本文を取得。
    ?context=edit を付けることで raw コンテンツを取れる。
    """
    headers = get_auth_headers(wp_username, wp_password)
    response = requests.get(
        f"{wp_url}/wp-json/wp/v2/posts/{post_id}?context=edit",
        headers=headers
    )
    print(f"get_post_content for {post_id}, status_code={response.status_code}")
    data = response.json()

    # 認証不足や権限が無い場合は 'raw' が取れない場合もある
    raw_content = data.get('content', {}).get('raw', '')
    return raw_content

def insert_links_to_content(content, link_mapping, max_links_per_post=1):
    """
    ・すでにリンク化されている箇所は上書きしない
    ・max_links_per_post 回だけリンクを挿入したら打ち切り（デフォルト1回）
    ・Post Snippets ブロックなど、ショートコード部分は避けたい場合は簡易的に除外する例も併記
    """
    links_added = 0

    # もしショートコードや特定ブロックは置換対象外にしたい場合の例:
    # 1) 一時的にショートコードを退避
    #    （厳密にはブロックコメントやHTMLタグ単位など、必要に応じて拡張）
    #    ここではシンプルに "[xxx ...]" ～ "]" の正規表現で除外。
    #    実プロジェクトでは自前で解析ロジックを強化してください。
    shortcode_pattern = r'(\[.*?\])'
    shortcodes = []
    def shortcode_replacer(m):
        shortcodes.append(m.group(0))
        return f"__SHORTCODE_{len(shortcodes)-1}__"

    content = re.sub(shortcode_pattern, shortcode_replacer, content)

    for keyword, url in link_mapping.items():
        if links_added >= max_links_per_post:
            break

        # 既にリンクがついている箇所は置換しないためのパターン
        #   <a ...>...</a>  または キーワード (キーワード自身をエスケープ)
        pattern = rf'(<a[^>]*>.*?</a>|{re.escape(keyword)})'

        def replacement(match):
            nonlocal links_added
            text = match.group(0)
            # 既にリンクタグ部分ならスルー
            if text.lower().startswith('<a'):
                return text

            # まだリンク挿入数が上限未満であれば差し込む
            if links_added < max_links_per_post:
                links_added += 1
                return f'<a href="{url}">{text}</a>'
            else:
                return text

        updated_content = re.sub(pattern, replacement, content, count=1)
        # 置換が行われた場合(links_addedが増えたら) contentを更新
        if links_added > 0:
            content = updated_content

    # 2) ショートコードを元に戻す
    def shortcode_restore(m):
        # m.group(1) には __SHORTCODE_xxx__ が入る
        index = int(m.group(1).split('_')[-1])
        return shortcodes[index]

    content = re.sub(r'__SHORTCODE_(\d+)__', shortcode_restore, content)

    return content

def update_post_content(post_id, new_content, wp_url, wp_username, wp_password):
    """
    raw な文字列をそのまま content に渡すことで、ブロック崩れを防ぐ
    """
    headers = get_auth_headers(wp_username, wp_password)
    payload = {
        'content': new_content
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
