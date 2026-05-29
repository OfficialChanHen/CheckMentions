"""Market & positioning signals (Layer 3).

Real-time options *flow* is a paid product, so this layer approximates the same
idea -- "is someone positioning ahead of news?" -- from freely available data:

  * yfinance  : 1-month price return + a volume-spike ratio (no key)
  * Polygon   : recent options-contract activity, the closest free proxy to
                unusual options flow (free key, rate-limited -> top names only)
  * Finnhub   : insider-sentiment / transactions (free key)
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Optional

from . import config, http

FINNHUB_INSIDER_URL = "https://finnhub.io/api/v1/stock/insider-sentiment"
POLYGON_OPTIONS_URL = "https://api.polygon.io/v3/snapshot/options/{ticker}"


def price_volume(ticker: str) -> Dict:
    """1-month return and recent-vs-average volume ratio via yfinance."""
    try:
        import yfinance as yf
    except Exception:
        return {"ret_1m": 0.0, "volume_spike": 1.0}
    try:
        hist = yf.Ticker(ticker).history(period="3mo", auto_adjust=True)
        if hist is None or hist.empty or len(hist) < 25:
            return {"ret_1m": 0.0, "volume_spike": 1.0}
        closes = hist["Close"].dropna()
        vols = hist["Volume"].dropna()
        # ~21 trading days ago to now
        ret_1m = float(closes.iloc[-1] / closes.iloc[-min(21, len(closes))] - 1.0)
        recent = float(vols.iloc[-5:].mean())
        base = float(vols.iloc[:-5].mean()) or 1.0
        spike = recent / base if base else 1.0
        return {"ret_1m": ret_1m, "volume_spike": spike}
    except Exception:
        return {"ret_1m": 0.0, "volume_spike": 1.0}


def insider_sentiment_finnhub(ticker: str) -> float:
    """Aggregate Finnhub MSPR (insider sentiment, -100..100) over the lookback.

    Returns a 0..1 'net buying' score; 0 if no key or no data.
    """
    key = config.env_key(config.KEY_FINNHUB)
    if not key:
        return 0.0
    frm = (date.today() - timedelta(days=config.INSIDER_LOOKBACK_DAYS)).isoformat()
    data = http.get_json(
        FINNHUB_INSIDER_URL,
        params={"symbol": ticker, "from": frm, "to": date.today().isoformat(), "token": key},
    )
    if not isinstance(data, dict):
        return 0.0
    rows = data.get("data") or []
    if not rows:
        return 0.0
    avg_mspr = sum(float(r.get("mspr") or 0) for r in rows) / len(rows)
    # map -100..100 -> 0..1, clamp
    return max(0.0, min(1.0, (avg_mspr + 100) / 200))


def options_activity_polygon(ticker: str) -> float:
    """Unusual-options proxy from Polygon's options snapshot (free key).

    Scores 0..1 from the share of the most-active contracts showing elevated
    volume-vs-open-interest -- a classic 'fresh positioning' tell. Polygon's
    free tier is heavily rate-limited, so call this only for top candidates.
    """
    key = config.env_key(config.KEY_POLYGON)
    if not key:
        return 0.0
    data = http.get_json(
        POLYGON_OPTIONS_URL.format(ticker=ticker),
        params={"order": "desc", "sort": "volume", "limit": 50, "apiKey": key},
    )
    if not isinstance(data, dict):
        return 0.0
    results = data.get("results") or []
    if not results:
        return 0.0
    fresh = 0
    considered = 0
    for c in results:
        day = c.get("day") or {}
        vol = float(day.get("volume") or 0)
        oi = float(c.get("open_interest") or 0)
        if vol <= 0:
            continue
        considered += 1
        # volume exceeding open interest = contracts opened today, not held
        if oi > 0 and vol > oi:
            fresh += 1
        elif oi == 0 and vol > 100:
            fresh += 1
    if considered == 0:
        return 0.0
    return min(1.0, fresh / considered)
