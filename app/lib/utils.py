"""CricSavant AI -- small shared helpers with no other home."""

import pandas as pd


def safe_num(v, default=0):
    """Numeric fallback that also treats NaN as missing.

    `v or default` looks like it handles "missing," but it doesn't --
    NaN is truthy in Python (`bool(float('nan'))` is True), so `NaN or 0`
    evaluates to NaN, not 0. Gold-table joins routinely produce NaN
    (not None) for players missing a given metric (no situational/venue
    sample, no career-T20-league row, etc.), and `int(NaN)` raises
    ValueError -- a real crash hit in testing (My Franchise chat query,
    Player Explorer detail view). This is the actual fix, not another
    `or 0` that silently has the same hole.
    """
    if v is None:
        return default
    try:
        if pd.isna(v):
            return default
    except (TypeError, ValueError):
        pass
    return v


def fmt_num(v, decimals=1, default="—"):
    """Format a possibly-NaN/None numeric value, or return a dash."""
    v = safe_num(v, default=None)
    if v is None:
        return default
    return f"{v:.{decimals}f}"
