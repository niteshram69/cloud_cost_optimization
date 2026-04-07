"""V2 API routes for hybrid multi-cloud storage optimization."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.api.schemas import OptimizationRequest, OptimizationResponse, TrainModelRequest, TrainModelResponse
from app.api.state import report_store
from app.collectors.access_logs import AccessLogCollector
from app.collectors.ingestion_service import MetadataIngestionService
from app.collectors.models import InventoryObjectRecord
from app.core.config import settings
from app.dashboards.schemas import AdminDashboardResponse, ClientDashboardResponse
from app.dashboards.service import DashboardAggregationService
from app.decision_engine.engine import HybridDecisionEngine
from app.decision_engine.types import DataTemperature
from app.feature_engineering.extractor import FeatureEngineeringService
from app.feature_engineering.models import FeatureVector
from app.ml_engine.model import StorageMLClassifier
from app.migration_engine.audit import MigrationAuditLogger
from app.migration_engine.engine import MigrationEngine
from app.migration_engine.gateways import GatewayFactory
from app.pricing_engine.catalog import PricingCatalog
from app.pricing_engine.engine import MultiCloudPricingEngine
from app.pricing_engine.fx import CurrencyConverter, StaticFXRateProvider
from app.rules_engine.policy import RuleBasedStorageClassifier

router = APIRouter(prefix="/api/v2", tags=["storage-optimization-v2"])


def _resolve_project_path(path_like: str) -> Path:
    path = Path(path_like)
    if path.is_absolute():
        return path
    project_root = Path(__file__).resolve().parents[2]
    return (project_root / path).resolve()


_inventory_service = MetadataIngestionService()
_access_log_collector = AccessLogCollector()
_feature_service = FeatureEngineeringService()
_rules_classifier = RuleBasedStorageClassifier()

_model_path = _resolve_project_path(settings.ML_MODEL_PATH)
_ml_classifier = StorageMLClassifier()
if _model_path.exists():
    try:
        _ml_classifier = StorageMLClassifier.load(str(_model_path))
    except Exception:
        # The service still runs with rule-based fallback if model loading fails.
        _ml_classifier = StorageMLClassifier()

_catalog = PricingCatalog(catalog_path=str(_resolve_project_path(settings.PRICING_CATALOG_PATH)))
_fx_converter = CurrencyConverter(StaticFXRateProvider())
_pricing_engine = MultiCloudPricingEngine(_catalog, _fx_converter)

_gateway_factory = GatewayFactory(azure_connection_string=settings.AZURE_BLOB_CONNECTION_STRING)
_audit_logger = MigrationAuditLogger(str(_resolve_project_path(settings.MIGRATION_AUDIT_LOG_PATH)))
_migration_engine = MigrationEngine(
    gateway_factory=_gateway_factory,
    audit_logger=_audit_logger,
    max_parallel=settings.MIGRATION_MAX_PARALLEL,
    max_ops_per_second=settings.MIGRATION_MAX_OPS_PER_SECOND,
)

_decision_engine = HybridDecisionEngine(
    feature_service=_feature_service,
    rules=_rules_classifier,
    ml_model=_ml_classifier,
    pricing=_pricing_engine,
    migration_engine=_migration_engine,
)

_dashboard_service = DashboardAggregationService()


@router.post("/optimize", response_model=OptimizationResponse)
async def optimize_storage(request: OptimizationRequest) -> OptimizationResponse:
    """Analyze and optimize object placement across AWS/GCP/Azure."""
    inventory_records = [
        InventoryObjectRecord(
            tenant_id=item.tenant_id,
            provider=item.provider.lower(),
            region=item.region,
            bucket=item.bucket,
            object_key=item.object_key,
            storage_tier=item.storage_tier,
            size_bytes=item.size_bytes,
            last_modified_at=item.last_modified_at,
            last_accessed_at=item.last_accessed_at,
            etag=item.etag,
            metadata={"growth_bytes_90d": str(item.growth_bytes_90d)},
        )
        for item in request.inventory
    ]

    access_events = _access_log_collector.parse_events([event.model_dump() for event in request.access_events])

    snapshots = _inventory_service.build_snapshots(
        inventory_records=inventory_records,
        access_events=access_events,
    )

    report = await _decision_engine.optimize_snapshots(
        snapshots=snapshots,
        mode=request.mode,
        currency=request.currency,
        ml_confidence_threshold=request.ml_confidence_threshold,
        allowed_regions=request.allowed_regions,
        delete_source_after_migration=request.delete_source_after_migration,
    )

    await report_store.add(report)
    return OptimizationResponse(**report.to_dict())


@router.post("/ml/train", response_model=TrainModelResponse)
async def train_ml_model(request: TrainModelRequest) -> TrainModelResponse:
    """Train adaptive ML classifier from labeled enterprise datasets."""
    if len(request.samples) < 20:
        raise HTTPException(status_code=400, detail="At least 20 labeled samples are required")

    features: list[FeatureVector] = []
    labels: list[DataTemperature] = []

    for sample in request.samples:
        features.append(
            FeatureVector(
                tenant_id=sample.tenant_id,
                object_id=sample.object_id,
                provider=sample.provider,
                region=sample.region,
                bucket="unknown",
                current_tier=sample.current_tier,
                object_size_gb=sample.object_size_gb,
                days_since_last_access=sample.days_since_last_access,
                access_frequency_30d=sample.access_frequency_30d,
                access_frequency_90d=sample.access_frequency_90d,
                read_write_ratio=sample.read_write_ratio,
                storage_growth_trend_gb_30d=sample.storage_growth_trend_gb_30d,
                access_pattern_entropy=sample.access_pattern_entropy,
                read_count_30d=sample.read_count_30d,
                write_count_30d=sample.write_count_30d,
                read_count_90d=sample.read_count_90d,
                write_count_90d=sample.write_count_90d,
            )
        )
        labels.append(DataTemperature(sample.label.upper()))

    summary = _ml_classifier.train(features=features, labels=labels)

    if request.persist_model:
        _model_path.parent.mkdir(parents=True, exist_ok=True)
        _ml_classifier.save(str(_model_path))

    return TrainModelResponse(
        model_version=summary.model_version,
        n_samples=summary.n_samples,
        accuracy=summary.accuracy,
        classes=summary.classes,
    )


@router.get("/dashboards/admin", response_model=AdminDashboardResponse)
async def admin_dashboard(currency: str = "USD") -> AdminDashboardResponse:
    """Global admin dashboard across tenants."""
    reports = await report_store.list_all()
    return _dashboard_service.build_admin_dashboard(reports=reports, currency=currency)


@router.get("/dashboards/client/{tenant_id}", response_model=ClientDashboardResponse)
async def client_dashboard(tenant_id: str, currency: str = "USD") -> ClientDashboardResponse:
    """Per-client dashboard with savings and regional comparisons."""
    reports = await report_store.list_all()
    return _dashboard_service.build_client_dashboard(
        tenant_id=tenant_id,
        reports=reports,
        currency=currency,
    )
