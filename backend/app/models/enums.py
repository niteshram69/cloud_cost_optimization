import enum


class UserRole(str, enum.Enum):
    USER = "USER"
    ADMIN = "ADMIN"


class CloudProvider(str, enum.Enum):
    AWS = "AWS"
    AZURE = "AZURE"
    GCP = "GCP"
    MULTI = "MULTI"


class DataTemperature(str, enum.Enum):
    HOT = "HOT"
    COLD = "COLD"
    ARCHIVE = "ARCHIVE"


class RecommendationStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACCEPTED = "ACCEPTED"
    DISMISSED = "DISMISSED"


class MigrationStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class OTPPurpose(str, enum.Enum):
    REGISTRATION = "REGISTRATION"
    PASSWORD_RESET = "PASSWORD_RESET"


class AccountState(str, enum.Enum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    PAYMENT_DUE = "PAYMENT_DUE"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"


class PlanCode(str, enum.Enum):
    FREE = "FREE"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"


class DataSourceType(str, enum.Enum):
    OFFICIAL_API = "OFFICIAL_API"
    WEBHOOK = "WEBHOOK"
    USER_SUBMITTED = "USER_SUBMITTED"


class IngestionMethod(str, enum.Enum):
    OFFICIAL_API = "OFFICIAL_API"
    WEBHOOK = "WEBHOOK"
    USER_REST = "USER_REST"
    USER_FILE_UPLOAD = "USER_FILE_UPLOAD"
    SDK_EVENT = "SDK_EVENT"


class UsageBucket(str, enum.Enum):
    HOUR = "HOUR"
    DAY = "DAY"


class BillingCycleStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    INVOICED = "INVOICED"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    PAID = "PAID"
    FAILED = "FAILED"
    VOID = "VOID"


class PaymentProvider(str, enum.Enum):
    RAZORPAY = "RAZORPAY"


class PaymentStatus(str, enum.Enum):
    CREATED = "CREATED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class SubscriptionStatus(str, enum.Enum):
    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CANCELLED = "CANCELLED"


class WebhookProcessStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"


class DecisionState(str, enum.Enum):
    EXPLORATORY = "EXPLORATORY"
    PREDICTED = "PREDICTED"
    FALLBACK = "FALLBACK"
    NO_OP = "NO_OP"
    BLOCKED = "BLOCKED"


class ExecutionEligibility(str, enum.Enum):
    NONE = "NONE"
    DRY_RUN_ELIGIBLE = "DRY_RUN_ELIGIBLE"
    EXECUTABLE = "EXECUTABLE"
    # Backward-compatible aliases (deprecated).
    MANUAL_OVERRIDE_ALLOWED = "DRY_RUN_ELIGIBLE"
    EXECUTION_ALLOWED = "EXECUTABLE"


class PricingConfidence(str, enum.Enum):
    REAL = "REAL"
    EXPORT = "EXPORT"
    ESTIMATE = "ESTIMATE"


class MigrationLifecycleState(str, enum.Enum):
    PLANNED = "PLANNED"
    APPROVED = "APPROVED"
    DRY_RUN = "DRY_RUN"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    ROLLED_BACK = "ROLLED_BACK"
    BLOCKED = "BLOCKED"


class OptimizationAction(str, enum.Enum):
    MOVE_TO_PREDICTED_TIER = "MOVE_TO_PREDICTED_TIER"
    MOVE_TO_STANDARD_IA = "MOVE_TO_STANDARD_IA"
    RETAIN = "RETAIN"


class GovernanceRuleType(str, enum.Enum):
    MAX_REQUESTS = "MAX_REQUESTS"
    MIN_AGE_DAYS = "MIN_AGE_DAYS"
    FORCED_RETAIN = "FORCED_RETAIN"
    MIN_CONFIDENCE_THRESHOLD = "MIN_CONFIDENCE_THRESHOLD"
    LATENCY_THRESHOLD_MS = "LATENCY_THRESHOLD_MS"
    ACCESS_SPIKE_PERCENT = "ACCESS_SPIKE_PERCENT"
    ERROR_RATE_PERCENT = "ERROR_RATE_PERCENT"


class MigrationExecutionMode(str, enum.Enum):
    MANUAL = "MANUAL"


class CircuitBreakerAction(str, enum.Enum):
    MIGRATE_TO_ARCHIVE = "MIGRATE_TO_ARCHIVE"
    MIGRATE_TO_COLD = "MIGRATE_TO_COLD"
    MIGRATE_TO_STANDARD_IA = "MIGRATE_TO_STANDARD_IA"


class CircuitBreakerOutcome(str, enum.Enum):
    BLOCKED_PRE_FLIGHT = "BLOCKED_PRE_FLIGHT"
    ROLLED_BACK_POST_MIGRATION = "ROLLED_BACK_POST_MIGRATION"


class RiskCode(str, enum.Enum):
    LATENCY = "LATENCY"
    RETRIEVAL_COST = "RETRIEVAL_COST"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
