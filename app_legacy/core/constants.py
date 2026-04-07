"""Application-wide constants."""

from enum import Enum


# API Version
API_V1_PREFIX = "/api/v1"


# Ingestion Status
class IngestionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# Classification Categories
class ClassificationCategory(str, Enum):
    SENSITIVE = "sensitive"
    INTERNAL = "internal"
    PUBLIC = "public"
    ARCHIVE = "archive"
    UNKNOWN = "unknown"


# Cost Providers
class CloudProvider(str, Enum):
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    OTHER = "other"


# Decision Actions
class DecisionAction(str, Enum):
    ARCHIVE = "archive"
    DELETE = "delete"
    DOWNSIZE = "downsize"
    RIGHTSIZE = "rightsize"
    MIGRATE = "migrate"
    REVIEW = "review"
    NONE = "none"


# Webhook Status
class WebhookStatus(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
