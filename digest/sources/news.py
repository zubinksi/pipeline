"""News fetcher: a Google News RSS search per drug (catches company press
releases via the wire services) plus any extra RSS feeds in the watchlist.

Everything fetched here is untrusted text. It is only ever passed on as data.
"""
from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone
from time import struct_time
from calendar import timegm

import feedparser
import httpx

from .ctgov import mentions

GOOGLE_NEWS = "https://news.google.com/rss/search"


def _clean(text: str, limit: int = 300) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _published(entry) -> datetime | None:
    st: struct_time | None = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(timegm(st), tz=timezone.utc) if st else None


def item_id(title: str) -> str:
    norm = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    return "news-" + hashlib.sha1(norm.encode()).hexdigest()[:12]


def parse_feed(content: bytes, feed_name: str) -> list[dict]:
    parsed = feedparser.parse(content)
    out = []
    for e in parsed.entries:
        title = _clean(e.get("title", ""), 250)
        outlet = feed_name
        src = e.get("source")
        if src and src.get("title"):
            outlet = src["title"]
            # Google News titles look like "Headline - Outlet"
            if title.endswith(" - " + outlet):
                title = title[: -len(outlet) - 3]
        link = e.get("link", "")
        if not title or not link:
            continue
        out.append({
            "id": item_id(title),
            "title": title,
            "summary": _clean(e.get("summary", "")),
            "outlet": outlet,
            "link": link,
            "published": (_published(e) or datetime.now(timezone.utc)).isoformat(),
        })
    return out


def fetch_google_news(client: httpx.Client, terms: list[str]) -> list[dict]:
    q = " OR ".join(f'"{t}"' for t in terms)
    r = client.get(GOOGLE_NEWS, params={"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    r.raise_for_status()
    return parse_feed(r.content, "Google News")


def fetch_feed(client: httpx.Client, url: str, name: str) -> list[dict]:
    r = client.get(url)
    r.raise_for_status()
    return parse_feed(r.content, name)


def match_drug(item: dict, drugs: list[dict], terms_for) -> str | None:
    """First watchlist drug named in the item's title (or summary)."""
    for d in drugs:
        if mentions(item["title"], terms_for(d)):
            return d["id"]
    for d in drugs:
        if mentions(item["summary"], terms_for(d)):
            return d["id"]
    return None
