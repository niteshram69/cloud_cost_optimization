"""Region-aware pricing catalog loader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TierPricing:
    """Normalized storage pricing attributes."""

    storage_cost_gb_month_usd: float
    retrieval_cost_gb_usd: float
    min_retention_days: int
    early_delete_cost_gb_usd: float
    data_egress_cost_gb_usd: float


class PricingCatalog:
    """Read-only view over multi-cloud region-aware pricing data."""

    def __init__(self, catalog_path: str | None = None):
        default_path = Path(__file__).with_name("pricing_catalog.json")
        path = Path(catalog_path) if catalog_path else default_path
        with open(path, "r", encoding="utf-8") as handle:
            self._catalog: dict = json.load(handle)

    def list_regions(self, provider: str) -> list[str]:
        """Return supported regions for provider."""
        provider_data = self._catalog.get(provider.lower(), {})
        return sorted(provider_data.keys())

    def list_tiers(self, provider: str, region: str) -> list[str]:
        """Return supported tiers for provider+region."""
        region_data = self._lookup_region(provider, region)
        return sorted(region_data.keys())

    def get_tier(self, provider: str, region: str, tier: str) -> TierPricing:
        """Fetch normalized pricing for provider/region/tier."""
        region_data = self._lookup_region(provider, region)
        tier_data = region_data.get(tier)
        if tier_data is None:
            raise KeyError(f"unsupported tier '{tier}' for provider={provider}, region={region}")

        return TierPricing(
            storage_cost_gb_month_usd=float(tier_data["storage_cost_gb_month_usd"]),
            retrieval_cost_gb_usd=float(tier_data["retrieval_cost_gb_usd"]),
            min_retention_days=int(tier_data["min_retention_days"]),
            early_delete_cost_gb_usd=float(tier_data["early_delete_cost_gb_usd"]),
            data_egress_cost_gb_usd=float(tier_data["data_egress_cost_gb_usd"]),
        )

    def _lookup_region(self, provider: str, region: str) -> dict:
        provider_data = self._catalog.get(provider.lower())
        if provider_data is None:
            raise KeyError(f"unsupported provider '{provider}'")

        region_data = provider_data.get(region)
        if region_data is None:
            region_data = provider_data.get("default")
        if region_data is None:
            raise KeyError(f"unsupported region '{region}' for provider '{provider}'")
        return region_data
