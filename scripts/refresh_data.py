"""
Daily data refresh for the STIR dashboard.

Run by GitHub Actions on a daily cron. Calls each loader, writes results to
data/ as parquet/json. Tolerates partial failures: if one loader fails the
others still write and the script exits 0 with the failure recorded in
metadata. Exits non-zero only when every loader fails (so the workflow
still commits a stale-but-better-than-nothing data dir on a single
upstream outage).

Run locally:    python scripts/refresh_data.py
Run in CI:      .github/workflows/refresh-data.yml
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, date, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from loaders.cme import fetch_full_strip
from loaders.fred import fetch_reference_rates, fetch_macro_series
from loaders.fomc import FOMC_DATES
from loaders.econ_calendar import fetch_all_releases

DATA_DIR = REPO_ROOT / "data"


def _json_default(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    raise TypeError(f"not JSON-serializable: {type(o).__name__}")


def write_parquet(name: str, df) -> int:
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{name}.parquet"
    df.to_parquet(path, index=True)
    return path.stat().st_size


def write_json(name: str, data) -> int:
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{name}.json"
    path.write_text(json.dumps(data, default=_json_default, indent=2))
    return path.stat().st_size


def main() -> int:
    results: dict[str, str] = {}

    # 1. Strip - CME futures via yfinance
    try:
        df = fetch_full_strip()
        size = write_parquet("strip", df)
        results["strip"] = f"ok ({len(df)} rows, {size} bytes)"
        print(f"[refresh] strip: {len(df)} rows, {size} bytes")
    except Exception as e:
        results["strip"] = f"fail: {e}"
        print(f"[refresh] strip FAILED: {e}", file=sys.stderr)

    # 2. Reference rates - FRED EFFR + SOFR
    try:
        df = fetch_reference_rates(days=90)
        size = write_parquet("reference_rates", df)
        results["reference_rates"] = f"ok ({len(df)} rows, {size} bytes)"
        print(f"[refresh] reference_rates: {len(df)} rows, {size} bytes")
    except Exception as e:
        results["reference_rates"] = f"fail: {e}"
        print(f"[refresh] reference_rates FAILED: {e}", file=sys.stderr)

    # 3. Macro series - FRED inflation + claims (per-series tolerant internally)
    try:
        df = fetch_macro_series(days=90)
        size = write_parquet("macro_series", df)
        failed = df.attrs.get("failed_series") or []
        msg = f"ok ({len(df)} rows, {size} bytes)"
        if failed:
            msg += f" partial: {failed}"
        results["macro_series"] = msg
        print(f"[refresh] macro_series: {msg}")
    except Exception as e:
        results["macro_series"] = f"fail: {e}"
        print(f"[refresh] macro_series FAILED: {e}", file=sys.stderr)

    # 4. FOMC dates - hardcoded, write all (dashboard filters)
    try:
        size = write_json("fomc_dates", [d.isoformat() for d in FOMC_DATES])
        results["fomc_dates"] = f"ok ({len(FOMC_DATES)} dates, {size} bytes)"
        print(f"[refresh] fomc_dates: {len(FOMC_DATES)} dates")
    except Exception as e:
        results["fomc_dates"] = f"fail: {e}"
        print(f"[refresh] fomc_dates FAILED: {e}", file=sys.stderr)

    # 5. Econ releases - BLS + hardcoded BEA, write all (dashboard filters)
    try:
        rels = fetch_all_releases()
        size = write_json(
            "econ_releases",
            [(d.isoformat(), name, imp) for d, name, imp in rels],
        )
        results["econ_releases"] = f"ok ({len(rels)} entries, {size} bytes)"
        print(f"[refresh] econ_releases: {len(rels)} entries")
    except Exception as e:
        results["econ_releases"] = f"fail: {e}"
        print(f"[refresh] econ_releases FAILED: {e}", file=sys.stderr)

    # 6. Metadata - timestamp + per-loader status
    metadata = {
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "loaders": results,
    }
    write_json("refresh_metadata", metadata)
    print(f"[refresh] metadata written -> {metadata['refreshed_at']}")

    successes = sum(1 for v in results.values() if v.startswith("ok"))
    print(f"[refresh] {successes}/{len(results)} loaders succeeded")
    return 0 if successes > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
