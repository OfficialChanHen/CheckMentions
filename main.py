#!/usr/bin/env python3
"""Daily Trump-shoutout candidate scanner — entry point.

Run order:
  1. Gather cheap signals for every tracked company (contracts, stake language,
     news/exec-alignment, price/volume, insider).
  2. Preliminary score; enrich the top names with rate-limited Polygon options.
  3. Re-score, rank, and discover untracked contract recipients.
  4. Write reports/<date>.md and emit the GitHub Issue title/body.

Designed to run unattended in GitHub Actions. Every data source degrades
gracefully: a missing API key or a failed call yields a neutral signal, never a
crash.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

from scanner import config, government, market, news, report
from scanner.config import PACIFIC
from scanner.scoring import Candidate, score_candidate


def active_keys() -> list:
    names = {
        config.KEY_NEWSAPI: "NewsAPI",
        config.KEY_POLYGON: "Polygon",
        config.KEY_FINNHUB: "Finnhub",
        config.KEY_FMP: "FMP",
        config.KEY_FEC: "FEC",
    }
    return [label for env, label in names.items() if config.env_key(env)]


def gather(company: config.Company) -> Candidate:
    signals = {}
    # Layer 2 — federal contracts
    signals.update(government.federal_contracts(company))
    # Layer 1 — government stake / congressional buys
    signals.update(government.stake_signal(company))
    # Layers 4 & 5 — news + executive alignment
    signals.update(news.news_signal(company))
    # Layer 6 — Truth Social direct mentions
    signals.update(news.truth_social_signal(company))
    # Layer 8 — Executive Orders naming the company (Federal Register, no key)
    signals.update(government.executive_order_mentions(company))
    # Layer 3 — price/volume + insider (options added later for top names)
    signals.update(market.price_volume(company.ticker))
    signals["insider_buy"] = max(
        market.insider_sentiment_finnhub(company.ticker),
        min(1.0, government.insider_buys_fmp(company.ticker) / 4.0),
    )
    signals["options_flow"] = 0.0
    # Trump personal holdings boost the positioning layer (static list, no API call).
    signals["trump_holds"] = government.trump_holds_stock(company.ticker)
    # Layer 7 — CEO FEC donations: zero by default; enriched in a second pass below.
    signals["ceo_fec_donations"] = 0
    cand = Candidate(company=company, signals=signals)
    return score_candidate(cand)


def _refresh_news_signals(candidates: list) -> None:
    """Re-run news_signal for every gathered candidate. Called when NewsAPI
    quota burns mid-run; after this returns, every candidate's L4/L5 numbers
    come from the same source (GDELT) instead of a mix of NewsAPI and GDELT.
    """
    print(f"[scan] re-running L4/L5 via GDELT for {len(candidates)} candidates",
          flush=True)
    for cand in candidates:
        try:
            cand.signals.update(news.news_signal(cand.company))
            score_candidate(cand)
        except Exception as e:
            print(f"[warn] gdelt refresh {cand.ticker}: {e}", flush=True)


def main() -> int:
    today_pt = datetime.now(PACIFIC)
    date_str = today_pt.strftime("%Y-%m-%d")
    keys = active_keys()
    print(f"[scan] {date_str} — active keys: {keys or 'none (free sources only)'}", flush=True)

    # Pre-flight NewsAPI quota probe. If quota is already burned at scan
    # start, switch the whole run to GDELT so every ticker uses the same
    # source -- otherwise mid-run quota burnout would mix NewsAPI's coverage
    # shape (tickers 1..N) with GDELT's (N+1..47), breaking cross-ticker
    # rank comparability.
    newsapi_key = config.env_key(config.KEY_NEWSAPI)
    if newsapi_key and not news._newsapi_healthy(newsapi_key):
        news.force_gdelt_mode("pre-flight probe failed -- quota already at 0")

    candidates = []
    for i, company in enumerate(config.UNIVERSE, 1):
        print(f"[scan] ({i}/{len(config.UNIVERSE)}) {company.ticker} {company.name}", flush=True)
        try:
            candidates.append(gather(company))
        except Exception as e:  # never let one name kill the run
            print(f"[warn] {company.ticker} failed: {e}", flush=True)
        # Mid-run quota detection. If _NEWSAPI_QUOTA_HIT just flipped, switch
        # to GDELT mode and re-fetch the already-gathered candidates' L4/L5
        # via GDELT so the whole run has consistent news-source coverage.
        if news._NEWSAPI_QUOTA_HIT and not news._GDELT_ONLY:
            news.force_gdelt_mode(f"quota burned at ticker {i}/{len(config.UNIVERSE)}")
            _refresh_news_signals(candidates)

    # Enrich the strongest preliminary candidates with Polygon options flow.
    candidates.sort(key=lambda c: c.score, reverse=True)
    if config.env_key(config.KEY_POLYGON):
        for cand in candidates[: config.POLYGON_TOP_N]:
            try:
                poly = market.options_activity_polygon(cand.ticker)
                # options_activity_polygon returns options_flow + a stale-data
                # flag the report uses to surface "Polygon EOD lag" instead of
                # silently scoring everyone at 0.
                cand.signals.update(poly)
                if poly.get("options_flow"):
                    score_candidate(cand)
            except Exception as e:
                print(f"[warn] polygon {cand.ticker}: {e}", flush=True)
        candidates.sort(key=lambda c: c.score, reverse=True)

    # Enrich top candidates with FEC CEO-donation data (rate-limited; second pass).
    # Works without a key via DEMO_KEY (40 req/hr); add FEC_API_KEY for full speed.
    for cand in candidates[: config.FEC_TOP_N]:
        try:
            donations = government.ceo_fec_donations(cand.company.ceo)
            if donations:
                cand.signals["ceo_fec_donations"] = donations
                score_candidate(cand)
        except Exception as e:
            print(f"[warn] fec {cand.ticker}: {e}", flush=True)
    candidates.sort(key=lambda c: c.score, reverse=True)

    # Discovery — untracked contract recipients in target sectors.
    known_aliases = []
    for c in config.UNIVERSE:
        known_aliases.append(c.name)
        known_aliases.extend(c.aliases)
    try:
        discoveries = government.discover_contract_recipients(known_aliases)
    except Exception as e:
        print(f"[warn] discovery failed: {e}", flush=True)
        discoveries = []

    # Global scan: Trump positive mentions of any company (tracked or not).
    try:
        positive_mentions = news.trump_positive_mentions(config.UNIVERSE)
    except Exception as e:
        print(f"[warn] positive-mention scan failed: {e}", flush=True)
        positive_mentions = []

    # Write outputs.
    os.makedirs("reports", exist_ok=True)
    report_path = f"reports/{date_str}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report.build_report(date_str, candidates, discoveries, keys,
                                    positive_mentions))
    print(f"[scan] wrote {report_path}", flush=True)

    issue_title = f"Trump-Shoutout Candidates — {date_str}"
    issue_body = report.build_issue_body(date_str, candidates, report_path)
    with open("issue_body.md", "w", encoding="utf-8") as f:
        f.write(issue_body)

    # Hand the title/path to the workflow via step outputs when available.
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"issue_title={issue_title}\n")
            f.write(f"report_path={report_path}\n")
            f.write(f"date={date_str}\n")

    top = candidates[0] if candidates else None
    if top:
        print(f"[scan] top candidate: {top.ticker} ({top.score:.1f})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
