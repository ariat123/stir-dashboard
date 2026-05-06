# STIR Dashboard

A CME-FedWatch-style short-term interest rate dashboard. SOFR and Fed Funds futures strips, implied post-meeting Fed path, calendar spreads, 25 bp policy rails, plus real rates, inflation expectations, and upcoming economic releases.

Built for macro research. Data refreshed daily via GitHub Actions.

## Stack

- Streamlit + Plotly for the UI
- FRED API for rates and macro series
- yfinance for futures
- BLS .ics feed for the economic calendar
- GitHub Actions for daily auto-refresh at 7pm ET

## Local development

1. Clone the repo
2. Create a virtualenv: `python -m venv .venv && source .venv/bin/activate`
3. Install: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and add your `FRED_API_KEY`
5. Run: `streamlit run app.py`

## Data refresh

Production data lives in `data/` as parquet files, refreshed daily by `.github/workflows/refresh-data.yml`. Three ways to refresh:

1. **Daily auto** — workflow runs at 23:00 UTC (7pm ET) Mon-Fri.
2. **Manual via GitHub** — Actions tab → Refresh Data → Run workflow.
3. **In-app button** — sidebar "Trigger refresh" calls the GitHub API to dispatch the workflow remotely. Requires `GITHUB_PAT` in Streamlit secrets (see below).
4. **Local CLI** — `python scripts/refresh_data.py`

### Streamlit secrets

The in-app refresh button needs a GitHub Personal Access Token with permission to dispatch workflows on this repo.

- **Local dev**: copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and paste the token.
- **Streamlit Cloud**: Settings → Secrets, paste the same TOML content.

Required PAT scope:
- **Fine-grained**: repo access to `stir-dashboard`, permission `Actions: Read and write`.
- **Classic**: full `repo` scope.

Create one at https://github.com/settings/tokens. The real token must never be committed (the gitignore covers `.streamlit/secrets.toml` and `.env`).
