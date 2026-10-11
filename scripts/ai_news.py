"""Pick a fresh trending AI story from news RSS feeds, have Gemini write an original
explainer article (with source credit), and publish it to Blogger."""
import html, json, os, re, sys, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

BLOG_ID = os.environ.get("AI_BLOG_ID", "5116321310790249819")
HISTORY = os.path.join(os.path.dirname(__file__), "..", "stories", "ai_history.json")
MODELS = [m for m in [os.environ.get("GEMINI_MODEL", "").strip(), "gemini-flash-latest", "gemini-2.5-flash"] if m]
FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "https://venturebeat.com/category/ai/feed/",
    "https://news.google.com/rss/search?q=%22AI+tool%22+OR+%22AI+model%22+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
]
UA = {"User-Agent": "Mozilla/5.0 (AI Tools Daily feed reader)"}


def http(url, data=None, headers=None, as_json=True):
    req = urllib.request.Request(url, data, {**UA, **(headers or {})}, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if as_json else raw
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{e.code} {e.read().decode(errors='ignore')[:300]}")


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def fetch_items():
    items = []
    for url in FEEDS:
        try:
            root = ET.fromstring(http(url, as_json=False))
        except Exception as e:
            print("Feed failed:", url, e)
            continue
        for it in root.iter():
            tag = it.tag.split("}")[-1]
            if tag not in ("item", "entry"):
                continue
            get = lambda name: next((c for c in it if c.tag.split("}")[-1] == name), None)
            title = clean(getattr(get("title"), "text", ""))
            link_el = get("link")
            link = (link_el.get("href") if link_el is not None and link_el.get("href") else getattr(link_el, "text", "")) or ""
            desc = clean(getattr(get("description"), "text", "") or getattr(get("summary"), "text", "") or getattr(get("content"), "text", ""))
            if title and link:
                items.append({"title": title, "link": link.strip(), "summary": desc[:1500], "feed": url})
    return items


def pick(items, history):
    seen_links = {h["source"] for h in history}
    seen_titles = [h["source_title"].lower() for h in history[-200:]]
    for it in items:
        t = it["title"].lower()
        if it["link"] in seen_links:
            continue
        words = set(re.findall(r"[a-z0-9]{4,}", t))
        if any(len(words & set(re.findall(r"[a-z0-9]{4,}", s))) >= 4 for s in seen_titles):
            continue  # same story from another outlet
        return it
    return None


def write_article(item):
    prompt = f"""You are a writer for "AI Tools Daily", an English blog for Indian readers about AI news and AI tools.
Write an ORIGINAL article (650-900 words) about this news item. Use ONLY the facts given below for any specific claims
(names, numbers, dates, features). You may add general background knowledge about AI that is widely known, but do NOT invent
quotes, statistics, prices, release dates or features. If details are missing, say they are not yet confirmed.
Do not copy sentences from the source; explain in your own simple words.

Structure: a catchy but honest headline; a 2-sentence intro; sections with <h2> headings such as "What happened",
"Why it matters", "How you can use it / Who it is for", "Things to keep in mind"; a short conclusion.
Output plain HTML using only <h2>, <p>, <ul>, <li>, <strong>.

NEWS ITEM
Title: {item['title']}
Summary: {item['summary']}

Return JSON: {{"title": "...", "meta_description": "max 150 chars", "html": "...", "labels": ["AI News", "..."]}}"""
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"}}).encode()
    last = None
    for model in MODELS:
        try:
            res = http(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", body,
                       {"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"].strip()})
            art = json.loads(res["candidates"][0]["content"]["parts"][0]["text"])
            if art.get("title") and len(art.get("html", "")) > 1500:
                print("Model used:", model)
                return art
            last = "article too short"
        except Exception as e:
            last = f"{model}: {e}"
            print("Gemini attempt failed ->", last)
    sys.exit(f"Could not write article: {last}")


def sanitize(h):
    h = re.sub(r"(?is)<(script|style|iframe)[^>]*>.*?</\1>", "", h)
    return re.sub(r"(?i)\son\w+=\"[^\"]*\"", "", h)


def access_token():
    data = urllib.parse.urlencode({
        "client_id": os.environ["GOOGLE_CLIENT_ID"].strip(),
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"].strip(),
        "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"].strip(),
        "grant_type": "refresh_token",
    }).encode()
    return http("https://oauth2.googleapis.com/token", data)["access_token"]


def main():
    history = json.load(open(HISTORY, encoding="utf-8")) if os.path.exists(HISTORY) else []
    items = fetch_items()
    print("Feed items:", len(items))
    item = pick(items, history)
    if not item:
        print("No new AI story found - skipping this run.")
        return
    print("Picked:", item["title"])
    art = write_article(item)
    src = html.escape(item["link"], quote=True)
    content = (sanitize(art["html"]) +
               f'\n<p style="font-size:14px;color:#666"><em>Source: <a href="{src}" target="_blank" rel="nofollow noopener">'
               f'{html.escape(item["title"])}</a>. This article is an original summary and explainer written for AI Tools Daily.</em></p>')
    labels = list(dict.fromkeys(["AI News"] + [l for l in art.get("labels", []) if isinstance(l, str)][:4]))
    draft = os.environ.get("DRAFT", "false").lower() == "true"
    res = http(f"https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts/?isDraft={'true' if draft else 'false'}",
               json.dumps({"kind": "blogger#post", "title": art["title"], "content": content, "labels": labels}).encode(),
               {"Authorization": "Bearer " + access_token(), "Content-Type": "application/json"})
    print(("Draft created: " if draft else "Published: ") + res.get("url", res.get("id", "")))
    if not draft:
        history.append({"title": art["title"], "url": res.get("url"), "source": item["link"], "source_title": item["title"]})
        os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
        json.dump(history, open(HISTORY, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
