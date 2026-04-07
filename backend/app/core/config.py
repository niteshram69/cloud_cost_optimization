from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    project_name: str = "Cloudteck by Mindteck"
    project_tagline: str = "Intelligent Data. Optimal Cloud. Minimal Cost."
    environment: Literal["development", "staging", "production"] = "development"

    api_prefix: str = "/api"
    database_url: str = "mysql+pymysql://root@localhost:3306/cloudteck"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    api_key_secret: str = "change-me-api-key-secret"
    integration_credentials_secret: str | None = None

    bootstrap_admin_enabled: bool = True
    bootstrap_admin_email: str = "nitesh.r@mindteck.us"
    bootstrap_admin_password: str = "mind@123"
    bootstrap_admin_name: str = "Nitesh R"
    bootstrap_admin_company: str = "Mindteck"
    bootstrap_admin_cloud_provider: Literal["AWS", "AZURE", "GCP", "MULTI"] = "MULTI"

    otp_ttl_minutes: int = 10
    otp_resend_cooldown_seconds: int = 60
    otp_max_attempts: int = 5
    otp_length: int = 6
    otp_enabled: bool = False

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_tls: bool = True

    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None

    default_currency: str = "USD"
    default_region: str = "IN"
    trial_days: int = 14
    payment_grace_days: int = 5
    payment_enforcement_enabled: bool = False
    usage_flush_batch_size: int = 1000
    usage_redis_ttl_seconds: int = 86400
    schedule_official_sync_cron: str = "*/30 * * * *"
    ingestion_use_celery: bool = False

    public_dataset_max_rows: int = 5000
    public_dataset_request_timeout_seconds: int = 20
    aws_s3_pricing_url: str = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonS3/current/index.json"
    azure_pricing_url: str = "https://prices.azure.com/api/retail/prices"
    gcp_billing_catalog_url: str = "https://cloudbilling.googleapis.com/v1/services"
    gcp_storage_service_id: str = "6F81-5844-456A"
    gcp_billing_api_key: str | None = None
    pricing_request_timeout_seconds: int = 30
    pricing_max_pages: int = 12

    cors_origins: list[AnyHttpUrl] | list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    grafana_embed_url: str = "http://localhost:3001/d/cloudteck/storage-optimization"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache

def get_settings() -> Settings:
    return Settings()


settings = get_settings()
