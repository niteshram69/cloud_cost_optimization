"""FX conversion with pluggable provider and daily refresh semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol


@dataclass(slots=True)
class FXSnapshot:
    """Exchange rates relative to USD."""

    as_of: date
    rates: dict[str, float]


class FXRateProvider(Protocol):
    """Contract for FX providers."""

    async def get_latest(self) -> FXSnapshot:
        """Return latest rates relative to USD."""


class StaticFXRateProvider:
    """Static provider used by default for deterministic behavior."""

    def __init__(self, rates: dict[str, float] | None = None):
        self._rates = rates or {
            "USD": 1.0,
            "INR": 83.10,
            "EUR": 0.92,
            "GBP": 0.79,
            "JPY": 151.2,
        }

    async def get_latest(self) -> FXSnapshot:
        return FXSnapshot(as_of=datetime.now(UTC).date(), rates=self._rates)


class CurrencyConverter:
    """Converts USD costs to target currencies with daily refresh."""

    def __init__(self, provider: FXRateProvider):
        self._provider = provider
        self._snapshot: FXSnapshot | None = None

    async def convert(self, amount_usd: float, currency: str) -> float:
        """Convert USD amount to target currency."""
        snapshot = await self._ensure_snapshot()
        code = currency.upper()
        rate = snapshot.rates.get(code)
        if rate is None:
            raise KeyError(f"Unsupported currency: {code}")
        return amount_usd * rate

    async def get_rate(self, currency: str) -> float:
        snapshot = await self._ensure_snapshot()
        code = currency.upper()
        rate = snapshot.rates.get(code)
        if rate is None:
            raise KeyError(f"Unsupported currency: {code}")
        return rate

    async def _ensure_snapshot(self) -> FXSnapshot:
        now = datetime.now(UTC).date()
        if self._snapshot is None or self._snapshot.as_of < now:
            self._snapshot = await self._provider.get_latest()
        return self._snapshot
