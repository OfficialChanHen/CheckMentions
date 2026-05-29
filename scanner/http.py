"""Shared HTTP layer: one session, per-host rate limiting, polite retries.

Every external call in the scanner goes through `get`/`post_json` here so that
rate limits (GDELT wants 1 req / 5s, Polygon's free tier 5 req/min, SEC asks for
a descriptive User-Agent, etc.) are enforced in exactly one place.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests

# Minimum seconds between requests to a given host. Tuned to each provider's
# documented free-tier limit, with a little headroom.
_MIN_INTERVAL = {
    "api.gdeltproject.org": 5.2,   # "limit requests to one every 5 seconds"
    "api.polygon.io": 13.0,        # free tier: 5 requests / minute
    "finnhub.io": 1.1,             # free tier: 60 / minute
    "efts.sec.gov": 0.2,           # SEC: stay well under 10 req/s
    "www.sec.gov": 0.2,
    "api.usaspending.gov": 0.35,
    "financialmodelingprep.com": 0.35,
    "newsapi.org": 0.25,
}
_DEFAULT_INTERVAL = 0.25

# Contact UA is required-as-courtesy by SEC and appreciated by GDELT.
USER_AGENT = "CheckMentions/1.0 (trump-shoutout-scanner; rathhen123@gmail.com)"

_last_hit: Dict[str, float] = {}
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return _session


def _throttle(url: str) -> None:
    host = urlparse(url).netloc
    interval = _MIN_INTERVAL.get(host, _DEFAULT_INTERVAL)
    last = _last_hit.get(host)
    if last is not None:
        wait = interval - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
    _last_hit[host] = time.monotonic()


def get(url: str, *, params: Optional[Dict[str, Any]] = None, timeout: int = 30,
        headers: Optional[Dict[str, str]] = None, retries: int = 2) -> Optional[requests.Response]:
    """Rate-limited GET. Returns the Response, or None on repeated failure."""
    for attempt in range(retries + 1):
        _throttle(url)
        try:
            resp = _get_session().get(url, params=params, timeout=timeout, headers=headers)
            if resp.status_code == 429 and attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            return resp
        except requests.RequestException:
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            return None
    return None


def get_json(url: str, **kwargs) -> Optional[Any]:
    resp = get(url, **kwargs)
    if resp is None or not resp.ok:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def post_json(url: str, payload: Dict[str, Any], *, timeout: int = 40,
              retries: int = 2) -> Optional[Any]:
    """Rate-limited POST with a JSON body, returning parsed JSON or None."""
    for attempt in range(retries + 1):
        _throttle(url)
        try:
            resp = _get_session().post(url, json=payload, timeout=timeout)
            if resp.status_code == 429 and attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            if not resp.ok:
                return None
            return resp.json()
        except (requests.RequestException, ValueError):
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            return None
    return None
