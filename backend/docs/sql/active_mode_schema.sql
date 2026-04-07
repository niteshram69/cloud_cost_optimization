-- Active Mode schema extensions (MySQL 8.0+)
-- Cloudteck by Mindteck

-- ========================================================
-- 1) metric_history (The Memory)
-- ========================================================
CREATE TABLE IF NOT EXISTS metric_history (
    history_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    resource_record_id INT NOT NULL,
    provider ENUM('AWS', 'AZURE', 'GCP', 'MULTI') NOT NULL,
    snapshot_date DATE NOT NULL,
    requests_24h INT UNSIGNED NOT NULL DEFAULT 0,
    size_bytes BIGINT UNSIGNED NOT NULL DEFAULT 0,
    tier_class VARCHAR(64) NOT NULL,
    raw_telemetry JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_metric_history_resource
        FOREIGN KEY (resource_record_id) REFERENCES storage_records(id)
        ON DELETE CASCADE,

    CONSTRAINT uq_metric_history_resource_date
        UNIQUE (resource_record_id, snapshot_date),

    INDEX idx_metric_history_resource_window (resource_record_id, snapshot_date),
    INDEX idx_metric_history_snapshot_provider (snapshot_date, provider)
) ENGINE=InnoDB COMMENT='Daily time-series telemetry for confidence/window calculations';

-- ========================================================
-- 2) governance_policies (The Steering Wheel)
-- ========================================================
CREATE TABLE IF NOT EXISTS governance_policies (
    policy_id INT AUTO_INCREMENT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    target_tag_key VARCHAR(64) NOT NULL DEFAULT 'Environment',
    target_tag_value VARCHAR(64) NULL,
    rule_type ENUM(
        'MAX_REQUESTS',
        'MIN_AGE_DAYS',
        'FORCED_RETAIN',
        'MIN_CONFIDENCE_THRESHOLD',
        'LATENCY_THRESHOLD_MS',
        'ACCESS_SPIKE_PERCENT',
        'ERROR_RATE_PERCENT'
    ) NOT NULL,
    threshold_value DECIMAL(12,4) NOT NULL,
    rule_metadata JSON NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_updated_by_user_id INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_governance_updated_by
        FOREIGN KEY (last_updated_by_user_id) REFERENCES users(id)
        ON DELETE SET NULL,

    CONSTRAINT uq_governance_policy_scope_rule
        UNIQUE (tenant_id, target_tag_key, target_tag_value, rule_type),

    INDEX idx_governance_policy_tenant (tenant_id, is_active)
) ENGINE=InnoDB COMMENT='Tenant/env scoped safety policies replacing hard-coded thresholds';

-- ========================================================
-- 3) circuit_breaker_events (The Feedback Loop)
-- ========================================================
CREATE TABLE IF NOT EXISTS circuit_breaker_events (
    event_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    resource_record_id INT NOT NULL,
    user_id INT NOT NULL,
    migration_plan_id BIGINT NULL,
    action_attempted ENUM('MIGRATE_TO_ARCHIVE', 'MIGRATE_TO_COLD', 'MIGRATE_TO_STANDARD_IA') NOT NULL,
    outcome ENUM('BLOCKED_PRE_FLIGHT', 'ROLLED_BACK_POST_MIGRATION') NOT NULL,
    failure_code VARCHAR(80) NOT NULL,
    failure_details JSON NULL,
    rollback_reason TEXT NULL,
    occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    backoff_until DATETIME NOT NULL,

    CONSTRAINT fk_circuit_resource
        FOREIGN KEY (resource_record_id) REFERENCES storage_records(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_circuit_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_circuit_plan
        FOREIGN KEY (migration_plan_id) REFERENCES migration_plans(id)
        ON DELETE SET NULL,

    INDEX idx_circuit_breaker_active_backoff (resource_record_id, backoff_until),
    INDEX idx_circuit_breaker_occurred (occurred_at)
) ENGINE=InnoDB COMMENT='Rollback and pre-flight block log with backoff timer to prevent flapping';

-- ========================================================
-- Supporting table: migration_plans (manual authorization pipeline)
-- ========================================================
CREATE TABLE IF NOT EXISTS migration_plans (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    recommendation_id INT NULL,
    resource_record_id INT NOT NULL,
    resource_id VARCHAR(255) NOT NULL,
    provider ENUM('AWS', 'AZURE', 'GCP', 'MULTI') NOT NULL,
    source_tier VARCHAR(120) NOT NULL,
    target_tier VARCHAR(120) NOT NULL,
    approved_target_tier VARCHAR(120) NOT NULL,
    ml_predicted_tier VARCHAR(120) NOT NULL,
    confidence_snapshot DOUBLE NOT NULL,
    guardrail_snapshot JSON NOT NULL,
    execution_mode ENUM('MANUAL') NOT NULL DEFAULT 'MANUAL',
    authorized_by INT NOT NULL,
    state ENUM('PLANNED', 'APPROVED', 'DRY_RUN', 'EXECUTING', 'COMPLETED', 'ROLLED_BACK', 'BLOCKED')
      NOT NULL DEFAULT 'PLANNED',
    override_confidence BOOLEAN NOT NULL DEFAULT FALSE,
    risks_acknowledged JSON NOT NULL,
    dry_run_report JSON NULL,
    execution_report JSON NULL,
    monitoring_report JSON NULL,
    rollback_reason TEXT NULL,
    authorized_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    executed_at DATETIME NULL,
    rolled_back_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_migration_plan_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_migration_plan_authorizer FOREIGN KEY (authorized_by) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_migration_plan_recommendation FOREIGN KEY (recommendation_id) REFERENCES recommendations(id) ON DELETE SET NULL,
    CONSTRAINT fk_migration_plan_resource FOREIGN KEY (resource_record_id) REFERENCES storage_records(id) ON DELETE CASCADE,

    INDEX idx_migration_plan_user_state (user_id, state),
    INDEX idx_migration_plan_resource (resource_id, created_at)
) ENGINE=InnoDB COMMENT='Deterministic zero-trust migration lifecycle records';

-- ========================================================
-- Supporting table: audit_events (explainability trail)
-- ========================================================
CREATE TABLE IF NOT EXISTS audit_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    migration_plan_id BIGINT NULL,
    who VARCHAR(128) NOT NULL,
    what VARCHAR(128) NOT NULL,
    resource VARCHAR(255) NOT NULL,
    confidence DOUBLE NOT NULL,
    guardrails JSON NOT NULL,
    risks_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    execution_result VARCHAR(64) NOT NULL,
    details JSON NULL,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_audit_event_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_audit_event_plan FOREIGN KEY (migration_plan_id) REFERENCES migration_plans(id) ON DELETE SET NULL,

    INDEX idx_audit_event_user_time (user_id, timestamp),
    INDEX idx_audit_event_resource (resource, timestamp)
) ENGINE=InnoDB COMMENT='Immutable explainability and authorization audit trail';
