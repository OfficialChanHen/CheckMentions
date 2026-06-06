# CheckMentions

An automated scanner that reverse-engineers the **"buy before Trump's shoutout"**
pattern into a checklist and ranks publicly traded companies by how strongly the
*leading* signals fire — **before** Trump ever mentions them.

The thesis (from the source brief): the shoutouts follow a three-act script —
*buy in low → talk it up publicly → let the government deliver a contract, a
stake, or policy that sweeps rivals away.* Chasing the shoutout means chasing a
rally that is usually already over. The edge is catching the next name from the
leading signals.

## The checklist (in order of how early it fires)

| Layer | Signal | Source | Weight |
|---|---|---|---|
| 1 🏛️ | Government holds / is negotiating an **equity stake** (the INTC model) | SEC EDGAR full-text + congressional buys (FMP) | 0.25 |
| 2 📑 | High **federal-revenue** share; policy clearing competition (DELL, PLTR, MU) | USASpending.gov | 0.20 |
| 3 📈 | **Unusual positioning** — options flow / insider buying / volume spikes / Trump's own holdings | Polygon, Finnhub/FMP, yfinance, OGE disclosures | 0.16 |
| 5 🤝 | **Executive alignment** — the CEO publicly backs / meets Trump (Mar-a-Lago, White House) | GDELT / NewsAPI | 0.12 |
| 8 📜 | **Executive Order** — a signed EO names the company directly (a leading policy signal) | Federal Register | 0.09 |
| 4 📣 | **Trump mention** — news co-mention, timing confirmation | GDELT / NewsAPI | 0.07 |
| 6 🔊 | **Truth Social** — Trump posts about the company on his own platform | truthsocial.com RSS | 0.07 |
| 7 💰 | **CEO donor** — FEC-verified donation from the CEO to a Trump campaign / PAC | FEC API | 0.04 |

The Trump shoutout (news co-mention / Truth Social) is deliberately a *light*
weight: it confirms timing, it does not predict the move. The heaviest weights
sit on the leading signals — a government stake, federal-revenue gravity, and a
company named directly in policy.

## How it runs

Two surfaces fire daily — Actions does the scan, a Claude routine does the brief.

**07:00 America/Los_Angeles — GitHub Actions** (`.github/workflows/daily-scan.yml`,
DST-aware via two UTC cron entries plus an idempotency guard):

1. Scores every company in `scanner/config.py` against the checklist.
2. Enriches the top names with Polygon options-flow and FEC CEO-donation data.
3. Discovers big recent federal-contract recipients **not** yet tracked
   (candidate "next INTC" names to review).
4. Commits `reports/<date>.md` to the repo **and** opens a summary GitHub Issue.
5. Runs `scanner/news.trump_positive_mentions()` — scans @realDonaldTrump's Truth
   Social RSS and "Trump praises X" news headlines, classifies each entity as
   tracked-or-untracked, and renders both tables in the report.

**07:30 America/Los_Angeles — Claude scheduled routine**
([claude.ai/code/routines](https://claude.ai/code/routines)):

6. Detects the fresh report Actions just committed and skips re-scanning.
   (If Actions failed, the routine runs its own scan in free-sources fallback mode.)
7. Diffs today's top 10 against the most recent prior report; flags single-layer
   collapses as API outages, not real signal moves.
8. Web-searches the top 3 candidates for last-48h news and notes whether news
   corroborates or contradicts each scanner signal.
9. Writes a **brief** (movers table + news check + data-quality flags) and an
   **Analysis & Recommendations** section (thesis-lifecycle classification,
   universe additions to consider, signal-calibration observations, data-quality
   fix priority, sector watch).
10. The brief is the routine's final chat message — visible in the Claude iOS
    app under **Code → Routines**.

Run either manually anytime: Actions tab → **Run workflow**, or
[claude.ai/code/routines](https://claude.ai/code/routines) → **Run now**.

## Data sources

Works out of the box on free, **no-key** sources: USASpending.gov, SEC EDGAR,
GDELT, yfinance, **Truth Social RSS**, and the **Federal Register** (Executive
Orders). FEC donation lookups also work key-free via `DEMO_KEY` (40 req/hr). Add
any of these free-tier keys as **repository secrets** to enrich the scan — each
one is optional and the scanner falls back gracefully if it is absent:

| Secret | Provider | Adds |
|---|---|---|
| `NEWSAPI_KEY` | [newsapi.org](https://newsapi.org) | Cleaner Trump / exec-praise news search |
| `POLYGON_API_KEY` | [polygon.io](https://polygon.io) | Options-flow proxy (Layer 3) |
| `FINNHUB_API_KEY` | [finnhub.io](https://finnhub.io) | Insider sentiment / transactions |
| `FMP_API_KEY` | [financialmodelingprep.com](https://financialmodelingprep.com) | Congressional + insider trading |
| `FEC_API_KEY` | [api.data.gov](https://api.data.gov/signup) | Faster CEO-donation lookups (100k/day vs. 40/hr) |

Set them under **Settings → Secrets and variables → Actions → New repository secret**.

## Local run

```bash
pip install -r requirements.txt
# optional: export NEWSAPI_KEY=... POLYGON_API_KEY=... etc.
python main.py
# -> writes reports/<today>.md
```

## Customizing

Edit `scanner/config.py`:
- **`UNIVERSE`** — add a company row. Fields:
  - `ticker`, `name`, `ceo`, `sector` — required.
  - `aliases` — extra names used for federal-contract matching.
  - `products` — distinctive products / programs Trump may reference *without*
    naming the company (e.g. `"Air Force One"` → BA, `"F-35"` → LMT,
    `"Ryzen"` → AMD). Truth Social and news scans treat these as company
    mentions. Only include strings unambiguous enough that a casual hit is
    almost certainly about the company — skip generic words ("Windows",
    "Patriot") to avoid false positives.
  - `confirmed_stake` — set to `True` once the government has *actually* taken
    or formally agreed to take an equity stake (the INTC model). When true,
    Layer 1 fires at max regardless of SEC / congress signals — the cleanest
    way to separate confirmed setups from speculative ones. Update by hand
    from primary sources (press release, EO, SC 13D).
  - The CEO name powers the executive-alignment and CEO-donor layers, so keep
    it current.
- **`WEIGHTS`** — re-weight the checklist layers (must sum to 1.0).
- **`DISCOVERY_NAICS`** — sector codes used to surface new contract recipients.
- **`TRUMP_KNOWN_HOLDINGS`** — tickers Trump personally holds (from his latest
  OGE financial disclosure); these boost the positioning layer.
- **`COMPANY_CONTEXT_TERMS`** (in `scanner/news.py`) — words that qualify a
  bare-name headline match as a legitimate company reference. The
  disambiguation filter blocks "[FirstName] [CompanyName]" personal-name
  matches (e.g. "Kane Parsons" the film director vs Parsons the contractor) —
  extend this set if a legitimate sector term is being filtered out.

Edit `scanner/government.py`:
- **`TRUMP_COMMITTEE_IDS`** / **`TRUMP_INAUGURAL_COMMITTEE_IDS`** — FEC committee
  IDs checked for CEO donations. Add the verified inaugural-committee ID here
  once confirmed at fec.gov.

Edit the Claude routine prompt:
- The brief's Analysis & Recommendations section lives in the routine config at
  [claude.ai/code/routines](https://claude.ai/code/routines). Update the prompt
  to tune what gets flagged (e.g. add custom guardrails, change the lifecycle
  taxonomy, expand sector-watch heuristics).

## Disclaimer

This is an automated **signal scan built from public data — not investment
advice**. Signals can be noisy, lagged, or wrong. Verify independently before
acting on anything here.
