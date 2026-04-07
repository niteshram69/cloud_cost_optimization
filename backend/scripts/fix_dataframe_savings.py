from __future__ import annotations

import pandas as pd


TIER_RATES_USD_PER_GB: dict[str, float] = {
    "standard": 0.023,
    "standardia": 0.0125,
    "coolblob": 0.0028,
    "archive": 0.00099,
}


def _normalize_tier(value: str) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("_", "").replace("-", "").replace(" ", "")
    aliases = {
        "s3standard": "standard",
        "standard": "standard",
        "hotblob": "standard",
        "standardia": "standardia",
        "s3standardia": "standardia",
        "onezoneia": "standardia",
        "coolblob": "coolblob",
        "azurecoolblob": "coolblob",
        "archive": "archive",
        "archiveblob": "archive",
        "glacier": "archive",
        "deeparchive": "archive",
    }
    return aliases.get(text, text)


def _tier_rate(final_action_tier: str) -> float:
    normalized = _normalize_tier(final_action_tier)
    if normalized not in TIER_RATES_USD_PER_GB:
        raise ValueError(f"Unsupported final_action_tier: {final_action_tier!r}")
    return TIER_RATES_USD_PER_GB[normalized]


def calculate_savings(row: pd.Series) -> float:
    """
    Calculate monthly savings for one row.

    Required columns:
    - final_action_tier
    - size_gb
    - current_cost
    """
    tier = row["final_action_tier"]
    size_gb = float(row["size_gb"])
    current_cost = float(row["current_cost"])
    rate = _tier_rate(tier)
    new_monthly_cost = size_gb * rate
    savings = current_cost - new_monthly_cost
    return round(savings, 6)


def apply_savings_fix(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds:
    - after_cost: recalculated monthly cost from action tier rate
    - savings: current_cost - after_cost
    """
    result = df.copy()
    result["after_cost"] = result.apply(
        lambda row: round(float(row["size_gb"]) * _tier_rate(str(row["final_action_tier"])), 6),
        axis=1,
    )
    result["savings"] = result.apply(calculate_savings, axis=1)
    return result

