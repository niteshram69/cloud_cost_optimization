"""Multi-cloud pricing engine with normalized cost comparison."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.decision_engine.types import DataTemperature
from app.feature_engineering.models import FeatureVector
from app.pricing_engine.catalog import PricingCatalog, TierPricing
from app.pricing_engine.fx import CurrencyConverter


@dataclass(slots=True)
class TierCostBreakdown:
    """Transparent cost breakdown for one provider/region/tier option."""

    provider: str
    region: str
    tier: str
    storage_cost_usd: float
    retrieval_cost_usd: float
    retention_penalty_usd: float
    egress_cost_usd: float
    total_monthly_usd: float
    total_yearly_usd: float
    fx_rate: float
    currency: str
    total_monthly_converted: float
    total_yearly_converted: float
    min_retention_days: int

    def to_dict(self) -> dict:
        return asdict(self)


class MultiCloudPricingEngine:
    """Evaluates normalized storage costs across AWS/GCP/Azure."""

    _CLASS_TO_TIERS = {
        "aws": {
            DataTemperature.HOT: ["S3_STANDARD"],
            DataTemperature.COLD: ["S3_IA"],
            DataTemperature.ARCHIVE: ["S3_GLACIER", "S3_DEEP_ARCHIVE"],
        },
        "gcp": {
            DataTemperature.HOT: ["STANDARD"],
            DataTemperature.COLD: ["NEARLINE"],
            DataTemperature.ARCHIVE: ["COLDLINE", "ARCHIVE"],
        },
        "azure": {
            DataTemperature.HOT: ["HOT"],
            DataTemperature.COLD: ["COOL"],
            DataTemperature.ARCHIVE: ["ARCHIVE"],
        },
    }

    def __init__(self, catalog: PricingCatalog, converter: CurrencyConverter):
        self._catalog = catalog
        self._converter = converter

    async def evaluate_options(
        self,
        feature: FeatureVector,
        data_class: DataTemperature,
        currency: str,
        allowed_regions: dict[str, list[str]] | None = None,
    ) -> list[TierCostBreakdown]:
        """Evaluate all cost options for selected class and allowed regions."""
        options: list[TierCostBreakdown] = []
        allowed_regions = allowed_regions or {}

        for provider, tier_map in self._CLASS_TO_TIERS.items():
            tiers = tier_map[data_class]
            regions = allowed_regions.get(provider) or self._catalog.list_regions(provider)

            for region in regions:
                for tier in tiers:
                    try:
                        pricing = self._catalog.get_tier(provider, region, tier)
                    except KeyError:
                        continue
                    option = await self._estimate_tier_cost(
                        feature=feature,
                        provider=provider,
                        region=region,
                        tier=tier,
                        tier_pricing=pricing,
                        currency=currency,
                    )
                    options.append(option)

        options.sort(key=lambda option: option.total_monthly_usd)
        return options

    async def estimate_current_cost(
        self,
        feature: FeatureVector,
        provider: str,
        region: str,
        tier: str,
        currency: str,
    ) -> TierCostBreakdown:
        """Estimate baseline cost for current provider/region/tier."""
        pricing = self._catalog.get_tier(provider, region, tier)
        return await self._estimate_tier_cost(
            feature=feature,
            provider=provider,
            region=region,
            tier=tier,
            tier_pricing=pricing,
            currency=currency,
        )

    async def _estimate_tier_cost(
        self,
        feature: FeatureVector,
        provider: str,
        region: str,
        tier: str,
        tier_pricing: TierPricing,
        currency: str,
    ) -> TierCostBreakdown:
        size_gb = max(0.0, feature.object_size_gb)

        expected_retrieval_gb = size_gb * min(1.0, feature.access_frequency_30d * 0.08)
        expected_egress_gb = size_gb * min(1.0, feature.access_frequency_30d * 0.03)

        storage_cost = size_gb * tier_pricing.storage_cost_gb_month_usd
        retrieval_cost = expected_retrieval_gb * tier_pricing.retrieval_cost_gb_usd
        egress_cost = expected_egress_gb * tier_pricing.data_egress_cost_gb_usd
        retention_penalty = self._retention_penalty(feature, tier_pricing, size_gb)

        monthly_total = storage_cost + retrieval_cost + egress_cost + retention_penalty
        yearly_total = monthly_total * 12

        fx_rate = await self._converter.get_rate(currency)
        monthly_converted = monthly_total * fx_rate
        yearly_converted = yearly_total * fx_rate

        return TierCostBreakdown(
            provider=provider,
            region=region,
            tier=tier,
            storage_cost_usd=round(storage_cost, 6),
            retrieval_cost_usd=round(retrieval_cost, 6),
            retention_penalty_usd=round(retention_penalty, 6),
            egress_cost_usd=round(egress_cost, 6),
            total_monthly_usd=round(monthly_total, 6),
            total_yearly_usd=round(yearly_total, 6),
            fx_rate=round(fx_rate, 6),
            currency=currency.upper(),
            total_monthly_converted=round(monthly_converted, 6),
            total_yearly_converted=round(yearly_converted, 6),
            min_retention_days=tier_pricing.min_retention_days,
        )

    @staticmethod
    def _retention_penalty(feature: FeatureVector, tier_pricing: TierPricing, size_gb: float) -> float:
        if tier_pricing.min_retention_days <= 0:
            return 0.0

        if feature.days_since_last_access >= tier_pricing.min_retention_days:
            return 0.0

        shortfall = tier_pricing.min_retention_days - feature.days_since_last_access
        penalty_factor = shortfall / tier_pricing.min_retention_days
        return size_gb * tier_pricing.early_delete_cost_gb_usd * max(0.0, penalty_factor)
