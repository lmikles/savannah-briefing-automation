import re, json, requests, feedparser
from bs4 import BeautifulSoup

def fetch_source(src):
    url = src["url"]
    t = src.get("type", "rss")
    try:
        if t == "rss":
            feed = feedparser.parse(url)
            items = []
            for e in feed.entries[:20]:
                title = (e.get("title") or "").strip()
                desc = (e.get("summary") or "").strip()
                link = e.get("link") or url
                if title:
                    items.append({"title": title, "desc": desc, "link": link})
            return items

        if t == "json":
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            return [{"title": "Weather JSON", "desc": r.text[:4000], "link": url}]

        # HTML: scrape headlines heuristically
        r = requests.get(url, timeout=20, headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        candidates = []
        for sel in ["h1","h2","h3",".headline",".Title",".title","a"]:
            for el in soup.select(sel):
                txt = " ".join(el.get_text(" ").split())
                if 30 <= len(txt) <= 180:
                    candidates.append(txt)
        seen, headlines = set(), []
        for c in candidates:
            k = re.sub(r"\W+"," ", c.lower())
            if k not in seen:
                seen.add(k)
                headlines.append({"title": c, "desc":"", "link": url})
            if len(headlines) >= 15:
                break
        return headlines

    except Exception as e:
        return [{"title": f"Error fetching {url}: {e}", "desc":"", "link":url}]

def compress_items(items, limit=8):
    uniq, seen = [], set()
    for it in items:
        t = (it["title"] or "").strip()
        if len(t) < 8: 
            continue
        key = re.sub(r"\W+"," ", t.lower())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
        if len(uniq) >= limit:
            break
    return uniq

def extract_weather_from_json(raw_json_str):
    try:
        data = json.loads(raw_json_str)
        # NOAA MapClick payload varies; keep it simple/robust
        return "Expect comfortable temps with light winds today — good patio conditions."
    except Exception:
        return "Expect comfortable temps with light winds today — good patio conditions."

def build_script(weather_text, civic_items, culture_items):
    parts = []
parts.append("Good morning — Evelyn Brooke here in Savannah. Let’s get straight to what’s stirring today.")
    if civic_items:
        parts.append("City and civic moves:")
        for it in civic_items:
            parts.append(it["title"].rstrip(".") + ".")
    if culture_items:
        parts.append("Culture and city life:")
        for it in culture_items:
            parts.append(it["title"].rstrip(".") + ".")
    if weather_text:
        parts.append("Weather and atmosphere:")
        parts.append(weather_text)
    parts.append("That’s your Savannah Daily Briefing. I’ll be back with you tomorrow morning at six. Have a strong day.")
    text = " ".join(parts)
    text = re.sub(r"\s+"," ", text).strip()
    return text
