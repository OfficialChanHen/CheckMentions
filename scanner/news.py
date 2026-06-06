"""News signals (Layers 4 & 5).

Two questions, answered from news:
  * Layer 4 -- has Trump been mentioned alongside the company lately? (timing)
  * Layer 5 -- has the company's CEO publicly praised / aligned with Trump?

Prefers NewsAPI.org when NEWSAPI_KEY is set (faster, structured), and always
keeps the free, no-key GDELT feed as a fallback / supplement.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional

from . import config, http

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
NEWSAPI_URL = "https://newsapi.org/v2/everything"
TRUTH_SOCIAL_RSS = "https://truthsocial.com/@realDonaldTrump.rss"

# Words that indicate a headline is *about a company*, not a person who happens
# to share a surname with one (e.g. "Kane Parsons" the film director vs Parsons
# the defense contractor).
COMPANY_CONTEXT_TERMS = {
    "stock", "stocks", "shares", "share", "ceo", "cfo", "coo",
    "earnings", "revenue", "profit", "loss", "losses",
    "contract", "deal", "acquisition", "merger", "ipo", "stake", "buyback",
    "corp", "corporation", "inc", "ltd", "holdings", "company",
    "billion", "million", "quarter", "fiscal", "guidance",
    "investor", "investors", "analyst", "analysts", "shareholders",
    "rally", "surge", "plunge", "jump", "drop", "soar", "tumble",
    "upgrade", "downgrade", "target", "pricetarget",
    "trump", "white house", "pentagon", "biden", "tariff", "tariffs",
    "defense", "chip", "chips", "semiconductor", "fab", "factory", "plant",
    "ai", "cloud", "data center", "server", "missile", "fighter", "drone",
    "award", "awarded", "wins", "won", "contract",
    "boycott", "lawsuit", "antitrust", "sec",
}

# Verbs Trump's posts/headlines use when he positively names a company.
PRAISE_VERBS = [
    "praises", "praised", "backs", "backed", "endorses", "endorsed",
    "thanks", "thanked", "thanking",
    "hails", "hailed", "lauds", "lauded",
    "commends", "commended", "supports", "supported",
    "celebrates", "celebrated", "applauds", "applauded",
    "loves", "great", "fantastic",
]

# "Trump <verb> <Entity>" extractor: pulls the capitalized phrase that follows
# a praise verb. Used to discover untracked companies Trump has praised.
# Captures consecutive capitalized words (e.g. "Lockheed Martin"); stops at the
# first lowercase token so trailing context like "for chip move" is dropped.
_PRAISE_RE = re.compile(
    r"\bTrump\s+(?:" + "|".join(re.escape(v) for v in PRAISE_VERBS) + r")\s+"
    r"([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,4})"
)

_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")


def _has_praise(text: str) -> bool:
    low = (text or "").lower()
    return any(term in low for term in config.PRAISE_TERMS)


# Truth Social RSS is the SAME feed regardless of company. The scanner used to
# hit it once per company in UNIVERSE (47 fetches × ~2s throttle = ~90s wasted
# per run); a single in-process cache reuses the parsed XML across all callers.
_TRUTH_SOCIAL_CACHE_FILLED: bool = False
_TRUTH_SOCIAL_ROOT: Optional["ET.Element"] = None


def _truth_social_root() -> Optional["ET.Element"]:
    """Fetch @realDonaldTrump's RSS once per process and cache the parsed root."""
    global _TRUTH_SOCIAL_CACHE_FILLED, _TRUTH_SOCIAL_ROOT
    if _TRUTH_SOCIAL_CACHE_FILLED:
        return _TRUTH_SOCIAL_ROOT
    _TRUTH_SOCIAL_CACHE_FILLED = True
    resp = http.get(TRUTH_SOCIAL_RSS)
    if resp is None or not resp.ok:
        return None
    try:
        _TRUTH_SOCIAL_ROOT = ET.fromstring(resp.text)
    except ET.ParseError:
        _TRUTH_SOCIAL_ROOT = None
    return _TRUTH_SOCIAL_ROOT


def _headline_about_company(title: str, company: config.Company) -> bool:
    """Is this headline title plausibly about *this* company?

    Defends against false positives like "Kane Parsons" (a film director) for
    Parsons the defense contractor, or "Apple Martin" for Apple Inc.

    Accepts the headline if any of:
      * the ticker appears as a cashtag ($TICKER) or in parens ((TICKER));
      * the CEO's full name appears in the title;
      * a distinctive multi-word alias (e.g. "Parsons Corporation") appears;
      * the canonical company name appears AND the title also carries a
        company-context term AND the only mentions of the name are not in the
        "[Capitalized first name] [CompanyName]" personal-name pattern.
    """
    if not title:
        return False
    title_norm = title.replace("’", "'")
    title_low = title_norm.lower()

    # Strong, unambiguous identifiers.
    tkr = company.ticker
    if f"${tkr.lower()}" in title_low or f"({tkr})" in title_norm:
        return True
    if company.ceo and company.ceo.lower() in title_low:
        return True
    for alias in company.aliases:
        if len(alias) > 6 and alias.lower() in title_low:
            return True

    name_low = company.name.lower()
    # Word-boundary match on the canonical name -- avoids "Intel" in "Intelligent".
    name_pat = re.compile(rf"\b{re.escape(name_low)}\b")
    name_hits = list(name_pat.finditer(title_low))
    if not name_hits:
        return False

    # Personal-name pattern: "[Capitalized first name] [CompanyName]" where the
    # prefix is not part of the CEO's own first name.
    ceo_first = company.ceo.split()[0].lower() if company.ceo else ""
    person_pat = re.compile(rf"\b([A-Z][a-z]+)\s+{re.escape(company.name)}\b")
    person_hits = [
        m for m in person_pat.finditer(title_norm)
        if m.group(1).lower() != ceo_first
    ]
    # If *every* mention of the company name is a personal-name pattern, reject.
    if person_hits and len(person_hits) >= len(name_hits):
        return False

    return any(term in title_low for term in COMPANY_CONTEXT_TERMS)


def _filter_headlines(arts: List[Dict], company: config.Company) -> List[Dict]:
    return [a for a in arts if _headline_about_company(a.get("title") or "", company)]


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

    # Disambiguate: drop articles whose title isn't actually about this company
    # (e.g. "Kane Parsons" the film director vs Parsons the defense contractor,
    # or articles where the company name only appears in the body, not the title).
    articles = _filter_headlines(articles, company)

    trump_mentions = len(articles)
    # Dual window: the 30d count picks up the broad story; the 7d count is the
    # momentum read (Trump mentions concentrating in the last week is the
    # "talk it up" phase ramping). Same fetch, no marginal API cost.
    cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
    trump_mentions_7d = 0
    for a in articles:
        raw = a.get("seendate") or ""
        try:
            # NewsAPI returns ISO-8601; GDELT returns YYYYMMDDTHHMMSSZ.
            if raw.endswith("Z") and "T" in raw and "-" not in raw:
                dt = datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            else:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            continue
        if dt >= cutoff_7d:
            trump_mentions_7d += 1

    # Executive alignment: a headline that names the CEO *and* carries a
    # praise / backing / investment verb.
    praise_hits = 0
    praise_samples: List[Dict] = []
    ceo_full = company.ceo.lower()
    for a in ceo_articles:
        title = a.get("title") or ""
        if ceo_full in title.lower() and _has_praise(title):
            praise_hits += 1
            if len(praise_samples) < 3:
                praise_samples.append(a)

    headlines = (praise_samples + articles)[:4]
    return {
        "trump_mentions": trump_mentions,
        "trump_mentions_7d": trump_mentions_7d,
        "exec_praise_hits": praise_hits,
        "headlines": [
            {"title": h.get("title", ""), "url": h.get("url", ""), "date": h.get("seendate", "")}
            for h in headlines if h.get("title")
        ],
    }


def truth_social_signal(company: config.Company) -> Dict:
    """Scan @realDonaldTrump's Truth Social RSS feed for posts mentioning the company.

    Returns truth_social_hits (count within the news lookback window) and a
    small sample of matching post titles for the report.  Falls back to zeros
    gracefully if the feed is unavailable.
    """
    root = _truth_social_root()
    if root is None:
        return {"truth_social_hits": 0, "truth_social_posts": []}

    cutoff = datetime.now(timezone.utc) - timedelta(days=config.NEWS_LOOKBACK_DAYS)
    # Distinctive identifiers: cashtag, ticker in parens, multi-word aliases,
    # the CEO's full name, and distinctive products / programs (e.g. "F-35",
    # "Ryzen", "Air Force One"). Trump frequently references a product without
    # naming the parent company, so the products list is load-bearing here.
    strong_terms = {f"${company.ticker.lower()}", f"({company.ticker})".lower()}
    for alias in company.aliases:
        if len(alias) > 6:
            strong_terms.add(alias.lower())
    if company.ceo:
        strong_terms.add(company.ceo.lower())
    for product in company.products:
        if len(product) >= 3:
            strong_terms.add(product.lower())
    name_low = company.name.lower()
    name_pat = re.compile(rf"\b{re.escape(name_low)}\b")
    # Personal-name pattern (FirstName + CompanyName) used to reject obvious
    # surname matches; Trump posts about people too.
    ceo_first = company.ceo.split()[0].lower() if company.ceo else ""
    person_pat = re.compile(rf"\b([A-Z][a-z]+)\s+{re.escape(company.name)}\b")

    hits = 0
    samples: List[Dict] = []

    for item in root.findall(".//item"):
        pub_raw = item.findtext("pubDate") or ""
        try:
            pub_dt = parsedate_to_datetime(pub_raw) if pub_raw else None
        except Exception:
            pub_dt = None
        if pub_dt is not None and pub_dt < cutoff:
            continue

        title = item.findtext("title") or ""
        desc = item.findtext("description") or ""
        content = title + " " + desc
        content_low = content.lower()

        matched = any(term in content_low for term in strong_terms)
        if not matched and name_pat.search(content_low):
            # Bare-name match on a Trump-authored post. Trump posts are short
            # and direct; if he names the company, he means the company. Skip
            # the heavier news-headline context requirement and only reject
            # obvious surname patterns ("Michael Dell" without other context).
            person_hits = [m for m in person_pat.finditer(content)
                           if m.group(1).lower() != ceo_first]
            name_hit_count = len(name_pat.findall(content_low))
            if person_hits and len(person_hits) >= name_hit_count:
                # Every mention is in a personal-name pattern -- skip.
                pass
            else:
                matched = True
        if matched:
            hits += 1
            if len(samples) < 3:
                link = item.findtext("link") or ""
                samples.append({"title": title, "url": link, "date": pub_raw})

    return {"truth_social_hits": hits, "truth_social_posts": samples}


# ---------------------------------------------------------------------------
# Global Trump positive-mention scan: surfaces companies (tracked OR untracked)
# that Trump has named approvingly in a recent Truth Social post or whose
# names appear in headlines of the form "Trump <praise verb> <Company>".
# ---------------------------------------------------------------------------

def _build_universe_index(universe: List[config.Company]) -> Dict[str, config.Company]:
    """Map lowercase name / alias / ticker / CEO name -> Company. Lookup helper
    for classifying free-text mentions as tracked or untracked."""
    idx: Dict[str, config.Company] = {}
    for c in universe:
        idx[c.name.lower()] = c
        idx[c.ticker.lower()] = c
        for a in c.aliases:
            idx[a.lower()] = c
        if c.ceo:
            idx[c.ceo.lower()] = c
    return idx


def _classify_mention(text: str, universe_idx: Dict[str, config.Company]
                      ) -> Optional[config.Company]:
    """Return the Company a free-text mention refers to, or None if untracked."""
    low = text.lower().strip()
    if not low:
        return None
    if low in universe_idx:
        return universe_idx[low]
    # Substring match against the longer keys first (e.g. "Apple Inc" beats "Apple").
    for key in sorted(universe_idx.keys(), key=len, reverse=True):
        if len(key) < 4:
            continue
        if re.search(rf"\b{re.escape(key)}\b", low):
            return universe_idx[key]
    return None


def _trump_news_articles(days: int, page_size: int = 60) -> List[Dict]:
    """Pull headlines likely to contain a Trump-says-X praise statement."""
    newsapi_key = config.env_key(config.KEY_NEWSAPI)
    # OR'd phrase queries work in both NewsAPI and GDELT.
    phrases = [f'"Trump {v}"' for v in
               ("praises", "backs", "endorses", "thanks", "hails", "lauds",
                "commends", "celebrates", "applauds")]
    query = " OR ".join(phrases)
    if newsapi_key:
        return _newsapi_articles(query, days, newsapi_key, page_size=page_size)
    return _gdelt_articles(query, days, maxrecords=page_size)


def trump_positive_mentions(universe: List[config.Company]) -> List[Dict]:
    """Return Trump's recent positive mentions of *any* company (tracked or not).

    Sources:
      * @realDonaldTrump Truth Social RSS — every post is Trump-authored, so
        cashtags ($TICKER) and company-name references are taken as positive
        attention (Trump rarely posts about a stock he wants to slam).
      * News headlines matching "Trump <praise verb> <Entity>" — the entity is
        regex-extracted and matched against the universe; non-matches are
        surfaced as untracked, which is how the next INTC gets discovered.

    Each dict carries source / company / ticker / is_tracked / title / url / date
    so the report can split into tracked vs untracked tables.
    """
    universe_idx = _build_universe_index(universe)
    days = config.NEWS_LOOKBACK_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out: List[Dict] = []
    seen: set = set()

    def _add(source: str, company: Optional[config.Company], display_name: str,
             ticker: Optional[str], title: str, url: str, date: str) -> None:
        key = (source, (ticker or display_name).lower(), url)
        if key in seen:
            return
        seen.add(key)
        out.append({
            "source": source,
            "ticker": ticker,
            "company_name": company.name if company else display_name,
            "is_tracked": company is not None,
            "title": title,
            "url": url,
            "date": date,
        })

    # --- Truth Social ---
    root = _truth_social_root()
    if root is not None:
        for item in root.findall(".//item"):
            pub_raw = item.findtext("pubDate") or ""
            try:
                pub_dt = parsedate_to_datetime(pub_raw) if pub_raw else None
            except Exception:
                pub_dt = None
            if pub_dt is not None and pub_dt < cutoff:
                continue
            title = item.findtext("title") or ""
            desc = item.findtext("description") or ""
            link = item.findtext("link") or ""
            content = f"{title} {desc}"

            # Cashtags ($TICKER) -- unambiguous, even for untracked names.
            for tkr in _CASHTAG_RE.findall(content):
                company = universe_idx.get(tkr.lower())
                _add("truth_social", company,
                     company.name if company else tkr,
                     company.ticker if company else tkr,
                     title or desc[:140], link, pub_raw)

            # Tracked company / CEO / alias mentions (word-boundary).
            content_low = content.lower()
            matched_tickers: set = set()
            for key, company in universe_idx.items():
                if len(key) < 4 or company.ticker in matched_tickers:
                    continue
                if re.search(rf"\b{re.escape(key)}\b", content_low):
                    # Apply person-name disambiguation for ambiguous short
                    # company names (e.g. "Parsons").
                    if key == company.name.lower() and not _headline_about_company(content, company):
                        continue
                    matched_tickers.add(company.ticker)
                    _add("truth_social", company, company.name,
                         company.ticker, title or desc[:140], link, pub_raw)

    # --- News: "Trump <praise verb> <Entity>" ---
    try:
        articles = _trump_news_articles(days)
    except Exception:
        articles = []

    for a in articles:
        title = a.get("title") or ""
        url = a.get("url") or ""
        date = a.get("seendate") or ""
        if not title:
            continue
        for m in _PRAISE_RE.finditer(title):
            entity = (m.group(1) or "").strip(" .,:;-")
            if len(entity) < 2:
                continue
            company = _classify_mention(entity, universe_idx)
            display = company.name if company else entity
            ticker = company.ticker if company else None
            _add("news", company, display, ticker, title, url, date)

    return out
