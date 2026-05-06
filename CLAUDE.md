# STIR Dashboard - Project Context

## Goal
Replicate a CME FedWatch-style short-term interest rate dashboard for The Macro Chain (Substack + X). Output: a Streamlit app with two tabs (Products, Meetings) deployed on Streamlit Community Cloud, auto-refreshed daily via GitHub Actions.

## Source of truth
The file `Cfr_Stir_Replication_Playbook.pdf` in this directory is the canonical spec.
- Math: page 6 (implied rate), page 8 (day-weighted post-meeting rate), page 9 (probabilities), page 10 (spread matrix), page 12 (terminal detection)
- Schemas: page 5 (the three DataFrame contracts)
- Reference code: appendix A1-A6 (pages 15-20). This code is canonical and runs end-to-end on synthetic data. Treat the math and Plotly functions as fixed unless I explicitly say otherwise.

## What's in scope vs out
In scope:
- Replace the three `make_mock_*` functions in A2 with real data loaders
- Streamlit UI wrapping the four Plotly figures
- Daily GitHub Actions workflow that pulls data and commits to the repo

Out of scope:
- Changing the math or chart styles
- Building a database (parquet files in /data/ are sufficient)
- Intraday data (end-of-day settlements only)

## Data sources (all free)
- SR3 and ZQ daily settlements: scrape CME's public settlement pages
- EFFR and SOFR daily values: NY Fed CSV downloads (markets.newyorkfed.org)
- FOMC dates: hardcoded list, refreshed annually from federalreserve.gov

## Conventions
- Python 3.11+
- pandas, plotly, streamlit, requests, beautifulsoup4, pyarrow
- No em dashes anywhere in code comments or UI text
- Test each loader independently before integrating
- Commit data files (parquet) to the repo, this is intentional, do not gitignore /data/

## Budget constraint
Total monthly cost target is under $10. Prefer free tools always. Do not suggest paid data feeds or paid hosting unless free options are exhausted.

## How I work
I'm an intermediate Python user, comfortable with code review but not architecting from scratch. Claude Code is the implementer. When in doubt, build the simplest version that works and let me iterate.

## Known quirks
- `find_terminal()` in dashboard_core.py: behavior is undefined on the floating-point edge where the front contract's implied rate equals OCR exactly. The function uses `>=` to set `hiking`, so a fractional difference (3.639999... vs 3.6400) decides whether the strip is read as a hike-trough or cut-trough scan. In practice this never matters because real settles are rarely exactly on OCR, but worth knowing if a debugging run shows the terminal flipping unexpectedly when prices nudge by a fraction of a basis point.

## Phase 4: Daily auto-refresh (live)
- Source of truth in production is `data/` (committed parquet + json files), not live API calls.
- `scripts/refresh_data.py` calls every loader and writes their output to `data/`. Tolerates partial failures: one loader can fail and the rest still write; the script exits 0 unless every loader fails.
- `.github/workflows/refresh-data.yml` runs the script on cron `0 23 * * 1-5` (7pm ET weekdays) and commits any changes back to the repo. `FRED_API_KEY` is a repo secret.
- `app.py` reads from parquet first; if `data/strip.parquet` is absent it falls back to live loaders (the local-dev path).
- The "Last updated" indicator shows the parquet refresh time. Dot is green under 30 hours old, amber 30-72, red over 72 hours (workflow likely broken).

### Manual refresh
- From GitHub: Actions tab -> Refresh Data -> Run workflow.
- From local dev: `python scripts/refresh_data.py` then reload the Streamlit page.
- To test the live fallback: delete `data/` and reload; the dashboard should fetch live (slower first paint).

### `data/` vs `.cache/`
Both store recent values, but they have different jobs:
- `data/` is the production source of truth, regenerated daily, committed to the repo.
- `.cache/macro_last_good.json` is a local-dev safety net used by `macro_latest()` when running live loaders. It holds the most recent good value seen for each macro column so a transient FRED outage on T10YIE doesn't blank a metric card. Not committed.