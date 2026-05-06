# ── A1 · IMPORTS, PALETTE, SCHEMAS ──────────────────────────────────────────
from __future__ import annotations
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
import numpy as np, pandas as pd
import plotly.graph_objects as go

# Brand palette — used by every Plotly figure further down.
CFR = {
    "bg":     "#000000", "panel":     "#080808", "rule":      "#3D2510",
    "orange": "#FE7C04", "orangeHot": "#FF9533", "orangeDim": "#5A2C00",
    "text":   "#D0D0D0", "green":     "#00E676", "red":       "#FF1744",
}

# CME month-code map → builds public-standard symbols (e.g. SR3M5, ZQK6).
_CME_MONTH_CODES = {1:"F",2:"G",3:"H",4:"J",5:"K",6:"M",
                    7:"N",8:"Q",9:"U",10:"V",11:"X",12:"Z"}

def _cme_symbol(root: str, expiry: date) -> str:
    return f"{root}{_CME_MONTH_CODES[expiry.month]}{expiry.year % 10}"


# Single contract (one row in the strip DataFrame).
@dataclass
class Contract:
    symbol: str   # e.g. "SR3M5", "ZQK6"
    root:   str   # "SR3" (3-month SOFR) or "ZQ" (30-day Fed Funds)
    expiry: date  # last day of the contract month
    settle: float # last settlement price (e.g. 95.42)


def to_strip(contracts: list[Contract]) -> pd.DataFrame:
    """Wrap a list of Contract into the canonical strip DataFrame."""
    return pd.DataFrame([c.__dict__ for c in contracts])


# ── A2 · SYNTHETIC DATA — REPLACE with your provider's loaders ──────────────
# Three loaders. Output schemas are documented on slide 5 of the playbook.
# Drop in your data feed (Refinitiv, Polygon, IBKR, CME DataMine, CSVs, …)
# and produce DataFrames with the same column names — every other line
# in this appendix stays identical.

def make_mock_strip(today: date) -> pd.DataFrame:
    contracts: list[Contract] = []
    # SOFR 3-month future — quarterly listings out two years
    sr3_months = [(today.year + (today.month + i*3 - 1) // 12,
                   ((today.month - 1 + i*3) % 12) + 1) for i in range(8)]
    sr3_rates = [4.20, 4.05, 3.92, 3.75, 3.55, 3.42, 3.50, 3.62]
    for (y, m), r in zip(sr3_months, sr3_rates):
        qm = next(q for q in (3,6,9,12) if q >= m) if m not in (3,6,9,12) else m
        exp = date(y, qm, monthrange(y, qm)[1])
        contracts.append(Contract(_cme_symbol("SR3", exp), "SR3", exp, 100.0 - r))
    # Fed Funds 30-day future — monthly listings out 18 months
    for i, r in enumerate(np.linspace(4.30, 3.30, 18) + np.random.normal(0, 0.015, 18)):
        m = ((today.month - 1 + i) % 12) + 1
        y = today.year + (today.month + i - 1) // 12
        exp = date(y, m, monthrange(y, m)[1])
        contracts.append(Contract(_cme_symbol("ZQ", exp), "ZQ", exp, 100.0 - r))
    return to_strip(contracts).sort_values(["root", "expiry"]).reset_index(drop=True)


def make_mock_ref_rates(today: date, days: int = 90) -> pd.DataFrame:
    """EFFR + SOFR daily reference rates (NY Fed publishes these as CSVs)."""
    idx = pd.bdate_range(end=today, periods=days)
    effr = pd.Series(4.33, index=idx) + np.random.normal(0, 0.005, days)
    sofr = effr + np.random.normal(0.005, 0.005, days)   # tiny basis
    return pd.DataFrame({"effr": effr, "sofr": sofr})


def make_mock_fomc_dates(today: date) -> list[date]:
    """Hand-maintained: refresh from federalreserve.gov each year."""
    cursor, out = today + timedelta(days=15), []
    for _ in range(8):
        out.append(cursor); cursor = cursor + timedelta(days=46)
    return out


# ── A3 · IMPLIED RATE · TERMINAL · STRIP VIEW ────────────────────────────────
def implied_rate(settle: float) -> float:
    return 100.0 - settle


def add_implied(strip: pd.DataFrame, ocr: float) -> pd.DataFrame:
    out = strip.copy()
    out["implied_rate"] = 100.0 - out["settle"]
    out["vs_ocr_bp"]    = (out["implied_rate"] - ocr) * 100.0
    return out


def find_terminal(strip_view: pd.DataFrame, ocr: float) -> pd.Series:
    """First peak (hiking) or trough (cutting) on the strip relative to OCR."""
    active = strip_view[strip_view["settle"] > 0].reset_index(drop=True)
    if active.empty:
        return strip_view.iloc[0]
    front = active.iloc[0]
    hiking = front["implied_rate"] >= ocr
    best   = front
    for _, row in active.iloc[1:].iterrows():
        if hiking and row["implied_rate"] >= best["implied_rate"]:
            best = row
        elif not hiking and row["implied_rate"] <= best["implied_rate"]:
            best = row
        else:
            break
    return best


def plot_strip(strip_view: pd.DataFrame, ocr: float, title: str) -> go.Figure:
    term = find_terminal(strip_view, ocr)
    colors = [CFR["orangeHot"] if s == term["symbol"] else CFR["orangeDim"]
              for s in strip_view["symbol"]]
    fig = go.Figure(go.Bar(
        x=strip_view["symbol"], y=strip_view["implied_rate"],
        marker_color=colors, marker_line_color="#9A4A02",
        hovertemplate="%{x}<br>%{y:.3f}%<extra></extra>",
    ))
    fig.add_hline(
        y=ocr, line_dash="dash", line_color=CFR["orange"],
        annotation_text="EFFECTIVE FFR", annotation_position="right",
        annotation_font=dict(color=CFR["orange"], family="Segoe UI"),
    )
    fig.update_layout(
        title=dict(text=title, font=dict(color=CFR["orange"], family="Bahnschrift", size=20)),
        template="plotly_dark", paper_bgcolor=CFR["bg"], plot_bgcolor="#050505",
        font=dict(family="Segoe UI", color=CFR["text"]),
        yaxis_title="Implied rate (%)", xaxis_title=None,
        margin=dict(l=60, r=20, t=60, b=40), height=420,
    )
    return fig


# ── A4 · MEETING-PATH MATH · PROBABILITIES ───────────────────────────────────
def post_meeting_rate(contract_rate: float, prev_rate: float,
                      meeting_day: int, days_in_month: int) -> float:
    """Recover the rate priced for the period AFTER an FOMC meeting from the
    monthly-average ZQ contract. monthly_avg = ((D-1)*prev + (N-D+1)*post) / N"""
    days_after = days_in_month - meeting_day + 1
    if days_after <= 0:
        return contract_rate
    return (contract_rate * days_in_month - (meeting_day - 1) * prev_rate) / days_after


def build_meeting_path(zq_strip: pd.DataFrame, effr_today: float,
                       fomc_dates: list[date]) -> pd.DataFrame:
    zq_by_month = {(r["expiry"].year, r["expiry"].month): r["implied_rate"]
                   for _, r in zq_strip.iterrows()}
    fomc_keys = {(d.year, d.month) for d in fomc_dates}
    prev = effr_today
    rows: list[dict] = []
    for d in fomc_dates:
        rate = zq_by_month.get((d.year, d.month))
        if rate is None:
            continue
        N = monthrange(d.year, d.month)[1]
        ny, nm = (d.year + (d.month == 12), d.month % 12 + 1)
        next_rate = zq_by_month.get((ny, nm))
        next_has_meeting = (ny, nm) in fomc_keys
        if next_rate is not None and not next_has_meeting:
            post = next_rate                                 # next-month shortcut
        else:
            post = post_meeting_rate(rate, prev, d.day, N)
        rows.append({"meeting": d, "post_rate": post,
                     "cum_cuts": (effr_today - post) / 0.25})
        prev = post
    return pd.DataFrame(rows)


def meeting_probs(post_rate: float, effr: float) -> dict[str, float]:
    """CME-FedWatch-style P(target rate) — interpolation between 25 bp levels."""
    raw = (effr - post_rate) / 0.25
    lower = int(np.floor(raw))
    frac = raw - lower
    mass: dict[int, float] = {lower: 1 - frac}
    if frac > 0.001:
        mass[lower + 1] = frac
    return {"hold":   100 * mass.get(0, 0.0),
            "cut25": 100 * mass.get(1, 0.0),
            "cut50": 100 * mass.get(2, 0.0),
            "cut75": 100 * mass.get(3, 0.0),
            "hike25": 100 * mass.get(-1, 0.0)}


# ── A5 · SPREAD MATRIX · MEETING-PATH PLOT · CB LVL OVERLAY ──────────────────
def spread_matrix(strip_view: pd.DataFrame, ocr: float,
                  horizons_m: tuple[int, ...] = (3, 6, 9, 12)) -> pd.DataFrame:
    if strip_view.empty:
        return pd.DataFrame()
    rows: list[dict] = []
    for _, row in strip_view.iterrows():
        row_mo = row["expiry"].month + 12 * row["expiry"].year
        spreads: dict[str, float] = {}
        for h in horizons_m:
            target = row_mo + h
            forward = strip_view[strip_view["expiry"].apply(
                lambda d: d.month + 12 * d.year >= target)]
            spreads[f"+{h}M"] = (round((forward.iloc[0]["implied_rate"]
                                        - row["implied_rate"]) * 100)
                                  if not forward.empty else float("nan"))
        rows.append({"contract": row["symbol"], **spreads})
    return pd.DataFrame(rows).set_index("contract")


def plot_meeting_path(path: pd.DataFrame, effr: float) -> go.Figure:
    fig = go.Figure(go.Scatter(
        x=path["meeting"], y=path["post_rate"], mode="lines+markers",
        line=dict(color=CFR["orangeHot"], width=2.4, shape="hv"),
        marker=dict(color=CFR["bg"],
                    line=dict(color=CFR["orangeHot"], width=1.5), size=8),
    ))
    fig.add_hline(y=effr, line_dash="dash", line_color=CFR["orange"],
                  annotation_text="EFFECTIVE FFR", annotation_position="right",
                  annotation_font=dict(color=CFR["orange"]))
    fig.update_layout(template="plotly_dark", paper_bgcolor=CFR["bg"],
                      plot_bgcolor="#050505",
                      font=dict(family="Segoe UI", color=CFR["text"]),
                      margin=dict(l=60, r=40, t=60, b=40), height=420)
    return fig


def cb_levels(effr: float, band_bp: int = 100, step_bp: int = 25) -> list[float]:
    settle = round(effr / 0.25) * 0.25
    n = band_bp // step_bp
    return [settle + (i - n) * (step_bp / 100.0) for i in range(2 * n + 1)]


def plot_cb_lvl(path: pd.DataFrame, effr: float) -> go.Figure:
    fig    = plot_meeting_path(path, effr)
    settle = round(effr / 0.25) * 0.25
    for lv in cb_levels(effr, band_bp=150):
        is_settle = abs(lv - settle) < 0.01
        fig.add_hline(
            y=lv,
            line_color=CFR["orange"] if is_settle else CFR["orangeDim"],
            line_dash="solid" if is_settle else "dot",
            line_width=1.4 if is_settle else 0.6,
        )
    return fig


# ── A6 · END-TO-END DRIVER ───────────────────────────────────────────────────
# Concatenate appendices A1-A5 above into a single .py file, then run this driver.
# To plug in your data provider, replace the three make_mock_* calls in step 1.

def main():
    np.random.seed(42)
    TODAY = date.today()

    # 1. Load inputs ── REPLACE these three lines with your provider's loaders ──
    strip      = make_mock_strip(TODAY)
    ref_rates = make_mock_ref_rates(TODAY)
    fomc_dates = make_mock_fomc_dates(TODAY)

    # 2. Anchor rates
    OCR = float(ref_rates["effr"].iloc[-1])
    SOFR = float(ref_rates["sofr"].iloc[-1])
    print(f"OCR (EFFR) today: {OCR:.4f}%   SOFR spot: {SOFR:.4f}%      "
          f"basis {(SOFR-OCR)*100:+.1f} bp")

    # 3. Decorate strip + split by product
    strip      = add_implied(strip, OCR)
    sofr_strip = strip[strip["root"] == "SR3"].reset_index(drop=True)
    ff_strip   = strip[strip["root"] == "ZQ"].reset_index(drop=True)

    # 4. PRODUCTS tab — strip views (toggleable in your UI)
    plot_strip(sofr_strip, OCR, "PRODUCTS · SOFR (SR3) STRIP").show()
    plot_strip(ff_strip,   OCR, "PRODUCTS · FED FUNDS (ZQ) STRIP").show()

    # 5. MEETINGS · STRIP — implied post-meeting rate path
    path = build_meeting_path(ff_strip, OCR, fomc_dates)
    plot_meeting_path(path, OCR).show()

    # 6. MEETINGS · STRIP — probability table
    probs_df = pd.DataFrame(
        [meeting_probs(r, OCR) for r in path["post_rate"]],
        index=[d.isoformat() for d in path["meeting"]],
    ).round(1)
    print(probs_df)

    # 7. MEETINGS · SPREADS — calendar matrix
    print(spread_matrix(ff_strip, OCR))

    # 8. MEETINGS · CB LVL — meeting path overlaid with policy rails
    plot_cb_lvl(path, OCR).show()


if __name__ == "__main__":
    main()
