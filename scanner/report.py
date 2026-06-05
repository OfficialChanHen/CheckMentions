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
    holds_note = " ✓ Trump holds" if s.get("trump_holds") else ""
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
            + holds_note
        ),
        "exec_alignment": f"{cand.company.ceo}: {s.get('exec_praise_hits', 0)} pro-Trump headline(s)",
        "exec_order": f"{s.get('exec_order_hits', 0)} Executive Order(s) naming {cand.company.name} (180d)",
        "trump_mention": f"{s.get('trump_mentions', 0)} Trump co-mentions in news (30d)",
        "truth_social": f"{s.get('truth_social_hits', 0)} Truth Social post(s) naming {cand.company.name}",
        "ceo_donor": (
            f"{cand.company.ceo}: {s.get('ceo_fec_donations', 0)} FEC donation(s) to Trump committees"
            if s.get("ceo_fec_donations") is not None
            else f"{cand.company.ceo}: not checked (FEC key absent or pending enrichment)"
        ),
    }
    label = {
        "gov_stake": "🏛️ Gov stake (L1)",
        "federal_revenue": "📑 Federal revenue (L2)",
        "positioning": "📈 Positioning (L3)",
        "exec_alignment": "🤝 Exec alignment (L5)",
        "exec_order": "📜 Executive Order (L8)",
        "trump_mention": "📣 Trump mention (L4)",
        "truth_social": "🔊 Truth Social (L6)",
        "ceo_donor": "💰 CEO donor (L7)",
    }
    for k in ("gov_stake", "federal_revenue", "positioning", "exec_alignment",
              "exec_order", "trump_mention", "truth_social", "ceo_donor"):
        lines.append(f"| {label[k]} | {cand.layers.get(k, 0):.2f} | {ev[k]} |")

    heads = s.get("headlines") or []
    ts_posts = s.get("truth_social_posts") or []
    eos = s.get("exec_orders") or []
    if heads or ts_posts or eos:
        lines.append("")
        if eos:
            lines.append("**Executive Orders:**")
            for e in eos[:2]:
                title = e.get("title", "").replace("|", "·")
                url = e.get("url", "")
                lines.append(f"- [{title}]({url})" if url else f"- {title}")
        if ts_posts:
            lines.append("**Truth Social posts:**")
            for p in ts_posts[:2]:
                title = p.get("title", "").replace("|", "·")
                url = p.get("url", "")
                lines.append(f"- [{title}]({url})" if url else f"- {title}")
        if heads:
            lines.append("**Recent headlines:**")
            for h in heads[:3]:
                title = h.get("title", "").replace("|", "·")
                url = h.get("url", "")
                lines.append(f"- [{title}]({url})" if url else f"- {title}")
    lines.append("")
    return "\n".join(lines)


def _positive_mentions_section(mentions: List[Dict]) -> List[str]:
    """Render the 'Positive Trump mentions' tables (tracked + untracked)."""
    lines = [
        "## 🎤 Positive Trump mentions (in & out of universe)",
        "",
        "_Recent Truth Social posts authored by @realDonaldTrump and news "
        "headlines of the form \"Trump praises/backs/thanks X\" — split by "
        "whether the named company is already in the tracked universe._",
        "",
    ]
    if not mentions:
        lines.append("_No positive Trump mentions surfaced this run._\n")
        return lines

    tracked = [m for m in mentions if m.get("is_tracked")]
    untracked = [m for m in mentions if not m.get("is_tracked")]

    def _row(m: Dict) -> str:
        title = (m.get("title") or "").replace("|", "·").strip()
        url = m.get("url") or ""
        title_md = f"[{title}]({url})" if (title and url) else (title or "—")
        src = "🔊 Truth Social" if m.get("source") == "truth_social" else "📰 News"
        tkr = m.get("ticker") or ""
        name = m.get("company_name") or ""
        return f"| {src} | **{tkr}** | {name} | {title_md} |"

    if tracked:
        lines.append("**Tracked universe — Trump named these recently:**")
        lines.append("")
        lines.append("| Source | Ticker | Company | Headline / Post |")
        lines.append("|---|---|---|---|")
        for m in tracked[:15]:
            lines.append(_row(m))
        lines.append("")
    if untracked:
        lines.append("**Untracked — consider adding to `scanner/config.py`:**")
        lines.append("")
        lines.append("| Source | Cashtag / Entity | Headline / Post |")
        lines.append("|---|---|---|")
        for m in untracked[:15]:
            title = (m.get("title") or "").replace("|", "·").strip()
            url = m.get("url") or ""
            title_md = f"[{title}]({url})" if (title and url) else (title or "—")
            src = "🔊 Truth Social" if m.get("source") == "truth_social" else "📰 News"
            ent = m.get("ticker") or m.get("company_name") or ""
            lines.append(f"| {src} | **{ent}** | {title_md} |")
        lines.append("")
    return lines


def build_report(date_str: str, ranked: List[Candidate], discoveries: List[Dict],
                 active_keys: List[str],
                 positive_mentions: List[Dict] | None = None) -> str:
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
        + (", FEC" if "FEC" in active_keys else "")
        + ", Truth Social RSS, Federal Register"
        + "). Verify before acting.",
        "",
        "## The checklist (in order of how early it fires)",
        "1. 🏛️ **Government stake** held or in talks — the single strongest filter (the INTC model).",
        "2. 📑 **Federal-revenue share** high and policy clearing the competition (DELL, PLTR, MU).",
        "3. 📈 **Unusual positioning** — options flow / insider buying / volume spikes with no news.",
        "4. 🤝 **Executive alignment** — the CEO publicly backs / invests alongside Trump.",
        "5. 📣 **Trump mention** — timing confirmation from news co-mentions.",
        "6. 🔊 **Truth Social** — Trump directly posts about the company on his own platform.",
        "7. 💰 **CEO donor** — FEC-verified donation from the CEO to a Trump campaign/PAC.",
        "8. 📜 **Executive Order** — a signed EO names the company directly (Federal Register).",
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

    parts.extend(_positive_mentions_section(positive_mentions or []))
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
