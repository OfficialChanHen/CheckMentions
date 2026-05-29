"""News signals (Layers 4 & 5).

Two questions, answered from news:
  * Layer 4 -- has Trump been mentioned alongside the company lately? (timing)
  * Layer 5 -- has the company's CEO publicly praised / aligned with Trump?

Prefers NewsAPI.org when NEWSAPI_KEY is set (faster, structured), and always
keeps the free, no-key GDELT feed as a fallback / supplement.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List

from . import config, http

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
NEWSAPI_URL = "https://newsapi.org/v2/everything"


def _has_praise(text: str) -> bool:
    low = (text or "").lower()
    return any(term in low for term in config.PRAISE_TERMS)


def _gdelt_articles(query: str, days: int, maxrecords: int = 40) -> List[Dict]:
    data = http.get_json(
        GDELT_URL,
        params={
            "query": query,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": maxrecords,
            "timespan": f"{days}days",
            "sort": "DateDesc",
        },
    )
    if not isinstance(data, dict):
        return []
    return data.get("articles", []) or []


def _newsapi_articles(query: str, days: int, key: str, page_size: int = 40) -> List[Dict]:
    frm = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    data = http.get_json(
        NEWSAPI_URL,
        params={
            "q": query,
            "from": frm,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": page_size,
            "apiKey": key,
        },
    )
    if not isinstance(data, dict) or data.get("status") != "ok":
        return []
    out = []
    for a in data.get("articles", []) or []:
        out.append({
            "title": a.get("title") or "",
            "url": a.get("url") or "",
            "seendate": a.get("publishedAt") or "",
            "domain": ((a.get("source") or {}).get("name")) or "",
        })
    return out


def news_signal(company: config.Company) -> Dict:
    """Return {trump_mentions, exec_praise_hits, headlines:[...]} for a company.

    `headlines` is a small sample of the most relevant article dicts for the
    report (title + url).
    """
    days = config.NEWS_LOOKBACK_DAYS
    newsapi_key = config.env_key(config.KEY_NEWSAPI)

    # One combined co-mention query: articles about Trump that also name the
    # company or its CEO. Phrase-quoted to avoid generic matches.
    if newsapi_key:
        query = f'"{company.name}" AND Trump'
        articles = _newsapi_articles(query, days, newsapi_key)
        # CEO-focused pass for the alignment layer.
        ceo_articles = _newsapi_articles(f'"{company.ceo}" AND Trump', days, newsapi_key)
    else:
        # GDELT query grammar: space = AND, OR uppercase, quotes for phrases.
        query = f'("{company.name}" OR "{company.ceo}") Trump'
        articles = _gdelt_articles(query, days)
        ceo_articles = [a for a in articles
                        if company.ceo.split()[-1].lower() in (a.get("title") or "").lower()]

    trump_mentions = len(articles)

    # Executive alignment: a headline that names the CEO *and* carries a
    # praise / backing / investment verb.
    praise_hits = 0
    praise_samples: List[Dict] = []
    ceo_last = company.ceo.split()[-1].lower()
    for a in ceo_articles:
        title = a.get("title") or ""
        if ceo_last in title.lower() and _has_praise(title):
            praise_hits += 1
            if len(praise_samples) < 3:
                praise_samples.append(a)

    headlines = (praise_samples + articles)[:4]
    return {
        "trump_mentions": trump_mentions,
        "exec_praise_hits": praise_hits,
        "headlines": [
            {"title": h.get("title", ""), "url": h.get("url", ""), "date": h.get("seendate", "")}
            for h in headlines if h.get("title")
        ],
    }
