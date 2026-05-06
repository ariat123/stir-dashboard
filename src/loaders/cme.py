"""
CME futures loader using Yahoo Finance as data source.

Pivot rationale: CME's unofficial CmeWS endpoint structure changed in 2026.
The old /CmeWS/mvc/Quotes/Future/{productId}/G path returns 404 even after
bypassing TLS fingerprinting. Rather than reverse-engineer a moving target,
we use Yahoo Finance which:
  - has individual contract coverage for both ZQ and SR3
  - is maintained by a popular Python library (yfinance, 17k+ stars)
  - is delayed ~15 min but matches CME settlement after market close
  - requires no API key, no bot mitigation, no User-Agent tricks

Yahoo ticker patterns:
  ZQK26.CBT  - May 2026 Fed Funds (suffix .CBT for CBOT-listed)
  SR3M26.CME - June 2026 SOFR    (suffix .CME for CME-listed, quarterly only)

Output schema matches the canonical Contract dataclass on PDF page 5:
DataFrame with columns: symbol, root, expiry, settle.
"""
from __future__ import annotations
import contextlib
import os
import sys
import yfinance as yf
import pandas as pd
from datetime import date
from calendar import monthrange


@contextlib.contextmanager
def _silence_stderr():
    """Suppress yfinance's chatter on tickers we already filter out.

    yfinance emits 'possibly delisted', 'connection timed out', and
    'Failed downloads' summaries to stderr (some via Python's stderr,
    some via the raw fd). We dup-redirect both so a successful run
    produces no stderr noise. Exceptions raised by yf.download still
    propagate normally; only writes are dropped.
    """
    saved_fd = os.dup(2)
    devnull = open(os.devnull, "w")
    saved_sys_stderr = sys.stderr
    try:
        os.dup2(devnull.fileno(), 2)
        sys.stderr = devnull
        yield
    finally:
        sys.stderr = saved_sys_stderr
        os.dup2(saved_fd, 2)
        os.close(saved_fd)
        devnull.close()

# CME month codes
MONTH_CODES = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}

# Yahoo's exchange suffix per root
EXCHANGE_SUFFIX = {
    "ZQ": "CBT",   # ZQ trades on CBOT
    "SR3": "CME",  # SR3 trades on CME
}

# Listing patterns: which months trade, how far out
# ZQ: monthly contracts listed 36 months out (we fetch 24 to keep tickers reasonable)
# SR3: quarterly only (March H, June M, Sep U, Dec Z), listed many years out (fetch 30 months)
LISTING_PATTERNS = {
    "ZQ": {"months": list(range(1, 13)), "horizon_months": 24},
    "SR3": {"months": [3, 6, 9, 12], "horizon_months": 30},
}


def _cme_short_symbol(root: str, expiry: date) -> str:
    """
    Build canonical CME-style symbol with single-digit year (e.g. 'ZQK6').
    Matches the synthetic data convention in the PDF appendix.
    """
    return f"{root}{MONTH_CODES[expiry.month]}{expiry.year % 10}"


def _yahoo_ticker(root: str, expiry: date) -> str:
    """Build Yahoo Finance ticker (e.g. 'ZQK26.CBT')."""
    suffix = EXCHANGE_SUFFIX[root]
    month_letter = MONTH_CODES[expiry.month]
    year_2digit = f"{expiry.year % 100:02d}"
    return f"{root}{month_letter}{year_2digit}.{suffix}"


def _expected_contracts(root: str, today: date) -> list[tuple[date, str, str]]:
    """
    Generate expected contract list for a root.
    Returns list of (expiry_date, yahoo_ticker, cme_symbol) tuples.
    """
    config = LISTING_PATTERNS[root]
    valid_months = set(config["months"])
    horizon = config["horizon_months"]

    out: list[tuple[date, str, str]] = []
    year, month = today.year, today.month
    for offset in range(horizon + 1):
        m = ((month - 1 + offset) % 12) + 1
        y = year + (month - 1 + offset) // 12
        if m not in valid_months:
            continue
        expiry = date(y, m, monthrange(y, m)[1])
        if expiry < today:
            continue
        out.append((
            expiry,
            _yahoo_ticker(root, expiry),
            _cme_short_symbol(root, expiry),
        ))
    return out


def fetch_cme_strip(root: str = "ZQ") -> pd.DataFrame:
    """
    Fetch the strip of futures contracts via Yahoo Finance.

    Returns DataFrame with columns: symbol, root, expiry, settle.
    `settle` is the most recent valid Close in price space (e.g. 95.42).
    """
    if root not in EXCHANGE_SUFFIX:
        raise ValueError(
            f"Unknown root {root!r}. Expected: {list(EXCHANGE_SUFFIX.keys())}"
        )

    today = date.today()
    expected = _expected_contracts(root, today)
    if not expected:
        raise RuntimeError(f"No expected contracts for {root}")

    tickers = [t for _, t, _ in expected]
    meta = {t: (e, s) for e, t, s in expected}  # ticker -> (expiry, cme_symbol)

    # Batch download last 5 days to handle weekends and holidays.
    # stderr silenced because yfinance prints warnings for delisted/missing
    # tickers we already filter out below.
    with _silence_stderr():
        df_raw = yf.download(
            tickers,
            period="5d",
            interval="1d",
            progress=False,
            auto_adjust=False,
            group_by="ticker",
            threads=True,
        )

    if df_raw is None or df_raw.empty:
        raise RuntimeError(f"yfinance returned no data for {root}")

    rows: list[dict] = []
    for ticker in tickers:
        # When multiple tickers requested, columns are MultiIndex: (ticker, field)
        try:
            if isinstance(df_raw.columns, pd.MultiIndex):
                ticker_data = df_raw[ticker]
            else:
                ticker_data = df_raw
        except KeyError:
            continue

        if ticker_data.empty:
            continue

        closes = ticker_data["Close"].dropna()
        if closes.empty:
            continue

        latest_close = float(closes.iloc[-1])
        if latest_close <= 0:
            continue

        expiry, cme_symbol = meta[ticker]
        rows.append({
            "symbol": cme_symbol,
            "root": root,
            "expiry": expiry,
            "settle": latest_close,
        })

    if not rows:
        raise RuntimeError(
            f"No valid contracts fetched for {root}. "
            f"Tried {len(tickers)} tickers, all empty. "
            f"Sample tickers: {tickers[:3]}"
        )

    df = pd.DataFrame(rows).sort_values("expiry").reset_index(drop=True)
    return df


def fetch_full_strip() -> pd.DataFrame:
    """Fetch both ZQ and SR3 strips and concatenate."""
    sr3 = fetch_cme_strip("SR3")
    zq = fetch_cme_strip("ZQ")
    return pd.concat([sr3, zq], ignore_index=True)


if __name__ == "__main__":
    print("Fetching ZQ strip via Yahoo Finance...")
    zq = fetch_cme_strip("ZQ")
    print(f"  Got {len(zq)} ZQ contracts")
    print(zq.head(8).to_string(index=False))
    print(f"  Implied front-month rate: {100 - zq.iloc[0]['settle']:.3f}%")

    print("\nFetching SR3 strip via Yahoo Finance...")
    sr3 = fetch_cme_strip("SR3")
    print(f"  Got {len(sr3)} SR3 contracts")
    print(sr3.head(8).to_string(index=False))
    print(f"  Implied front-quarter rate: {100 - sr3.iloc[0]['settle']:.3f}%")
