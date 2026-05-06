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

Production data lives in `data/` as parquet files, refreshed daily by `.github/workflows/refresh-data.yml`. To refresh manually:

```
python scripts/refresh_data.py
```
