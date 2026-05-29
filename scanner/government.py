"""Government-interest signals (Layers 1 & 2) -- the threads that actually move
the valuation.

  * Layer 1 (strongest): is the government taking / weighing an equity stake?
      - SEC EDGAR full-text search for stake language near the company (no key)
      - Financial Modeling Prep congressional (Senate/House) buys (free key)
  * Layer 2: federal-revenue gravity -- recent contract obligations.
      - USASpending.gov spending_by_award (no key)

Also exposes discovery: top recent contract recipients by sector NAICS, used
to surface names that are not yet in the universe.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

from . import config, http

USASPENDING_AWARD_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
SEC_FTS_URL = "https://efts.sec.gov/LATEST/search-index"
FMP_SENATE_URL = "https://financialmodelingprep.com/api/v4/senate-trading"
FMP_HOUSE_URL = "https://financialmodelingprep.com/api/v4/senate-disclosure"
FMP_INSIDER_URL = "https://financialmodelingprep.com/api/v4/insider-trading"

CONTRACT_TYPES = ["A", "B", "C", "D"]  # definitive contracts + IDV task orders


def _window():
    end = date.today()
    start = end - timedelta(days=config.CONTRACT_LOOKBACK_DAYS)
    return start.isoformat(), end.isoformat()


def federal_contracts(company: config.Company) -> Dict:
    """Sum recent federal contract obligations to the company.

    Searches USASpending for each recipient alias and keeps the largest single
    award plus the total across the lookback window.
    """
    start, end = _window()
    names = [company.name] + company.aliases
    total = 0.0
    top_award = 0.0
    top_agency = ""
    count = 0
    seen = set()
    for name in names:
        payload = {
            "filters": {
                "time_period": [{"start_date": start, "end_date": end}],
                "award_type_codes": CONTRACT_TYPES,
                "recipient_search_text": [name],
            },
            "fields": ["Award ID", "Recipient Name", "Award Amount", "Awarding Agency"],
            "page": 1,
            "limit": 25,
            "sort": "Award Amount",
            "order": "desc",
        }
        data = http.post_json(USASPENDING_AWARD_URL, payload)
        if not isinstance(data, dict):
            continue
        for r in data.get("results", []) or []:
            aid = r.get("Award ID")
            if aid in seen:
                continue
            seen.add(aid)
            amt = float(r.get("Award Amount") or 0)
            total += amt
            count += 1
            if amt > top_award:
                top_award = amt
                top_agency = r.get("Awarding Agency") or ""
    return {
        "contract_total": total,
        "top_award": top_award,
        "top_agency": top_agency,
        "award_count": count,
    }


def stake_signal(company: config.Company) -> Dict:
    """Layer 1: evidence the government holds or is negotiating a stake.

    Combines SEC full-text hits on stake language near the company name with
    congressional-purchase disclosures from FMP (if a key is present).
    """
    # --- SEC EDGAR full-text search (recent filings) ---
    sec_hits = 0
    sec_form = ""
    q = f'"{company.name}"'
    for term in config.STAKE_TERMS:
        data = http.get_json(
            SEC_FTS_URL,
            params={"q": f"{q} {term}", "forms": "8-K,10-K,10-Q,SC 13D,SC 13G"},
            headers={"User-Agent": http.USER_AGENT},
        )
        if isinstance(data, dict):
            hits = (((data.get("hits") or {}).get("total") or {}).get("value")) or 0
            if hits:
                sec_hits += int(hits)
                if not sec_form:
                    forms = (((data.get("aggregations") or {}).get("form_filter") or {})
                             .get("buckets") or [])
                    if forms:
                        sec_form = forms[0].get("key", "")
        # only need a couple of probes to establish signal presence
        if sec_hits >= 3:
            break

    # --- Congressional buys (FMP, optional) ---
    congress_buys = 0
    fmp_key = config.env_key(config.KEY_FMP)
    if fmp_key:
        for url in (FMP_SENATE_URL, FMP_HOUSE_URL):
            data = http.get_json(url, params={"symbol": company.ticker, "apikey": fmp_key})
            if isinstance(data, list):
                for tx in data[:50]:
                    typ = (tx.get("type") or tx.get("transaction") or "").lower()
                    if "purchase" in typ or "buy" in typ:
                        congress_buys += 1

    return {
        "sec_stake_hits": min(sec_hits, 5),
        "sec_form": sec_form,
        "congress_buys": congress_buys,
    }


def insider_buys_fmp(ticker: str) -> int:
    """Optional FMP insider-purchase count (positioning layer support)."""
    fmp_key = config.env_key(config.KEY_FMP)
    if not fmp_key:
        return 0
    data = http.get_json(FMP_INSIDER_URL, params={"symbol": ticker, "page": 0, "apikey": fmp_key})
    if not isinstance(data, list):
        return 0
    buys = 0
    for tx in data[:60]:
        if "P-Purchase" in (tx.get("transactionType") or ""):
            buys += 1
    return buys


def discover_contract_recipients(known_aliases: List[str], limit: int = 8) -> List[Dict]:
    """Surface big recent contract recipients in target sectors that are NOT in
    the tracked universe -- candidate "next INTC" names to review by hand.
    """
    start, end = _window()
    known = {a.lower() for a in known_aliases}
    found: Dict[str, Dict] = {}
    payload_fields = ["Recipient Name", "Award Amount", "Awarding Agency", "NAICS"]
    for naics in config.DISCOVERY_NAICS:
        payload = {
            "filters": {
                "time_period": [{"start_date": start, "end_date": end}],
                "award_type_codes": CONTRACT_TYPES,
                "naics_codes": [naics],
            },
            "fields": payload_fields,
            "page": 1,
            "limit": 15,
            "sort": "Award Amount",
            "order": "desc",
        }
        data = http.post_json(USASPENDING_AWARD_URL, payload)
        if not isinstance(data, dict):
            continue
        for r in data.get("results", []) or []:
            name = (r.get("Recipient Name") or "").strip()
            if not name:
                continue
            low = name.lower()
            # skip names that map to something we already track
            if any(k in low or low in k for k in known):
                continue
            amt = float(r.get("Award Amount") or 0)
            cur = found.get(low)
            if cur is None or amt > cur["amount"]:
                found[low] = {
                    "name": name,
                    "amount": amt,
                    "agency": r.get("Awarding Agency") or "",
                }
    ranked = sorted(found.values(), key=lambda x: x["amount"], reverse=True)
    return ranked[:limit]
