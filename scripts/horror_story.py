"""Write an original Hindi horror story with Gemini and publish it to Blogger."""
import json, os, random, sys, urllib.error, urllib.parse, urllib.request

BLOG_ID = os.environ.get("HORROR_BLOG_ID", "8701672830660739320")
HISTORY = os.path.join(os.path.dirname(__file__), "..", "stories", "history.json")
MODELS = [m for m in [os.environ.get("GEMINI_MODEL", "").strip(), "gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"] if m]
SETTINGS = ["पुरानी हवेली", "रात की आख़िरी ट्रेन", "गाँव का सूखा कुआँ", "बंद पड़ा हॉस्टल", "पहाड़ी सड़क का ढाबा", "श्मशान के पास का घर",
            "पुराना सरकारी अस्पताल", "शादी वाला घर", "जंगल का रेस्ट हाउस", "किराये का नया फ़्लैट", "स्कूल की लाइब्रेरी", "नदी किनारे का मंदिर",
            "हाईवे की सुनसान रात", "पुरानी हवेली की तस्वीर", "दादी का संदूक", "रेलवे का पुराना क्वार्टर", "खेत के बीच का बरगद", "बारिश वाली रात की टैक्सी"]


def http_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data, headers or {}, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{e.code} {e.read().decode()[:400]}")


def write_story(past_titles):
    setting = random.choice(SETTINGS)
    prompt = (
        "तुम एक हिंदी हॉरर कहानीकार हो। एक बिल्कुल नई, मौलिक (original) हिंदी डरावनी कहानी लिखो, देवनागरी में।\n"
        f"कहानी की जगह/थीम: {setting}।\n"
        "शर्तें: 900-1300 शब्द; भारतीय माहौल; रहस्य और धीरे-धीरे बढ़ता डर; ज़्यादा खून-खराबा नहीं; बच्चों से जुड़ी हिंसा नहीं; "
        "किसी असली व्यक्ति, जगह के दावे या मौजूदा किताब/फ़िल्म की कॉपी नहीं; अंत चौंकाने वाला हो।\n"
        "इन शीर्षकों से अलग कहानी हो: " + "; ".join(past_titles[-40:]) + "\n"
        'सिर्फ़ JSON लौटाओ: {"title": "...", "summary": "1-2 लाइन", "paragraphs": ["...", "..."], "labels": ["...","..."]}'
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 1.0, "responseMimeType": "application/json"},
    }).encode()
    last = None
    for model in MODELS:
        try:
            res = http_json(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", body,
                            {"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"].strip()})
            text = res["candidates"][0]["content"]["parts"][0]["text"]
            story = json.loads(text)
            if story.get("title") and len(story.get("paragraphs", [])) >= 5:
                print("Model used:", model)
                return story
            last = "story too short"
        except Exception as e:  # try next model
            last = f"{model}: {e}"
            print("Gemini attempt failed ->", last)
    sys.exit(f"Could not generate story: {last}")


def access_token():
    data = urllib.parse.urlencode({
        "client_id": os.environ["GOOGLE_CLIENT_ID"].strip(),
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"].strip(),
        "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"].strip(),
        "grant_type": "refresh_token",
    }).encode()
    return http_json("https://oauth2.googleapis.com/token", data)["access_token"]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main():
    history = json.load(open(HISTORY, encoding="utf-8")) if os.path.exists(HISTORY) else []
    story = write_story([h["title"] for h in history])
    html = [f'<p><em>{esc(story.get("summary", ""))}</em></p>']
    html += [f"<p>{esc(p)}</p>" for p in story["paragraphs"]]
    html.append('<p style="font-size:13px;color:#777"><em>यह कहानी पूरी तरह काल्पनिक है। इसके पात्र, जगहें और घटनाएँ किसी असली व्यक्ति या घटना से जुड़ी नहीं हैं।</em></p>')
    labels = list(dict.fromkeys(["Hindi Horror Story", "डरावनी कहानी"] + story.get("labels", [])[:3]))
    draft = os.environ.get("DRAFT", "false").lower() == "true"
    res = http_json(
        f"https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts/?isDraft={'true' if draft else 'false'}",
        json.dumps({"kind": "blogger#post", "title": story["title"], "content": "\n".join(html), "labels": labels}).encode(),
        {"Authorization": "Bearer " + access_token(), "Content-Type": "application/json"})
    print(("Draft created: " if draft else "Published: ") + res.get("url", res.get("id", "")))
    if not draft:
        history.append({"title": story["title"], "url": res.get("url")})
        os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
        json.dump(history, open(HISTORY, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
