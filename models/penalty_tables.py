"""
models/penalty_tables.py
Deterministic RPC penalty period classification.

PENALTY_PERIODS maps each penalty name to its three periods (minimum/medium/maximum).
Each period is a 6-tuple: (start_years, start_months, start_days, end_years, end_months, end_days)

Usage:
    period = classify_penalty_period("prision correccional", years=2, months=4)
    # → "maximum"
    desc = describe_period("prision correccional", "medium")
    # → "1 year, 1 day to 2 years, 4 months"
"""

PENALTY_PERIODS: dict[str, dict[str, tuple[int, int, int, int, int, int]]] = {
    "prision correccional": {
        "minimum": (0, 6, 1, 1, 0, 0),    # 6m 1d  → 1y 0m
        "medium":  (1, 0, 1, 2, 4, 0),    # 1y 1d  → 2y 4m
        "maximum": (2, 4, 1, 6, 0, 0),    # 2y 4m 1d → 6y 0m
    },
    "arresto mayor": {
        "minimum": (0, 1, 1, 0, 2, 0),    # 1m 1d  → 2m
        "medium":  (0, 2, 1, 0, 4, 0),    # 2m 1d  → 4m
        "maximum": (0, 4, 1, 0, 6, 0),    # 4m 1d  → 6m
    },
    "prision mayor": {
        "minimum": (6, 0, 1, 8, 0, 0),    # 6y 1d  → 8y
        "medium":  (8, 0, 1, 10, 0, 0),   # 8y 1d  → 10y
        "maximum": (10, 0, 1, 12, 0, 0),  # 10y 1d → 12y
    },
    "reclusion temporal": {
        "minimum": (12, 0, 1, 14, 0, 0),  # 12y 1d → 14y 8m
        "medium":  (14, 8, 1, 17, 4, 0),  # 14y 8m 1d → 17y 4m
        "maximum": (17, 4, 1, 20, 0, 0),  # 17y 4m 1d → 20y
    },
    "reclusion perpetua": {
        "minimum": (20, 0, 1, 40, 0, 0),
        "medium":  (40, 0, 1, 40, 0, 0),
        "maximum": (40, 0, 1, 40, 0, 0),
    },
}


def _total_days(years: int, months: int, days: int) -> int:
    """Convert years/months/days to a total day count for comparison."""
    return years * 365 + months * 30 + days


def classify_penalty_period(
    penalty_name: str,
    years: int,
    months: int,
    days: int = 0,
) -> str:
    """
    Classify a penalty duration into 'minimum', 'medium', 'maximum', or
    'out_of_range' for the given RPC penalty.

    Uses day-level precision. Returns the first matching period.
    """
    penalty_name = penalty_name.strip().lower()
    periods = PENALTY_PERIODS.get(penalty_name)
    if periods is None:
        return "unknown_penalty"

    target = _total_days(years, months, days)

    for period_name in ("minimum", "medium", "maximum"):
        sy, sm, sd, ey, em, ed = periods[period_name]
        start = _total_days(sy, sm, sd)
        end = _total_days(ey, em, ed)
        if start <= target <= end:
            return period_name

    return "out_of_range"


def describe_period(penalty_name: str, period: str) -> str:
    """
    Return a human-readable string describing a penalty period range.

    Example:
        describe_period("prision correccional", "medium")
        # → "1 year, 1 day to 2 years, 4 months"
    """
    penalty_name = penalty_name.strip().lower()
    periods = PENALTY_PERIODS.get(penalty_name)
    if periods is None:
        return f"{penalty_name} (unknown)"

    period = period.strip().lower()
    spec = periods.get(period)
    if spec is None:
        return f"{period} period (unknown)"

    sy, sm, sd, ey, em, ed = spec

    def _fmt(y, m, d):
        parts = []
        if y:
            parts.append(f"{y} year{'s' if y > 1 else ''}")
        if m:
            parts.append(f"{m} month{'s' if m > 1 else ''}")
        if d:
            parts.append(f"{d} day{'s' if d > 1 else ''}")
        return ", ".join(parts) if parts else "0 days"

    return f"{_fmt(sy, sm, sd)} to {_fmt(ey, em, ed)}"
