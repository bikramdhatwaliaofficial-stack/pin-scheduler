"""Publish the next unposted item from posts/queue.json to Blogger."""
import json, os, sys, urllib.parse, urllib.request

BLOG_ID = os.environ.get("BLOG_ID", "7685699494231753472")
QUEUE = os.path.join(os.path.dirname(__file__), "..", "posts", "queue.json")
DRAFT = os.environ.get("DRAFT", "false").lower() == "true"


def access_token():
    data = urllib.parse.urlencode({
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    with urllib.request.urlopen("https://oauth2.googleapis.com/token", data) as r:
        return json.load(r)["access_token"]


def main():
    with open(QUEUE, encoding="utf-8") as f:
        queue = json.load(f)
    item = next((p for p in queue if not p.get("posted")), None)
    if item is None:
        print("Queue empty - nothing to post. Add more posts to posts/queue.json")
        return
    body = json.dumps({
        "kind": "blogger#post",
        "title": item["title"],
        "content": item["content"],
        "labels": item.get("labels", []),
    }).encode()
    url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts/?isDraft={'true' if DRAFT else 'false'}"
    req = urllib.request.Request(url, body, method="POST", headers={
        "Authorization": "Bearer " + access_token(),
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        print("Blogger error:", e.code, e.read().decode()[:500])
        sys.exit(1)
    print(("Draft created: " if DRAFT else "Published: ") + res.get("url", res.get("id", "")))
    if not DRAFT:
        item["posted"] = True
        item["url"] = res.get("url")
        with open(QUEUE, "w", encoding="utf-8") as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
