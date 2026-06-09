"""Market & positioning signals (Layer 3).

Real-time options *flow* is a paid product, so this layer approximates the same
idea -- "is someone positioning ahead of news?" -- from freely available data:

  * yfinance  : 1-month price return + a volume-spike ratio (no key)
  * Polygon   : recent options-contract activity, the closest free proxy to
                unusual options flow (free key, rate-limited -> top names only)
  * Finnhub   : insider-sentiment / transactions (free key)
"""

from __future__ import annotations

from datetime import timedelta
from typing import Dict, Optional

from . import config, http

FINNHUB_INSIDER_URL = "https://finnhub.io/api/v1/stock/insider-sentiment"
POLYGON_OPTIONS_URL = "https://api.polygon.io/v3/snapshot/options/{ticker}"
# Polygon's /v3/snapshot/options endpoint accepts sort = ticker | strike_price
# | expiration_date (NOT volume). Asking for `sort=volume` silently falls back
# to the default (ticker), which buried the high-volume contracts past the
# limit cutoff and made options_flow read 0.00 for every name.


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
    today = config.today_pacific()
    frm = (today - timedelta(days=config.INSIDER_LOOKBACK_DAYS)).isoformat()
    data = http.get_json(
        FINNHUB_INSIDER_URL,
        params={"symbol": ticker, "from": frm, "to": today.isoformat(), "token": key},
    )
    if not isinstance(data, dict):
        return 0.0
    rows = data.get("data") or []
    if not rows:
        return 0.0
    avg_mspr = sum(float(r.get("mspr") or 0) for r in rows) / len(rows)
    # map -100..100 -> 0..1, clamp
    return max(0.0, min(1.0, (avg_mspr + 100) / 200))


def options_activity_polygon(ticker: str) -> Dict:
    """Unusual-options proxy from Polygon's options snapshot (free key).

    Returns {"options_flow": float 0..1, "polygon_data_stale": bool}. The
    `polygon_data_stale` flag is set when today's volume data hasn't
    propagated to the free tier yet (typical at 5 AM PT scan time), in which
    case the score falls back to an open-interest concentration proxy rather
    than reading 0 and looking identical to "no unusual positioning".

    Two scoring paths:
      * Live data path (`day.volume > 0` on at least one contract): the
        classic vol-vs-OI heuristic -- fresh contracts opened today, not
        held -- gives a precise positioning read.
      * OI-fallback path (`day.volume == 0` across the whole response):
        rank by `open_interest`, score by the concentration of the top-20
        contracts' OI as a share of the whole chain's OI. Concentration in
        a few strikes is a classic positioning tell even without today's
        volume data; the data_stale flag fires so the report tells the
        user the scoring path degraded.
    """
    key = config.env_key(config.KEY_POLYGON)
    if not key:
        return {"options_flow": 0.0, "polygon_data_stale": False}
    horizon = (config.today_pacific() + timedelta(days=120)).isoformat()
    data = http.get_json(
        POLYGON_OPTIONS_URL.format(ticker=ticker),
        params={
            "expiration_date.lte": horizon,
            "limit": 250,
            "apiKey": key,
        },
    )
    if not isinstance(data, dict):
        return {"options_flow": 0.0, "polygon_data_stale": False}
    results = data.get("results") or []
    if not results:
        return {"options_flow": 0.0, "polygon_data_stale": False}

    # Live data path: sort by today's volume and apply vol-vs-OI heuristic.
    results.sort(key=lambda c: float((c.get("day") or {}).get("volume") or 0), reverse=True)
    top = results[:50]
    fresh = 0
    considered = 0
    for c in top:
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

    if considered > 0:
        return {
            "options_flow": min(1.0, fresh / considered),
            "polygon_data_stale": False,
        }

    # Fallback path: every contract had volume = 0 (free-tier EOD lag or
    # pre-market). Rank by open_interest and use top-20 OI concentration
    # as the positioning proxy.
    results.sort(key=lambda c: float(c.get("open_interest") or 0), reverse=True)
    total_oi = sum(float(c.get("open_interest") or 0) for c in results)
    if total_oi <= 0:
        return {"options_flow": 0.0, "polygon_data_stale": True}
    top20_oi = sum(float(c.get("open_interest") or 0) for c in results[:20])
    # Concentration of the top-20 in the whole chain. A diversified chain
    # (every strike has roughly equal OI) scores low; a chain where one
    # strike dwarfs the rest scores high.
    concentration = top20_oi / total_oi
    # Map [0..1] concentration onto [0..1] score with a small floor so a
    # totally-flat chain reads as 0 rather than negative.
    return {
        "options_flow": max(0.0, min(1.0, (concentration - 0.2) / 0.6)),
        "polygon_data_stale": True,
    }
