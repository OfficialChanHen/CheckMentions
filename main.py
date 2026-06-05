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
from zoneinfo import ZoneInfo

from scanner import config, government, market, news, report
from scanner.scoring import Candidate, score_candidate

PACIFIC = ZoneInfo("America/Los_Angeles")


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


def main() -> int:
    today_pt = datetime.now(PACIFIC)
    date_str = today_pt.strftime("%Y-%m-%d")
    keys = active_keys()
    print(f"[scan] {date_str} — active keys: {keys or 'none (free sources only)'}", flush=True)

    candidates = []
    for i, company in enumerate(config.UNIVERSE, 1):
        print(f"[scan] ({i}/{len(config.UNIVERSE)}) {company.ticker} {company.name}", flush=True)
        try:
            candidates.append(gather(company))
        except Exception as e:  # never let one name kill the run
            print(f"[warn] {company.ticker} failed: {e}", flush=True)

    # Enrich the strongest preliminary candidates with Polygon options flow.
    candidates.sort(key=lambda c: c.score, reverse=True)
    if config.env_key(config.KEY_POLYGON):
        for cand in candidates[: config.POLYGON_TOP_N]:
            try:
                flow = market.options_activity_polygon(cand.ticker)
                if flow:
                    cand.signals["options_flow"] = flow
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
