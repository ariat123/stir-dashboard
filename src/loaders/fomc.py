"""
Hardcoded FOMC meeting end-dates (the day the policy decision is announced).

REFRESH ANNUALLY. The Fed typically announces next-year dates in summer.
Source of truth: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm

The math in build_meeting_path() uses the END date of each meeting (when the
decision is announced and effective), so two-day meetings are listed by their
second day.
"""
from __future__ import annotations
from datetime import date

# 2026 dates verified at federalreserve.gov as of May 2026
# 2027 dates: NOT YET PUBLISHED. Update this list once Fed announces them.
FOMC_DATES: list[date] = [
    # 2026 (verified)
    date(2026, 1, 28),
    date(2026, 3, 18),
    date(2026, 4, 29),
    date(2026, 6, 17),
    date(2026, 7, 29),
    date(2026, 9, 16),
    date(2026, 10, 28),
    date(2026, 12, 9),
    # 2027 placeholders (Fed typically announces in summer of prior year)
    # Refresh from federalreserve.gov when available.
]


def upcoming_fomc_dates(today: date | None = None) -> list[date]:
    """Return FOMC meeting dates from today onwards, sorted ascending."""
    today = today or date.today()
    return sorted(d for d in FOMC_DATES if d >= today)


if __name__ == "__main__":
    upcoming = upcoming_fomc_dates()
    print(f"Upcoming FOMC meetings ({len(upcoming)} dates):")
    for d in upcoming:
        print(f"  {d.strftime('%Y-%m-%d (%A)')}")
