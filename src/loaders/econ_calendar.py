"""
Upcoming US economic data calendar.

BLS publishes a .ics feed for its own news releases. We fetch and parse it,
then merge with hardcoded entries for things BLS doesn't publish:
  - FOMC meetings (sourced from loaders.fomc)
  - PCE releases from BEA (no clean .ics feed available)
  - GDP releases from BEA

Source URL: https://www.bls.gov/schedule/news_release/bls.ics

Graceful degradation: if BLS fetch fails (network down, format change,
blocked), we return whatever's hardcoded - the dashboard never breaks
because BLS is unreachable.
"""
from __future__ import annotations
import sys
from pathlib import Path

# Make src/ importable so `from loaders.fomc import ...` works in both
# script-run and package-import contexts.
_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from datetime import date, datetime
from curl_cffi import requests  # NOT stdlib - bypasses BLS TLS fingerprinting
from icalendar import Calendar

from loaders.fomc import FOMC_DATES


BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
IMPERSONATE_PROFILE = "chrome120"

HEADERS = {
    "Accept": "text/calendar, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Map BLS event SUMMARY -> (display name, importance). None means skip.
BLS_NAME_MAP: dict[str, tuple[str, str] | None] = {
    "Employment Situation":                   ("Nonfarm Payrolls", "high"),
    "Consumer Price Index":                   ("CPI",              "high"),
    "Producer Price Index":                   ("PPI",              "medium"),
    "Job Openings and Labor Turnover":        ("JOLTS",            "medium"),
    "Job Openings and Labor Turnover Survey": ("JOLTS",            "medium"),
    "Employment Cost Index":                  ("ECI",              "medium"),
    # Skipped: not high-importance for STIR dashboard
    "Real Earnings":                          None,
    "U.S. Export and Import Price Indexes":   None,
    "U.S. Import and Export Price Indexes":   None,
}

# BEA PCE releases (hardcoded - BEA does not publish a clean .ics feed)
PCE_DATES: list[tuple[date, str]] = [
    (date(2026, 5, 30), "PCE (Apr)"),
    (date(2026, 6, 26), "PCE (May)"),
    (date(2026, 7, 31), "PCE (Jun)"),
    (date(2026, 8, 28), "PCE (Jul)"),
]

# BEA GDP releases (hardcoded)
GDP_DATES: list[tuple[date, str]] = [
    (date(2026, 5, 29), "GDP Q1 (2nd estimate)"),
    (date(2026, 6, 26), "GDP Q1 (3rd estimate)"),
    (date(2026, 7, 30), "GDP Q2 (advance)"),
]


def fetch_bls_releases(timeout: int = 10) -> list[tuple[date, str, str]]:
    """Fetch and parse the BLS .ics feed.

    Returns list of (date, display_name, importance). Raises on network or
    parse error - callers should catch and degrade gracefully.
    """
    resp = requests.get(
        BLS_ICS_URL,
        headers=HEADERS,
        impersonate=IMPERSONATE_PROFILE,
        timeout=timeout,
    )
    resp.raise_for_status()
    cal = Calendar.from_ical(resp.content)

    out: list[tuple[date, str, str]] = []
    for event in cal.walk("VEVENT"):
        summary = str(event.get("SUMMARY", "")).strip()
        if summary not in BLS_NAME_MAP:
            continue
        mapping = BLS_NAME_MAP[summary]
        if mapping is None:
            continue
        display_name, importance = mapping

        dtstart = event.get("DTSTART")
        if dtstart is None:
            continue
        dt = dtstart.dt
        if isinstance(dt, datetime):
            dt = dt.date()
        if not isinstance(dt, date):
            continue

        out.append((dt, display_name, importance))
    return out


def hardcoded_releases() -> list[tuple[date, str, str]]:
    """FOMC + PCE + GDP entries (no .ics source available)."""
    out: list[tuple[date, str, str]] = []
    for d in FOMC_DATES:
        out.append((d, "FOMC Meeting", "high"))
    for d, name in PCE_DATES:
        out.append((d, name, "high"))
    for d, name in GDP_DATES:
        out.append((d, name, "medium"))
    return out


def fetch_all_releases() -> list[tuple[date, str, str]]:
    """All releases: BLS feed + hardcoded sources.

    On BLS fetch error returns hardcoded entries only - the dashboard
    keeps working with FOMC/PCE/GDP even if BLS is unreachable.
    """
    out = hardcoded_releases()
    try:
        bls = fetch_bls_releases()
        out.extend(bls)
    except Exception as exc:
        print(f"[econ_calendar] BLS fetch failed ({exc}); using hardcoded only")
    return out


def upcoming_releases(
    today: date | None = None,
    limit: int = 8,
) -> list[tuple[date, str, str]]:
    """Return upcoming releases sorted by date, up to `limit`."""
    today = today or date.today()
    all_releases = fetch_all_releases()
    upcoming = sorted(r for r in all_releases if r[0] >= today)
    return upcoming[:limit]


if __name__ == "__main__":
    upcoming = upcoming_releases()
    print(f"Upcoming releases ({len(upcoming)}):")
    for d, name, imp in upcoming:
        days = (d - date.today()).days
        print(f"  {d.strftime('%Y-%m-%d')}  {name:<28}  [{imp:<6}]  {days} days")
