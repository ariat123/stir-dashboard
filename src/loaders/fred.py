"""
FRED loader for EFFR, SOFR, and macro inflation/real-rate series.

Sign up for a free key at: https://fredaccount.stlouisfed.org/apikey
Set FRED_API_KEY environment variable, or pass api_key= to the function.

Output schemas match the canonical ref_rates schema on PDF page 5.
"""
from __future__ import annotations
import os
import pandas as pd
from fredapi import Fred


def _get_fred_client(api_key: str | None = None) -> Fred:
    api_key = api_key or os.environ.get("FRED_API_KEY")
    if not api_key:
        raise ValueError(
            "FRED API key required. Set FRED_API_KEY env var or pass api_key=. "
            "Get a free key at https://fredaccount.stlouisfed.org/apikey"
        )
    return Fred(api_key=api_key)


def fetch_reference_rates(
    api_key: str | None = None,
    days: int = 90,
) -> pd.DataFrame:
    """
    Fetch EFFR and SOFR from FRED for the last N days.

    Returns DataFrame indexed by business-day DatetimeIndex with columns:
    - effr: Effective Federal Funds Rate (%)
    - sofr: Secured Overnight Financing Rate (%)
    """
    fred = _get_fred_client(api_key)
    end = pd.Timestamp.today().normalize()
    start = end - pd.Timedelta(days=days)

    effr = fred.get_series("EFFR", observation_start=start, observation_end=end)
    sofr = fred.get_series("SOFR", observation_start=start, observation_end=end)

    df = pd.DataFrame({"effr": effr, "sofr": sofr})
    df = df.dropna(how="all").sort_index()

    if df.empty:
        raise RuntimeError("FRED returned no data for EFFR/SOFR in window")

    return df


# FRED ids for the macro series we expose to the dashboard
_MACRO_SERIES = {
    "real_10y":           "DFII10",  # 10y TIPS yield
    "breakeven_10y":      "T10YIE",  # 10y breakeven inflation
    "fwd_5y5y_inflation": "T5YIFR",  # 5y5y forward inflation expectation
    "jobless_claims":     "ICSA",    # Initial Claims (weekly, raw count)
}


def fetch_macro_series(
    api_key: str | None = None,
    days: int = 90,
) -> pd.DataFrame:
    """
    Fetch macro inflation/real-rate series from FRED.

    Returns DataFrame indexed by date with columns:
    - real_10y: 10-year TIPS yield (%)
    - breakeven_10y: 10-year breakeven inflation (%)
    - fwd_5y5y_inflation: 5y5y forward inflation expectation (%)

    Errors per series are tolerated: if a single series fails (FRED outage,
    series ID retired, etc.), that column is filled with NaN rather than
    raising. The dashboard degrades gracefully on partial outages. Failed
    series IDs are recorded in df.attrs['failed_series'] for diagnostics.
    """
    fred = _get_fred_client(api_key)
    end = pd.Timestamp.today().normalize()
    start = end - pd.Timedelta(days=days)

    out: dict[str, pd.Series] = {}
    failed: list[str] = []
    for col, fred_id in _MACRO_SERIES.items():
        try:
            out[col] = fred.get_series(
                fred_id, observation_start=start, observation_end=end
            )
        except Exception:
            out[col] = pd.Series(dtype=float)
            failed.append(fred_id)

    df = pd.DataFrame(out).sort_index()
    if failed:
        df.attrs["failed_series"] = failed
    return df


if __name__ == "__main__":
    df = fetch_reference_rates(days=30)
    print(f"Reference rates: {len(df)} business days of EFFR + SOFR")
    print(df.tail(5).to_string())
    latest = df.iloc[-1]
    print(
        f"\n  EFFR={latest['effr']:.4f}%  SOFR={latest['sofr']:.4f}%  "
        f"basis={(latest['sofr'] - latest['effr']) * 100:+.1f} bp"
    )

    print()
    macro = fetch_macro_series(days=30)
    print(f"Macro series: {len(macro)} rows")
    print(macro.tail(5).to_string())
    def latest_for(col):
        s = macro[col].dropna()
        return s.iloc[-1] if not s.empty else float("nan")

    def fmt_pct(v):
        return f"{v:.2f}%" if not pd.isna(v) else "—"

    def fmt_claims(v):
        return f"{int(v / 1000):d}k" if not pd.isna(v) else "—"

    if macro.attrs.get("failed_series"):
        print(f"\n  WARNING - failed FRED IDs: {macro.attrs['failed_series']}")
    print(
        f"\n  Real 10y={fmt_pct(latest_for('real_10y'))}  "
        f"Breakeven 10y={fmt_pct(latest_for('breakeven_10y'))}  "
        f"5y5y fwd={fmt_pct(latest_for('fwd_5y5y_inflation'))}  "
        f"Initial Claims={fmt_claims(latest_for('jobless_claims'))}"
    )
