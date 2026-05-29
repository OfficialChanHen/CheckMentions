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
| 1 🏛️ | Government holds / is negotiating an **equity stake** (the INTC model) | SEC EDGAR full-text + congressional buys (FMP) | 0.30 |
| 2 📑 | High **federal-revenue** share; policy clearing competition (DELL, PLTR, MU) | USASpending.gov | 0.25 |
| 3 📈 | **Unusual positioning** — options flow / insider buying / volume spikes | Polygon, Finnhub/FMP, yfinance | 0.20 |
| 4 🤝 | **Executive alignment** — the CEO publicly backs / invests alongside Trump | GDELT / NewsAPI | 0.15 |
| 5 📣 | **Trump mention** — timing confirmation, the *last* layer, not the first | GDELT / NewsAPI | 0.10 |

The Trump shoutout is deliberately the *lightest* weight: it confirms timing,
it does not predict the move.

## How it runs

A GitHub Actions workflow (`.github/workflows/daily-scan.yml`) fires every
morning at **07:00 America/Los_Angeles** (year-round, DST-aware), then:

1. Scores every company in `scanner/config.py` against the checklist.
2. Enriches the top names with Polygon options-flow data.
3. Discovers big recent federal-contract recipients **not** yet tracked
   (candidate "next INTC" names to review).
4. Commits `reports/<date>.md` to the repo **and** opens a summary GitHub Issue.

Run it manually anytime from the Actions tab (**Run workflow**).

## Data sources

Works out of the box on free, **no-key** sources: USASpending.gov, SEC EDGAR,
GDELT, and yfinance. Add any of these free-tier keys as **repository secrets**
to enrich the scan — each one is optional and the scanner falls back gracefully
if it is absent:

| Secret | Provider | Adds |
|---|---|---|
| `NEWSAPI_KEY` | [newsapi.org](https://newsapi.org) | Cleaner Trump / exec-praise news search |
| `POLYGON_API_KEY` | [polygon.io](https://polygon.io) | Options-flow proxy (Layer 3) |
| `FINNHUB_API_KEY` | [finnhub.io](https://finnhub.io) | Insider sentiment / transactions |
| `FMP_API_KEY` | [financialmodelingprep.com](https://financialmodelingprep.com) | Congressional + insider trading |

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
  CEO name powers the executive-alignment layer, so keep it current.
- **`WEIGHTS`** — re-weight the checklist layers (must sum to 1.0).
- **`DISCOVERY_NAICS`** — sector codes used to surface new contract recipients.

## Disclaimer

This is an automated **signal scan built from public data — not investment
advice**. Signals can be noisy, lagged, or wrong. Verify independently before
acting on anything here.
