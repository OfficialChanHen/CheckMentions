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

A GitHub Actions workflow (`.github/workflows/daily-scan.yml`) fires every
morning at **07:00 America/Los_Angeles** (year-round, DST-aware), then:

1. Scores every company in `scanner/config.py` against the checklist.
2. Enriches the top names with Polygon options-flow and FEC CEO-donation data.
3. Discovers big recent federal-contract recipients **not** yet tracked
   (candidate "next INTC" names to review).
4. Commits `reports/<date>.md` to the repo **and** opens a summary GitHub Issue.

Run it manually anytime from the Actions tab (**Run workflow**).

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
- **`UNIVERSE`** — add a company row (ticker, name, CEO, sector, aliases). The
  CEO name powers the executive-alignment and CEO-donor layers, so keep it current.
- **`WEIGHTS`** — re-weight the checklist layers (must sum to 1.0).
- **`DISCOVERY_NAICS`** — sector codes used to surface new contract recipients.
- **`TRUMP_KNOWN_HOLDINGS`** — tickers Trump personally holds (from his latest
  OGE financial disclosure); these boost the positioning layer.

Edit `scanner/government.py`:
- **`TRUMP_COMMITTEE_IDS`** / **`TRUMP_INAUGURAL_COMMITTEE_IDS`** — FEC committee
  IDs checked for CEO donations. Add the verified inaugural-committee ID here
  once confirmed at fec.gov.

## Disclaimer

This is an automated **signal scan built from public data — not investment
advice**. Signals can be noisy, lagged, or wrong. Verify independently before
acting on anything here.
