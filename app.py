"""STIR Dashboard - Streamlit UI.

Two-tab dashboard wrapping the validated data layer + dashboard_core figures.
Run: streamlit run app.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from datetime import date, datetime, timedelta, timezone

REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_DIR = REPO_ROOT / "data"
_LAST_GOOD_FILE = REPO_ROOT / ".cache" / "macro_last_good.json"

import pandas as pd
import streamlit as st

from loaders.cme import fetch_full_strip
from loaders.fred import fetch_reference_rates, fetch_macro_series
from loaders.fomc import upcoming_fomc_dates
from loaders.econ_calendar import fetch_all_releases
from dashboard_core import (
    add_implied,
    build_meeting_path,
    find_terminal,
    meeting_probs,
    plot_cb_lvl,
    plot_meeting_path,
    plot_strip,
    spread_matrix,
)

st.set_page_config(
    page_title="STIR Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed",
)

PLOT_CFG = {"displayModeBar": False}


# ────────────────────────────────────────────────────────────────────
# CSS injection
# ────────────────────────────────────────────────────────────────────

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Lora:wght@600;700&family=IBM+Plex+Mono:wght@400;500;600;700&family=Inter:wght@300;400;500&display=swap');

#MainMenu {visibility: hidden;}
header[data-testid="stHeader"] {display: none;}
footer {visibility: hidden;}
.stDeployButton {display: none;}
[data-testid="stStatusWidget"] {display: none;}
[data-testid="stToolbar"] {display: none;}

.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background-color: #000000;
}

.main .block-container,
[data-testid="stMainBlockContainer"] {
    max-width: 1400px;
    padding-top: 2rem;
    padding-bottom: 3rem;
}

/* Header section */
.eyebrow {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    color: #FE7C04;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    margin: 0 0 0.6rem 0;
    font-weight: 500;
}
.page-title {
    font-family: 'Playfair Display', 'Lora', Georgia, serif !important;
    font-size: 3rem;
    color: #F5F5F5 !important;
    font-weight: 700;
    margin: 0 0 0.75rem 0 !important;
    line-height: 1;
    letter-spacing: -0.02em;
}
.page-desc {
    font-family: 'Inter', sans-serif;
    color: #888;
    font-size: 0.95rem;
    max-width: 720px;
    line-height: 1.55;
    margin: 0 0 0.5rem 0;
}
.last-updated-right {
    text-align: right;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    color: #888;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding-top: 0.6rem;
    line-height: 1.4;
}
.last-updated-right .dot {
    font-size: 0.85rem;
    margin-right: 0.4rem;
    vertical-align: middle;
}
.last-updated-right .ts-label { color: #555; }
.last-updated-right .ts-value { color: #B0B0B0; margin-left: 0.4rem; }

.divider-rule {
    border: 0;
    border-top: 1px solid #1A1A1A;
    margin: 0.4rem 0 1.5rem 0;
}

.section-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: #FE7C04;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    margin: 0.5rem 0 0.75rem 0;
    font-weight: 500;
}

/* Metric cards */
.metric-card {
    border: 1px solid #1A1A1A;
    border-radius: 4px;
    padding: 1rem 1rem;
    background-color: #060606;
    height: 100%;
    min-height: 116px;
    transition: border-color 0.15s;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}
.metric-card:hover { border-color: #2A2A2A; }
.metric-card .label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    color: #888;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 0.4rem;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.metric-card .value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.65rem;
    color: #F0F0F0;
    font-weight: 700;
    line-height: 1.1;
    letter-spacing: -0.01em;
}
.metric-card .caption {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    color: #666;
    margin-top: 0.4rem;
    letter-spacing: 0.02em;
    line-height: 1.3;
}

/* Upcoming-data release cards */
.release-card {
    border: 1px solid #1A1A1A;
    border-left: 3px solid #2A2A2A;
    border-radius: 4px;
    padding: 0.65rem 0.85rem;
    background-color: #050505;
    height: 100%;
    min-height: 88px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}
.release-card.high { border-left-color: #FE7C04; }
.release-card.medium { border-left-color: #888; }
.release-card.low { border-left-color: #444; }
.release-card .date {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.85rem;
    font-weight: 700;
    color: #F0F0F0;
    letter-spacing: 0.04em;
}
.release-card .name {
    font-family: 'Inter', sans-serif;
    font-size: 0.78rem;
    color: #B0B0B0;
    margin: 0.25rem 0 0.4rem;
    line-height: 1.3;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
}
.release-card .days {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.62rem;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 0.1em;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    border-bottom: 1px solid #1A1A1A;
    background-color: transparent;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: #888 !important;
    padding: 0.85rem 1.6rem !important;
    font-family: 'IBM Plex Mono', monospace !important;
    text-transform: uppercase;
    letter-spacing: 0.14em !important;
    font-size: 0.85rem !important;
    font-weight: 500;
    border-bottom: 2px solid transparent;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] { color: #FE7C04 !important; }
.stTabs [data-baseweb="tab-highlight"] {
    background-color: #FE7C04 !important;
    height: 2px !important;
}
.stTabs [data-baseweb="tab-border"] { background-color: #1A1A1A !important; }

[data-testid="stCaptionContainer"],
.stCaption {
    font-family: 'IBM Plex Mono', monospace !important;
    color: #888 !important;
    font-size: 0.78rem !important;
    letter-spacing: 0.04em;
}
[data-testid="stCaptionContainer"] strong,
.stCaption strong {
    color: #E0E0E0 !important;
    font-weight: 700;
}

h1, h2, h3, h4, h5, h6 {
    font-family: 'Playfair Display', Georgia, serif !important;
    color: #F0F0F0 !important;
}

.stRadio > div { background: transparent; gap: 0.5rem; }
.stRadio label {
    font-family: 'IBM Plex Mono', monospace !important;
    color: #888 !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.78rem !important;
}

[data-testid="stDataFrame"] {
    background: #060606;
    border: 1px solid #1A1A1A;
    border-radius: 4px;
}

[data-testid="stSidebar"] {
    background-color: #050505;
    border-right: 1px solid #1A1A1A;
}

div[data-testid="stPlotlyChart"] {
    border: 1px solid #1F1F1F;
    border-radius: 4px;
    background: #050505;
    padding: 4px;
}

/* Hide Streamlit's auto-generated anchor link icons next to headings */
.stMarkdown h1 a, .stMarkdown h2 a, .stMarkdown h3 a, .stMarkdown h4 a,
[data-testid="stHeading"] a[href^="#"],
[data-testid="stHeadingWithActionElements"] a[href^="#"] {
    display: none !important;
}

/* Segmented control (st.segmented_control) styling */
[data-testid="stSegmentedControl"] {
    margin-bottom: 0.5rem;
}
[data-testid="stSegmentedControl"] button,
[data-testid="stSegmentedControl"] [role="radio"],
[data-testid="stSegmentedControl"] label {
    background-color: #0A0A0A !important;
    color: #888 !important;
    border: 1px solid #1F1F1F !important;
    font-family: 'IBM Plex Mono', monospace !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
    font-size: 0.78rem !important;
    padding: 0.5rem 1.2rem !important;
    transition: background-color 0.15s, color 0.15s;
}
[data-testid="stSegmentedControl"] button[aria-pressed="true"],
[data-testid="stSegmentedControl"] button[aria-checked="true"],
[data-testid="stSegmentedControl"] [role="radio"][aria-checked="true"],
[data-testid="stSegmentedControl"] label[data-baseweb="checkbox"][aria-checked="true"] {
    background-color: #FE7C04 !important;
    color: #000000 !important;
    border-color: #FE7C04 !important;
}
[data-testid="stSegmentedControl"] button:hover:not([aria-pressed="true"]):not([aria-checked="true"]) {
    background-color: #1A1A1A !important;
    color: #B0B0B0 !important;
    border-color: #2A2A2A !important;
}

.stAlert {
    background-color: #100805 !important;
    color: #D0D0D0 !important;
    border-left-color: #FE7C04 !important;
}
</style>
""",
    unsafe_allow_html=True,
)


# ────────────────────────────────────────────────────────────────────
# Data loading: parquet-first, live-fallback
# ────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=600)
def load_data():
    """Read from data/ parquet+json. Falls back to live loaders if data
    files are missing (local dev). Returns:
        strip, rates, macro, fomc, all_releases, metadata
    where metadata is a dict with 'refreshed_at' (ISO 8601) and 'source'
    ('disk' or 'live').
    """
    p_strip = DATA_DIR / "strip.parquet"
    if p_strip.exists():
        strip = pd.read_parquet(p_strip)
        rates = pd.read_parquet(DATA_DIR / "reference_rates.parquet")
        macro = pd.read_parquet(DATA_DIR / "macro_series.parquet")

        fomc_raw = json.loads((DATA_DIR / "fomc_dates.json").read_text())
        today = date.today()
        fomc = sorted(date.fromisoformat(s) for s in fomc_raw if date.fromisoformat(s) >= today)

        rels_raw = json.loads((DATA_DIR / "econ_releases.json").read_text())
        releases = [(date.fromisoformat(d), n, i) for d, n, i in rels_raw]

        metadata = json.loads((DATA_DIR / "refresh_metadata.json").read_text())
        metadata["source"] = "disk"
        return strip, rates, macro, fomc, releases, metadata

    # Dev fallback: live fetch on every cache miss
    return (
        fetch_full_strip(),
        fetch_reference_rates(days=30),
        fetch_macro_series(days=30),
        upcoming_fomc_dates(),
        fetch_all_releases(),
        {
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
            "source": "live",
            "loaders": {},
        },
    )


def _read_last_good() -> dict:
    """Disk-backed last-good values per column. Survives sessions + restarts."""
    if _LAST_GOOD_FILE.exists():
        try:
            return json.loads(_LAST_GOOD_FILE.read_text())
        except Exception:
            return {}
    return {}


def _write_last_good(values: dict) -> None:
    _LAST_GOOD_FILE.parent.mkdir(parents=True, exist_ok=True)
    _LAST_GOOD_FILE.write_text(json.dumps(values))


def macro_latest(df: pd.DataFrame, col: str) -> float:
    """Latest value for col, with disk-backed last-good fallback.

    FRED is flaky enough that consecutive fetches return different failure
    patterns. Persisting per-column last-good values on disk means a
    transient outage on T10YIE doesn't blank the Breakeven 10y card; we
    just keep showing yesterday's value.
    """
    last_good = _read_last_good()
    if col in df.columns:
        s = df[col].dropna()
        if not s.empty:
            v = float(s.iloc[-1])
            if last_good.get(col) != v:
                last_good[col] = v
                _write_last_good(last_good)
            return v
    return last_good.get(col, float("nan"))


with st.sidebar:
    st.markdown("### Controls")
    if st.button("Force refresh data", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.caption("Cache TTL: 10 min")


strip_raw, ref_rates, macro_series, fomc_dates, all_releases, metadata = load_data()

_today = date.today()
releases = sorted(r for r in all_releases if r[0] >= _today)[:6]

OCR = float(ref_rates["effr"].iloc[-1])
SOFR_SPOT = float(ref_rates["sofr"].iloc[-1])
basis_bp = (SOFR_SPOT - OCR) * 100

strip = add_implied(strip_raw, OCR)
sofr_strip = strip[strip["root"] == "SR3"].reset_index(drop=True)
ff_strip = strip[strip["root"] == "ZQ"].reset_index(drop=True)
path = build_meeting_path(ff_strip, OCR, fomc_dates)


# ────────────────────────────────────────────────────────────────────
# Derived metrics
# ────────────────────────────────────────────────────────────────────

def _12m_policy_moves(zq: pd.DataFrame, ocr: float) -> tuple[float, str]:
    target = pd.Timestamp(date.today() + timedelta(days=365))
    expiries = pd.to_datetime(zq["expiry"])
    diffs = (expiries - target).abs()
    idx = int(diffs.values.argmin())
    row = zq.iloc[idx]
    cuts = (ocr - float(row["implied_rate"])) / 0.25
    return cuts, str(row["symbol"])


def _next_meeting(dates: list[date]):
    if not dates:
        return None, 0
    nxt = dates[0]
    return nxt, (nxt - date.today()).days


def _terminal(zq: pd.DataFrame, ocr: float) -> tuple[float, str]:
    term = find_terminal(zq, ocr)
    return float(term["implied_rate"]), str(term["symbol"])


def _next_cut_prob(meeting_path: pd.DataFrame, ocr: float) -> tuple[float, float]:
    if meeting_path.empty:
        return 0.0, 100.0
    p = meeting_probs(float(meeting_path.iloc[0]["post_rate"]), ocr)
    return float(p["cut25"]), float(p["hold"])


def _latest_or_nan(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns:
        return float("nan")
    s = df[col].dropna()
    return float(s.iloc[-1]) if not s.empty else float("nan")


def _fmt_pct(v: float) -> str:
    return f"{v:.2f}%" if not pd.isna(v) else "—"


cuts_12m_x, cuts_12m_sym = _12m_policy_moves(ff_strip, OCR)
next_dt, days_until = _next_meeting(fomc_dates)
term_rate, term_sym = _terminal(ff_strip, OCR)
cut_prob, hold_prob = _next_cut_prob(path, OCR)
policy_rail = round(OCR / 0.25) * 0.25
real_10y = macro_latest(macro_series, "real_10y")
be_10y = macro_latest(macro_series, "breakeven_10y")
fwd_5y5y = macro_latest(macro_series, "fwd_5y5y_inflation")
claims_raw = macro_latest(macro_series, "jobless_claims")


def _fmt_claims(v: float) -> str:
    return f"{int(v / 1000):d}k" if not pd.isna(v) else "—"


# ────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────

refreshed_iso = metadata.get("refreshed_at")
source = metadata.get("source", "disk")
try:
    refreshed = datetime.fromisoformat(refreshed_iso)
    if refreshed.tzinfo is None:
        refreshed = refreshed.replace(tzinfo=timezone.utc)
except Exception:
    refreshed = datetime.now(timezone.utc)

age_hours = (datetime.now(timezone.utc) - refreshed).total_seconds() / 3600

if source == "live":
    dot_color = "#00E676"
    ts_display = refreshed.astimezone().strftime("%Y-%m-%d %H:%M") + " · LIVE"
elif age_hours < 30:
    dot_color = "#00E676"
    ts_display = refreshed.strftime("%Y-%m-%d %H:%M UTC")
elif age_hours < 72:
    dot_color = "#FFA000"
    ts_display = refreshed.strftime("%Y-%m-%d %H:%M UTC")
else:
    dot_color = "#FF1744"
    ts_display = refreshed.strftime("%Y-%m-%d %H:%M UTC")

header_left, header_right = st.columns([4, 1])
with header_left:
    st.markdown(
        '<div class="eyebrow">US RATES · STIR DASHBOARD</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<h1 class="page-title">Macro Dashboard</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="page-desc">CME-FedWatch-style STIR view. SOFR and Fed Funds strips, '
        'implied post-meeting path, calendar spreads, and 25 bp policy rails.</p>',
        unsafe_allow_html=True,
    )
with header_right:
    st.markdown(
        f'<div class="last-updated-right">'
        f'<span class="dot" style="color: {dot_color};">●</span>'
        f'<span class="ts-label">Last updated</span>'
        f'<span class="ts-value">{ts_display}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

st.markdown('<hr class="divider-rule" />', unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────
# Metric cards (5 + 5)
# ────────────────────────────────────────────────────────────────────

def _card(label: str, value: str, caption: str) -> str:
    return (
        f'<div class="metric-card">'
        f'<div>'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f'</div>'
        f'<div class="caption">{caption}</div>'
        f'</div>'
    )


# Row 1 - today's snapshot
row1 = [
    ("Effective FFR",  f"{OCR:.2f}%",          "current policy anchor"),
    ("SOFR spot",      f"{SOFR_SPOT:.2f}%",    f"{basis_bp:+.1f} bp vs EFFR"),
    ("Real 10y",       _fmt_pct(real_10y),     "10y TIPS yield"),
    ("Breakeven 10y",  _fmt_pct(be_10y),       "10y inflation expectation"),
    ("Initial claims", _fmt_claims(claims_raw), "weekly · lower = stronger"),
]

cols = st.columns(5, gap="small")
for col, (label, value, caption) in zip(cols, row1):
    with col:
        st.markdown(_card(label, value, caption), unsafe_allow_html=True)


# Row 2 - forward expectations
st.markdown('<div style="height: 0.75rem;"></div>', unsafe_allow_html=True)

if cuts_12m_x >= 0:
    cuts_12m_value = f"{cuts_12m_x:.1f}x"
    cuts_12m_caption = f"cuts priced through {cuts_12m_sym}"
else:
    cuts_12m_value = f"{abs(cuts_12m_x):.1f}x"
    cuts_12m_caption = f"hikes priced through {cuts_12m_sym}"

next_meeting_value = next_dt.strftime("%b %-d") if next_dt else "—"
next_meeting_caption = f"{days_until} days away" if next_dt else "no FOMC dates loaded"

row2 = [
    ("Next meeting",     next_meeting_value,  next_meeting_caption),
    ("Next cut prob",    f"{cut_prob:.0f}%",  f"hold {hold_prob:.0f}%"),
    ("Terminal rate",    f"{term_rate:.2f}%", term_sym),
    ("12m cuts priced",  cuts_12m_value,      cuts_12m_caption),
    ("5y5y forward",     _fmt_pct(fwd_5y5y),  "long-run inflation expectation"),
]

cols = st.columns(5, gap="small")
for col, (label, value, caption) in zip(cols, row2):
    with col:
        st.markdown(_card(label, value, caption), unsafe_allow_html=True)

st.markdown('<div style="height: 1.75rem;"></div>', unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────
# Upcoming data section
# ────────────────────────────────────────────────────────────────────

st.markdown('<div class="section-label">Upcoming Data</div>', unsafe_allow_html=True)

if releases:
    rcols = st.columns(len(releases), gap="small")
    for col, (rdate, rname, rimp) in zip(rcols, releases):
        days = (rdate - date.today()).days
        with col:
            st.markdown(
                f'<div class="release-card {rimp}">'
                f'<div class="date">{rdate.strftime("%b %-d")}</div>'
                f'<div class="name">{rname}</div>'
                f'<div class="days">{days} days</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
else:
    st.caption("No upcoming releases in calendar.")

st.markdown('<div style="height: 1.75rem;"></div>', unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────
# Tabs
# ────────────────────────────────────────────────────────────────────

tab_products, tab_meetings = st.tabs(["Products", "Meetings"])

with tab_products:
    if hasattr(st, "segmented_control"):
        product = st.segmented_control(
            "Product",
            options=["SOFR (SR3)", "Fed Funds (ZQ)"],
            default="SOFR (SR3)",
            label_visibility="collapsed",
        )
        if product is None:
            product = "SOFR (SR3)"
    else:
        product = st.radio(
            "Product",
            ["SOFR (SR3)", "Fed Funds (ZQ)"],
            horizontal=True,
            label_visibility="collapsed",
        )

    if product == "SOFR (SR3)":
        view, title = sofr_strip, "SOFR (SR3) STRIP"
    else:
        view, title = ff_strip, "FED FUNDS (ZQ) STRIP"

    fig_strip = plot_strip(view, OCR, title)
    fig_strip.update_layout(margin=dict(t=30, r=70))
    if fig_strip.layout.annotations:
        fig_strip.layout.annotations[0].text = "EFFR"
    y_min = float(view["implied_rate"].min()) - 0.1
    y_max = float(view["implied_rate"].max()) + 0.1
    fig_strip.update_yaxes(range=[y_min, y_max])
    st.plotly_chart(fig_strip, width="stretch", config=PLOT_CFG)

    term_view = find_terminal(view, OCR)
    basis_view = (term_view["implied_rate"] - OCR) * 100
    st.caption(
        f"Terminal: **{term_view['symbol']}** · "
        f"**{term_view['implied_rate']:.3f}%** · "
        f"{basis_view:+.1f} bp vs EFFR · "
        f"{len(view)} contracts"
    )


with tab_meetings:
    sub_strip, sub_spreads, sub_cb = st.tabs(["Strip", "Spreads", "CB LVL"])

    with sub_strip:
        if path.empty:
            st.warning("No FOMC meetings within ZQ horizon.")
        else:
            fig_path = plot_meeting_path(path, OCR)
            fig_path.update_layout(margin=dict(r=70))
            if fig_path.layout.annotations:
                fig_path.layout.annotations[0].text = "EFFR"
            st.plotly_chart(fig_path, width="stretch", config=PLOT_CFG)

            probs_df = pd.DataFrame(
                [meeting_probs(r, OCR) for r in path["post_rate"]],
                index=[d.strftime("%b %-d, %Y") for d in path["meeting"]],
            ).round(1)
            probs_df.index.name = "Meeting"
            probs_df = probs_df.rename(columns={
                "hold":   "Hold",
                "cut25":  "-25 bp",
                "cut50":  "-50 bp",
                "cut75":  "-75 bp",
                "hike25": "+25 bp",
            })

            def _prob_row(row):
                max_val = row.max()
                base = (
                    "font-family: 'IBM Plex Mono', monospace; "
                    "text-align: right;"
                )
                out = []
                for v in row:
                    if pd.isna(v) or v <= 0:
                        out.append(base + " color: #444;")
                    elif v == max_val:
                        out.append(base + " color: #FE7C04; font-weight: 700;")
                    else:
                        out.append(base + " color: #D0D0D0;")
                return out

            styled_probs = (
                probs_df.style
                .apply(_prob_row, axis=1)
                .format(lambda v: f"{v:.1f}" if pd.notna(v) and v > 0 else "—")
            )
            st.dataframe(styled_probs, width="stretch")

    with sub_spreads:
        sm = spread_matrix(ff_strip, OCR)
        if sm.empty:
            st.warning("No data for spread matrix.")
        else:
            CAP_BP = 20.0  # gradient saturates at +/- 20 bp

            def _spread_cell(val):
                base = (
                    "font-family: 'IBM Plex Mono', monospace; "
                    "text-align: right; "
                    "font-weight: 600;"
                )
                if pd.isna(val):
                    return (
                        "background-color: #0A0A0A; color: #444; "
                        "font-family: 'IBM Plex Mono', monospace; "
                        "text-align: right;"
                    )
                intensity = min(1.0, abs(val) / CAP_BP)
                alpha = 0.08 + intensity * 0.45
                if val < 0:
                    return (
                        f"background-color: rgba(0, 230, 118, {alpha}); "
                        "color: #00E676; " + base
                    )
                if val > 0:
                    return (
                        f"background-color: rgba(255, 23, 68, {alpha}); "
                        "color: #FF1744; " + base
                    )
                return base + " color: #888;"

            # Single callable handles NaN explicitly. Streamlit's st.dataframe
            # does not always honor Styler.na_rep, so we produce "—" inline.
            styled_sm = (
                sm.style
                .format(lambda v: f"{v:.0f} bp" if pd.notna(v) else "—")
                .map(_spread_cell)
            )
            table_height = min(35 * len(sm) + 50, 800)
            st.dataframe(styled_sm, width="stretch", height=table_height)
            st.caption(
                "Spreads in basis points. Green = cuts priced into the forward contract. "
                "Red = hikes. Em-dash = no forward contract that far out. "
                "Gradient saturates at ±20 bp."
            )

    with sub_cb:
        if path.empty:
            st.warning("No FOMC meetings within ZQ horizon.")
        else:
            st.markdown(
                '<div class="section-label">Solid orange · current 25 bp policy rail '
                '&nbsp;·&nbsp; Dotted · neighboring rails</div>',
                unsafe_allow_html=True,
            )
            fig_cb = plot_cb_lvl(path, OCR)
            fig_cb.update_layout(margin=dict(r=70))
            if fig_cb.layout.annotations:
                fig_cb.layout.annotations[0].text = "EFFR"
            cb_y_min = float(path["post_rate"].min()) - 0.15
            cb_y_max = float(path["post_rate"].max()) + 0.15
            fig_cb.update_yaxes(range=[cb_y_min, cb_y_max])
            st.plotly_chart(fig_cb, width="stretch", config=PLOT_CFG)
