"""Static configuration: the candidate universe, sector targeting, scoring
weights, and keyword banks.

This file is meant to be edited by hand. Add a row to UNIVERSE to track a new
name; the scanner does the rest. CEO names power the "executive praises Trump"
layer, so keep them current (they were accurate as of early 2026).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Company:
    ticker: str
    name: str            # canonical name used in news phrase search
    ceo: str             # CEO full name, for the executive-alignment layer
    sector: str
    aliases: List[str] = field(default_factory=list)  # extra names for contract matching


# ---------------------------------------------------------------------------
# The universe. Clustered exactly where the pattern lives: semis, AI infra,
# defense, and federal tech. These are the sectors where a government order,
# stake, or policy tailwind actually moves the valuation.
# ---------------------------------------------------------------------------
UNIVERSE: List[Company] = [
    # --- Semiconductors / AI silicon ---
    Company("INTC", "Intel", "Lip-Bu Tan", "Semiconductors", ["Intel Corp", "Intel Federal"]),
    Company("NVDA", "Nvidia", "Jensen Huang", "Semiconductors", ["Nvidia Corp"]),
    Company("MU", "Micron", "Sanjay Mehrotra", "Semiconductors", ["Micron Technology"]),
    Company("AMD", "AMD", "Lisa Su", "Semiconductors", ["Advanced Micro Devices"]),
    Company("AVGO", "Broadcom", "Hock Tan", "Semiconductors", ["Broadcom Inc"]),
    Company("QCOM", "Qualcomm", "Cristiano Amon", "Semiconductors", ["Qualcomm Inc"]),
    Company("TXN", "Texas Instruments", "Haviv Ilan", "Semiconductors", []),
    Company("MCHP", "Microchip Technology", "Steve Sanghi", "Semiconductors", []),
    Company("ON", "ON Semiconductor", "Hassane El-Khoury", "Semiconductors", ["onsemi"]),
    Company("GFS", "GlobalFoundries", "Tim Breen", "Semiconductors", []),
    Company("AMAT", "Applied Materials", "Gary Dickerson", "Semiconductors", []),
    Company("LRCX", "Lam Research", "Tim Archer", "Semiconductors", []),
    Company("KLAC", "KLA Corporation", "Rick Wallace", "Semiconductors", ["KLA Corp"]),
    Company("TSM", "TSMC", "C.C. Wei", "Semiconductors", ["Taiwan Semiconductor"]),
    Company("ARM", "Arm Holdings", "Rene Haas", "Semiconductors", []),

    # --- Hardware / AI infrastructure ---
    Company("DELL", "Dell", "Michael Dell", "AI Infrastructure", ["Dell Technologies", "Dell Federal Systems"]),
    Company("SMCI", "Super Micro", "Charles Liang", "AI Infrastructure", ["Super Micro Computer", "Supermicro"]),
    Company("HPE", "Hewlett Packard Enterprise", "Antonio Neri", "AI Infrastructure", ["HPE"]),
    Company("HPQ", "HP Inc", "Enrique Lores", "AI Infrastructure", ["Hewlett-Packard"]),
    Company("ANET", "Arista Networks", "Jayshree Ullal", "AI Infrastructure", []),
    Company("CSCO", "Cisco", "Chuck Robbins", "AI Infrastructure", ["Cisco Systems"]),
    Company("WDC", "Western Digital", "Irving Tan", "AI Infrastructure", []),
    Company("STX", "Seagate", "Dave Mosley", "AI Infrastructure", ["Seagate Technology"]),
    Company("VRT", "Vertiv", "Giordano Albertazzi", "AI Infrastructure", ["Vertiv Holdings"]),

    # --- Federal tech / software / cloud ---
    Company("PLTR", "Palantir", "Alex Karp", "Federal Tech", ["Palantir Technologies"]),
    Company("ORCL", "Oracle", "Safra Catz", "Federal Tech", ["Oracle Corp", "Oracle America"]),
    Company("MSFT", "Microsoft", "Satya Nadella", "Federal Tech", ["Microsoft Corp"]),
    Company("IBM", "IBM", "Arvind Krishna", "Federal Tech", ["International Business Machines"]),
    Company("AMZN", "Amazon", "Andy Jassy", "Federal Tech", ["Amazon Web Services", "Amazon.com"]),
    Company("GOOGL", "Google", "Sundar Pichai", "Federal Tech", ["Alphabet", "Google LLC"]),
    Company("CRM", "Salesforce", "Marc Benioff", "Federal Tech", []),
    Company("NOW", "ServiceNow", "Bill McDermott", "Federal Tech", []),
    Company("SNOW", "Snowflake", "Sridhar Ramaswamy", "Federal Tech", []),

    # --- Defense primes & services ---
    Company("LMT", "Lockheed Martin", "Jim Taiclet", "Defense", []),
    Company("RTX", "RTX", "Chris Calio", "Defense", ["Raytheon", "RTX Corporation"]),
    Company("NOC", "Northrop Grumman", "Kathy Warden", "Defense", []),
    Company("GD", "General Dynamics", "Phebe Novakovic", "Defense", []),
    Company("BA", "Boeing", "Kelly Ortberg", "Defense", ["Boeing Company"]),
    Company("LDOS", "Leidos", "Tom Bell", "Defense", ["Leidos Holdings"]),
    Company("BAH", "Booz Allen Hamilton", "Horacio Rozanski", "Defense", ["Booz Allen"]),
    Company("SAIC", "SAIC", "Toni Townes-Whitley", "Defense", ["Science Applications International"]),
    Company("CACI", "CACI International", "John Mengucci", "Defense", ["CACI"]),
    Company("KTOS", "Kratos", "Eric DeMarco", "Defense", ["Kratos Defense"]),
    Company("PSN", "Parsons", "Carey Smith", "Defense", ["Parsons Corporation"]),

    # --- Mentioned by name in the source brief ---
    Company("TMO", "Thermo Fisher", "Marc Casper", "Federal Tech", ["Thermo Fisher Scientific"]),
]

# Quick lookups
BY_TICKER: Dict[str, Company] = {c.ticker: c for c in UNIVERSE}


# ---------------------------------------------------------------------------
# Sector discovery: NAICS codes used to surface *new* contract recipients that
# are not yet in the universe (so the scanner can find the next INTC, not just
# re-score known names).
# ---------------------------------------------------------------------------
DISCOVERY_NAICS = [
    "334413",  # Semiconductor & Related Device Manufacturing
    "334111",  # Electronic Computer Manufacturing
    "334118",  # Computer Terminal & Peripheral Equipment
    "541512",  # Computer Systems Design Services
    "541511",  # Custom Computer Programming Services
    "511210",  # Software Publishers
    "336414",  # Guided Missile & Space Vehicle Manufacturing
    "336411",  # Aircraft Manufacturing
    "541330",  # Engineering Services
]


# ---------------------------------------------------------------------------
# Scoring weights. Deliberately ordered to AVOID chasing: the leading signals
# (a government stake, federal-revenue gravity) carry the score; the Trump
# shoutout itself is the lightest weight because by the time he speaks the rally
# is usually over. The shoutout confirms timing; it does not predict the move.
# Weights must sum to 1.0.
# ---------------------------------------------------------------------------
WEIGHTS = {
    "gov_stake": 0.30,        # Layer 1 -- strongest filter (the INTC model)
    "federal_revenue": 0.25,  # Layer 2 -- contracts / policy (DELL, PLTR, MU)
    "positioning": 0.20,      # Layer 3 -- options flow / insider / volume spike
    "exec_alignment": 0.15,   # Layer 5 -- the CEO publicly backs Trump
    "trump_mention": 0.10,    # Layer 4 -- timing confirmation only
}

# Lookback windows (days)
CONTRACT_LOOKBACK_DAYS = 120
NEWS_LOOKBACK_DAYS = 30
INSIDER_LOOKBACK_DAYS = 90

# Only the strongest preliminary candidates get the rate-limited Polygon
# options enrichment (free tier is 5 req/min).
POLYGON_TOP_N = 15


# ---------------------------------------------------------------------------
# Keyword banks
# ---------------------------------------------------------------------------
# Words that, near a company name, suggest the government is taking / weighing
# an equity position -- the single strongest signal in the playbook.
STAKE_TERMS = [
    '"equity stake"', '"government stake"', '"golden share"', '"warrant"',
    '"CHIPS Act"', '"strategic investment"', '"national security agreement"',
]

# Words in a headline that turn a neutral CEO+Trump co-mention into an
# actual show of alignment / praise.
PRAISE_TERMS = [
    "praise", "praises", "applaud", "thank", "thanks", "back", "backs",
    "support", "endorse", "endorses", "hails", "lauds", "ally", "dinner",
    "meeting", "pledge", "invest", "investment", "commits", "commitment",
]


def env_key(name: str) -> Optional[str]:
    """Read an API key from the environment (GitHub Secret), or None."""
    val = os.environ.get(name)
    return val.strip() if val and val.strip() else None


# Secret names the workflow forwards. Absent key -> that source is skipped and
# the scanner falls back to the free no-key path.
KEY_NEWSAPI = "NEWSAPI_KEY"
KEY_POLYGON = "POLYGON_API_KEY"
KEY_FINNHUB = "FINNHUB_API_KEY"
KEY_FMP = "FMP_API_KEY"
