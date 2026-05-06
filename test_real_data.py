"""
End-to-end integration test on REAL data.

Pulls live data from all three loaders, runs the full pipeline through
dashboard_core, writes four Plotly figures to figures/ as HTML, and prints
a text summary to stdout.

Run: python test_real_data.py
"""
from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd

from loaders.cme import fetch_full_strip
from loaders.fred import fetch_reference_rates
from loaders.fomc import upcoming_fomc_dates
from dashboard_core import (
    add_implied,
    plot_strip,
    build_meeting_path,
    meeting_probs,
    spread_matrix,
    plot_meeting_path,
    plot_cb_lvl,
    find_terminal,
)

FIGURES_DIR = REPO_ROOT / "figures"
FIGURES_DIR.mkdir(exist_ok=True)


def main() -> None:
    print("Fetching live data...")
    strip = fetch_full_strip()
    ref_rates = fetch_reference_rates(days=30)
    fomc_dates = upcoming_fomc_dates()

    OCR = float(ref_rates["effr"].iloc[-1])
    SOFR_SPOT = float(ref_rates["sofr"].iloc[-1])
    basis_bp = (SOFR_SPOT - OCR) * 100

    strip = add_implied(strip, OCR)
    sofr_strip = strip[strip["root"] == "SR3"].reset_index(drop=True)
    ff_strip = strip[strip["root"] == "ZQ"].reset_index(drop=True)

    fig_sofr = plot_strip(sofr_strip, OCR, "PRODUCTS · SOFR (SR3) STRIP")
    fig_ff = plot_strip(ff_strip, OCR, "PRODUCTS · FED FUNDS (ZQ) STRIP")

    path = build_meeting_path(ff_strip, OCR, fomc_dates)
    fig_path = plot_meeting_path(path, OCR)
    fig_cb = plot_cb_lvl(path, OCR)

    fig_sofr.write_html(FIGURES_DIR / "sofr_strip.html")
    fig_ff.write_html(FIGURES_DIR / "zq_strip.html")
    fig_path.write_html(FIGURES_DIR / "meeting_path.html")
    fig_cb.write_html(FIGURES_DIR / "cb_lvl.html")

    sofr_term = find_terminal(sofr_strip, OCR)
    ff_term = find_terminal(ff_strip, OCR)

    print()
    print("=" * 64)
    print("ANCHOR RATES")
    print("=" * 64)
    print(f"  EFFR  : {OCR:.4f}%")
    print(f"  SOFR  : {SOFR_SPOT:.4f}%")
    print(f"  basis : {basis_bp:+.1f} bp")

    print()
    print("=" * 64)
    print("STRIP SUMMARY")
    print("=" * 64)
    print(f"  SR3 contracts : {len(sofr_strip):>3}   "
          f"front {sofr_strip.iloc[0]['symbol']} "
          f"@ {sofr_strip.iloc[0]['implied_rate']:.3f}%   "
          f"terminal {sofr_term['symbol']} "
          f"@ {sofr_term['implied_rate']:.3f}%")
    print(f"  ZQ  contracts : {len(ff_strip):>3}   "
          f"front {ff_strip.iloc[0]['symbol']} "
          f"@ {ff_strip.iloc[0]['implied_rate']:.3f}%   "
          f"terminal {ff_term['symbol']} "
          f"@ {ff_term['implied_rate']:.3f}%")

    print()
    print("=" * 64)
    print("MEETING PATH (post-meeting implied rates)")
    print("=" * 64)
    if path.empty:
        print("  (no FOMC meetings within ZQ horizon)")
    else:
        path_view = path.copy()
        path_view["meeting"] = path_view["meeting"].astype(str)
        path_view["post_rate"] = path_view["post_rate"].round(4)
        path_view["cum_cuts"] = path_view["cum_cuts"].round(2)
        print(path_view.to_string(index=False))

        print()
        print("PROBABILITIES BY MEETING (CME-FedWatch style, %)")
        probs = pd.DataFrame(
            [meeting_probs(r, OCR) for r in path["post_rate"]],
            index=[d.isoformat() for d in path["meeting"]],
        ).round(1)
        print(probs.to_string())

    print()
    print("=" * 64)
    print("SPREAD MATRIX (ZQ, bp vs forward contract)")
    print("=" * 64)
    sm = spread_matrix(ff_strip, OCR)
    print(sm.to_string())

    print()
    print(f"Wrote figures to {FIGURES_DIR.relative_to(REPO_ROOT)}/")
    for name in ("sofr_strip.html", "zq_strip.html",
                 "meeting_path.html", "cb_lvl.html"):
        print(f"  {name}")


if __name__ == "__main__":
    main()
