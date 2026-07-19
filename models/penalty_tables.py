"""
models/penalty_tables.py
Deterministic RPC penalty period classification.

PENALTY_PERIODS maps each penalty name to its three periods (minimum/medium/maximum).
Each period is a 6-tuple: (start_years, start_months, start_days, end_years, end_months, end_days)

Indivisible penalties (arresto menor, reclusion perpetua, death) are mapped to None.

Usage:
    period = classify_penalty_period("prision correccional", years=2, months=4)
    # → "minimum"  (2y 4m is the END of minimum, not the start of medium)
    desc = describe_period("prision correccional", "medium")
    # → "2 years, 4 months, 1 day to 4 years, 2 months"
"""

PENALTY_PERIODS: dict[str, dict[str, tuple[int, int, int, int, int, int]] | None] = {
    # Indivisible — no periods apply
    "arresto menor": None,       # 1 day to 30 days
    "reclusion perpetua": None,  # 20 years and 1 day to 40 years
    "death": None,               # indivisible

    "arresto mayor": {
        "minimum": (0, 1, 1, 0, 2, 0),    # 1m 1d   → 2m
        "medium":  (0, 2, 1, 0, 4, 0),    # 2m 1d   → 4m
        "maximum": (0, 4, 1, 0, 6, 0),    # 4m 1d   → 6m
    },
    "prision correccional": {
        "minimum": (0, 6, 1, 2, 4, 0),    # 6m 1d      → 2y 4m
        "medium":  (2, 4, 1, 4, 2, 0),    # 2y 4m 1d   → 4y 2m
        "maximum": (4, 2, 1, 6, 0, 0),    # 4y 2m 1d   → 6y
    },
    "destierro": {
        # Same range as prision correccional per RPC Art. 27
        "minimum": (0, 6, 1, 2, 4, 0),
        "medium":  (2, 4, 1, 4, 2, 0),
        "maximum": (4, 2, 1, 6, 0, 0),
    },
    "prision mayor": {
        "minimum": (6, 0, 1, 8, 0, 0),    # 6y 1d   → 8y
        "medium":  (8, 0, 1, 10, 0, 0),   # 8y 1d   → 10y
        "maximum": (10, 0, 1, 12, 0, 0),  # 10y 1d  → 12y
    },
    "reclusion temporal": {
        "minimum": (12, 0, 1, 14, 8, 0),  # 12y 1d      → 14y 8m
        "medium":  (14, 8, 1, 17, 4, 0),  # 14y 8m 1d   → 17y 4m
        "maximum": (17, 4, 1, 20, 0, 0),  # 17y 4m 1d   → 20y
    },
}

# Article 359 specific — prescribed penalty for serious slander by deed
# "arresto mayor in its maximum period to prision correccional in its minimum period"
# This is a special range that does NOT correspond to a single penalty's full span.
ARTICLE_359_SERIOUS_SLANDER: dict[str, str] = {
    "prescribed_range":   "arresto mayor maximum to prision correccional minimum",
    "prescribed_start":   "4 months and 1 day",
    "prescribed_end":     "2 years and 4 months",
    "medium_period":      "1 year and 1 day to 1 year and 8 months",
    "next_lower":         "arresto mayor minimum and medium periods",
    "next_lower_start":   "1 month and 1 day",
    "next_lower_end":     "4 months",
    "fine_alternative":   "P200.00 to P1,000.00",
}


def _total_days(years: int, months: int, days: int) -> int:
    """Approximate conversion to days for period boundary comparison.

    Uses 365 days/year and 30 days/month — sufficient for RPC period
    boundaries which always fall on whole month values, never mid-month.
    """
    return years * 365 + months * 30 + days


def classify_penalty_period(
    penalty_name: str,
    years: int,
    months: int,
    days: int = 0,
) -> str:
    """Classify a penalty duration into 'minimum', 'medium', 'maximum',
    'indivisible', 'out_of_range', or 'unknown_penalty'.

    Uses day-level precision via _total_days().
    Returns the first matching period (minimum checked before medium before maximum).
    """
    penalty_name = penalty_name.strip().lower()
    periods = PENALTY_PERIODS.get(penalty_name)

    if penalty_name not in PENALTY_PERIODS:
        return "unknown_penalty"
    if periods is None:
        return "indivisible"

    target = _total_days(years, months, days)

    for period_name in ("minimum", "medium", "maximum"):
        sy, sm, sd, ey, em, ed = periods[period_name]
        start = _total_days(sy, sm, sd)
        end = _total_days(ey, em, ed)
        if start <= target <= end:
            return period_name

    return "out_of_range"


def describe_period(penalty_name: str, period: str) -> str:
    """Return a human-readable string describing a penalty period range.

    Example:
        describe_period("prision correccional", "medium")
        # → "2 years, 4 months, 1 day to 4 years, 2 months"
    """
    penalty_name = penalty_name.strip().lower()
    periods = PENALTY_PERIODS.get(penalty_name)

    if penalty_name not in PENALTY_PERIODS:
        return f"{penalty_name} (unknown penalty)"
    if periods is None:
        return f"{penalty_name} (indivisible — no periods)"

    period = period.strip().lower()
    spec = periods.get(period)
    if spec is None:
        return f"{period} period (not found for {penalty_name})"

    sy, sm, sd, ey, em, ed = spec

    def _fmt(y: int, m: int, d: int) -> str:
        parts = []
        if y:
            parts.append(f"{y} year{'s' if y != 1 else ''}")
        if m:
            parts.append(f"{m} month{'s' if m != 1 else ''}")
        if d:
            parts.append(f"{d} day{'s' if d != 1 else ''}")
        return ", ".join(parts) if parts else "0 days"

    return f"{_fmt(sy, sm, sd)} to {_fmt(ey, em, ed)}"


def get_article_359_facts() -> str:
    """Return a pre-formatted verified fact string for Article 359
    (serious slander by deed) for injection into the reduce prompt."""
    a = ARTICLE_359_SERIOUS_SLANDER
    return (
        f"VERIFIED PENALTY FACT (Article 359 — Serious Slander by Deed):\n"
        f"  Prescribed penalty range : {a['prescribed_range']}\n"
        f"  Prescribed range spans   : {a['prescribed_start']} to {a['prescribed_end']}\n"
        f"  Medium period of range   : {a['medium_period']}\n"
        f"  Next lower penalty       : {a['next_lower']}\n"
        f"  Next lower range         : {a['next_lower_start']} to {a['next_lower_end']}\n"
        f"  Fine alternative         : {a['fine_alternative']}\n"
        f"Use these exact figures in Section 5 (Ruling) and Section 6 (ALAC).\n"
        f"Do not compute or infer penalty ranges — use only the values above."
    )
