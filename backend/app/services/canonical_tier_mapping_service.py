from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import CanonicalTierMapping, CloudProvider, DataTemperature


DEFAULT_CANONICAL_MAPPINGS: list[tuple[CloudProvider, str, DataTemperature]] = [
    (CloudProvider.AWS, "S3 Standard", DataTemperature.HOT),
    (CloudProvider.AWS, "Standard-IA", DataTemperature.COLD),
    (CloudProvider.AWS, "One Zone-IA", DataTemperature.COLD),
    (CloudProvider.AWS, "Glacier", DataTemperature.ARCHIVE),
    (CloudProvider.AWS, "Deep Archive", DataTemperature.ARCHIVE),
    (CloudProvider.GCP, "Standard", DataTemperature.HOT),
    (CloudProvider.GCP, "Nearline", DataTemperature.COLD),
    (CloudProvider.GCP, "Coldline", DataTemperature.COLD),
    (CloudProvider.GCP, "Archive", DataTemperature.ARCHIVE),
    (CloudProvider.AZURE, "Hot Blob", DataTemperature.HOT),
    (CloudProvider.AZURE, "Cool Blob", DataTemperature.COLD),
    (CloudProvider.AZURE, "Archive Blob", DataTemperature.ARCHIVE),
]


class CanonicalTierMappingService:
    def __init__(self, db: Session):
        self.db = db

    def ensure_defaults(self) -> None:
        existing = self.db.scalars(select(CanonicalTierMapping)).all()
        by_key = {(row.cloud.value, row.native_tier.strip().lower()): row for row in existing}

        changed = False
        for cloud, native_tier, canonical_tier in DEFAULT_CANONICAL_MAPPINGS:
            key = (cloud.value, native_tier.strip().lower())
            row = by_key.get(key)
            if not row:
                self.db.add(
                    CanonicalTierMapping(
                        cloud=cloud,
                        native_tier=native_tier,
                        canonical_tier=canonical_tier,
                        is_active=True,
                    )
                )
                changed = True
                continue
            if row.canonical_tier != canonical_tier or not row.is_active:
                row.canonical_tier = canonical_tier
                row.is_active = True
                changed = True
        if changed:
            self.db.commit()

    def resolve(self, *, cloud: CloudProvider, native_tier: str) -> DataTemperature | None:
        normalized = native_tier.strip().lower()
        if not normalized:
            return None
        row = self.db.scalar(
            select(CanonicalTierMapping).where(
                CanonicalTierMapping.cloud == cloud,
                CanonicalTierMapping.is_active.is_(True),
                CanonicalTierMapping.native_tier == native_tier,
            )
        )
        if row:
            return row.canonical_tier

        # Case-insensitive fallback for legacy rows.
        rows = self.db.scalars(
            select(CanonicalTierMapping).where(
                CanonicalTierMapping.cloud == cloud,
                CanonicalTierMapping.is_active.is_(True),
            )
        ).all()
        for item in rows:
            if item.native_tier.strip().lower() == normalized:
                return item.canonical_tier
        return None
