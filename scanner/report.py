"""Render the daily Markdown report and the GitHub Issue body."""

from __future__ import annotations

from typing import Dict, List

from .scoring import Candidate, fired_layers


def _fmt_money(x: float) -> str:
    if x >= 1e9:
        return f"${x/1e9:.2f}B"
    if x >= 1e6:
        return f"${x/1e6:.1f}M"
    if x >= 1e3:
        return f"${x/1e3:.0f}K"
    return f"${x:.0f}"


def _candidate_block(cand: Candidate) -> str:
    s = cand.signals
    flags = ", ".join(fired_layers(cand)) or "—"
    lines = [
        f"### {cand.score:.1f}  ·  {cand.company.name} ({cand.ticker})  ·  _{cand.company.sector}_",
        f"**Signals fired:** {flags}",
        "",
        "| Layer | Score | Evidence |",
        "|---|---|---|",
    ]
    ev = {
        "gov_stake": (
            f"SEC stake-language hits: {s.get('sec_stake_hits', 0)}"
            + (f" ({s.get('sec_form')})" if s.get("sec_form") else "")
            + f"; congressional buys: {s.get('congress_buys', 0)}"
        ),
        "federal_revenue": (
            f"{_fmt_money(s.get('contract_total', 0))} across {s.get('award_count', 0)} awards"
            + (f"; top {_fmt_money(s.get('top_award', 0))} from {s.get('top_agency')}"
               if s.get("top_award") else "")
        ),
        "positioning": (
            f"1m return {s.get('ret_1m', 0)*100:+.1f}%; volume {s.get('volume_spike', 1):.1f}×"
            f"; options flow {s.get('options_flow', 0):.2f}; insider {s.get('insider_buy', 0):.2f}"
        ),
        "exec_alignment": f"{cand.company.ceo}: {s.get('exec_praise_hits', 0)} pro-Trump headline(s)",
        "trump_mention": f"{s.get('trump_mentions', 0)} Trump co-mentions (30d)",
    }
    label = {
        "gov_stake": "🏛️ Gov stake (L1)",
        "federal_revenue": "📑 Federal revenue (L2)",
        "positioning": "📈 Positioning (L3)",
        "exec_alignment": "🤝 Exec alignment (L5)",
        "trump_mention": "📣 Trump mention (L4)",
    }
    for k in ("gov_stake", "federal_revenue", "positioning", "exec_alignment", "trump_mention"):
        lines.append(f"| {label[k]} | {cand.layers.get(k, 0):.2f} | {ev[k]} |")

    heads = s.get("headlines") or []
    if heads:
        lines.append("")
        lines.append("**Recent headlines:**")
        for h in heads[:3]:
            title = h.get("title", "").replace("|", "·")
            url = h.get("url", "")
            lines.append(f"- [{title}]({url})" if url else f"- {title}")
    lines.append("")
    return "\n".join(lines)


def build_report(date_str: str, ranked: List[Candidate], discoveries: List[Dict],
                 active_keys: List[str]) -> str:
    top = ranked[:10]
    parts = [
        f"# Trump-Shoutout Candidate Scan — {date_str}",
        "",
        "_Reverse-engineering the “buy in low → talk it up → government delivers” "
        "pattern into a checklist that catches the next name **before** the shoutout. "
        "Scores weight the leading signals (a government stake, federal-revenue "
        "gravity) over the shoutout itself — chasing the shoutout means chasing a "
        "rally that is usually already over._",
        "",
        "> **Not investment advice.** This is an automated signal scan built from "
        "public data (USASpending, SEC EDGAR, GDELT"
        + ("/NewsAPI" if "NewsAPI" in active_keys else "")
        + ", yfinance"
        + (", Polygon" if "Polygon" in active_keys else "")
        + (", Finnhub" if "Finnhub" in active_keys else "")
        + (", FMP" if "FMP" in active_keys else "")
        + "). Verify before acting.",
        "",
        "## The checklist (in order of how early it fires)",
        "1. 🏛️ **Government stake** held or in talks — the single strongest filter (the INTC model).",
        "2. 📑 **Federal-revenue share** high and policy clearing the competition (DELL, PLTR, MU).",
        "3. 📈 **Unusual positioning** — options flow / insider buying / volume spikes with no news.",
        "4. 🤝 **Executive alignment** — the CEO publicly backs / invests alongside Trump.",
        "5. 📣 **Trump mention** — timing confirmation, the *last* layer, not the first.",
        "",
        "## Top candidates",
        "",
    ]
    if not top:
        parts.append("_No candidates scored above zero this run (data sources may have been unavailable)._\n")
    else:
        parts.append("| # | Ticker | Company | Score | Signals fired |")
        parts.append("|---|---|---|---|---|")
        for i, c in enumerate(top, 1):
            parts.append(f"| {i} | **{c.ticker}** | {c.company.name} | {c.score:.1f} | "
                         f"{', '.join(fired_layers(c)) or '—'} |")
        parts.append("")
        parts.append("## Detail")
        parts.append("")
        for c in top:
            parts.append(_candidate_block(c))

    parts.append("## 🔭 New entrants to review")
    parts.append("")
    parts.append("_Big recent federal-contract recipients in target sectors that are **not** "
                 "yet tracked. Manually map any worth adding to `scanner/config.py`._")
    parts.append("")
    if discoveries:
        parts.append("| Recipient | Recent top award | Agency |")
        parts.append("|---|---|---|")
        for d in discoveries:
            parts.append(f"| {d['name']} | {_fmt_money(d['amount'])} | {d.get('agency','')} |")
    else:
        parts.append("_None surfaced this run._")
    parts.append("")
    parts.append("---")
    parts.append(f"_Active data keys this run: {', '.join(active_keys) if active_keys else 'free sources only'}._")
    parts.append("")
    return "\n".join(parts)


def build_issue_body(date_str: str, ranked: List[Candidate], report_path: str) -> str:
    top = ranked[:5]
    lines = [
        f"Daily Trump-shoutout candidate scan for **{date_str}**.",
        "",
        "**Top 5 by checklist score (leading signals weighted over the shoutout):**",
        "",
    ]
    if top:
        for i, c in enumerate(top, 1):
            lines.append(f"{i}. **{c.ticker}** — {c.company.name} · score **{c.score:.1f}** · "
                         f"{', '.join(fired_layers(c)) or '—'}")
    else:
        lines.append("_No candidates scored above zero this run._")
    lines += [
        "",
        f"📄 Full report: [`{report_path}`]({report_path})",
        "",
        "_Automated signal scan from public data — not investment advice._",
    ]
    return "\n".join(lines)
