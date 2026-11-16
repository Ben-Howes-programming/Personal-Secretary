"""
news.py
=======
Purpose : Headlines from the FT, BBC and Guardian RSS feeds, with each source's
          political lean attached, plus matching of headlines to your holdings.
Location: services/news.py
Used by : views/markets.py, views/home.py
Note    : Only headlines, summaries and links are read. Clicking a link opens the
          article in your browser, where your FT subscription applies. Add your
          personal myFT feed address as MYFT_RSS_URL in .env to include it.
Cache   : Each feed is fetched at most once every 20 minutes.
"""

import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime

import config
from database import database as db

FEED_TTL = 20 * 60
HEADERS = {"User-Agent": "Mozilla/5.0 (personal RSS reader)"}
ATOM = "{http://www.w3.org/2005/Atom}"


def strip_html(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def parse_feed(xml_text):
    """Parse RSS or Atom into [{title, link, summary, published_ts}]."""
    items = []
    root = ET.fromstring(xml_text)
    for node in root.iter("item"):                      # RSS
        stamp = None
        try:
            stamp = parsedate_to_datetime(node.findtext("pubDate") or "").timestamp()
        except (TypeError, ValueError):
            pass
        items.append({"title": strip_html(node.findtext("title")), "link": (node.findtext("link") or "").strip(),
                      "summary": strip_html(node.findtext("description"))[:280], "published_ts": stamp})
    for node in root.iter(f"{ATOM}entry"):              # Atom
        link = node.find(f"{ATOM}link")
        items.append({"title": strip_html(node.findtext(f"{ATOM}title")),
                      "link": link.get("href", "") if link is not None else "",
                      "summary": strip_html(node.findtext(f"{ATOM}summary"))[:280], "published_ts": None})
    return [item for item in items if item["title"]]


def fetch_feed(source, section, lean, url, force=False):
    key = f"news:{url}"
    if not force:
        cached = db.cache_get(key)
        if cached is not None:
            return cached
    try:
        import requests
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        items = parse_feed(response.content)
    except Exception:
        return db.cache_get(key, allow_stale=True) or []   # show the last copy if the feed is down
    for item in items:
        item.update(source=source, section=section, lean=lean)
    db.cache_set(key, items, FEED_TTL)
    return items


def get_news(sources=None, force=False):
    """Every configured feed merged, newest first, with duplicate links removed."""
    feeds = [feed for feed in config.NEWS_FEEDS if not sources or feed[0] in sources]
    with ThreadPoolExecutor(max_workers=6) as pool:
        batches = list(pool.map(lambda feed: fetch_feed(*feed, force=force), feeds))
    seen, merged = set(), []
    for batch in batches:
        for item in batch:
            if item["link"] not in seen:
                seen.add(item["link"])
                merged.append(item)
    merged.sort(key=lambda item: item.get("published_ts") or 0, reverse=True)
    return merged


def matching(items, keywords):
    """Headlines that mention any keyword (whole words, case-insensitive)."""
    words = [word.strip().lower() for word in keywords if word and word.strip()]
    if not words:
        return []
    pattern = re.compile(r"\b(" + "|".join(re.escape(word) for word in words) + r")\b", re.I)
    return [item for item in items if pattern.search(item["title"] + " " + item.get("summary", ""))]


def clear_cache():
    db.cache_clear("news:")
