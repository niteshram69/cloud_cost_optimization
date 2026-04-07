-- ========================================================
-- Cloudteck Cold-Start Fix (MySQL 8.0+)
-- Stored Procedure: sp_onboard_new_resources
-- ========================================================
-- NOTE:
-- This repo schema uses `storage_records` + `ingested_records` (not `resources`).
-- Procedure onboards only ghost resources:
-- - active user resources
-- - with 0 rows in metric_history
--
-- Idempotent behavior:
-- - Never overwrites existing history
-- - Inserts only missing (resource_record_id, snapshot_date) rows
--
-- Audit behavior:
-- - Logs one circuit_breaker_events row per onboarded resource
-- - action_attempted enum in current schema does not include DATA_IMPUTATION,
--   so logical action is captured in failure_details JSON.
-- ========================================================

DELIMITER $$

DROP PROCEDURE IF EXISTS sp_onboard_new_resources $$

CREATE PROCEDURE sp_onboard_new_resources()
BEGIN
    DECLARE v_rows_generated BIGINT DEFAULT 0;
    DECLARE v_resources_onboarded BIGINT DEFAULT 0;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        DROP TEMPORARY TABLE IF EXISTS tmp_ghost_resources;
        RESIGNAL;
    END;

    START TRANSACTION;

    DROP TEMPORARY TABLE IF EXISTS tmp_ghost_resources;
    CREATE TEMPORARY TABLE tmp_ghost_resources (
        resource_record_id INT NOT NULL PRIMARY KEY,
        user_id INT NOT NULL,
        provider ENUM('AWS', 'AZURE', 'GCP', 'MULTI') NOT NULL,
        requests_30d BIGINT NOT NULL DEFAULT 0,
        size_bytes BIGINT UNSIGNED NOT NULL DEFAULT 0,
        tier_class VARCHAR(64) NOT NULL
    ) ENGINE=Memory;

    INSERT INTO tmp_ghost_resources (
        resource_record_id,
        user_id,
        provider,
        requests_30d,
        size_bytes,
        tier_class
    )
    WITH latest_ingest AS (
        SELECT
            x.user_id,
            x.resource_name,
            x.requests_30d,
            x.size_bytes,
            x.current_tier,
            ROW_NUMBER() OVER (
                PARTITION BY x.user_id, x.resource_name
                ORDER BY x.created_at DESC, x.id DESC
            ) AS rn
        FROM (
            SELECT
                ir.id,
                ir.user_id,
                ir.created_at,
                COALESCE(
                    JSON_UNQUOTE(JSON_EXTRACT(ir.raw_payload, '$.record.resource_id')),
                    JSON_UNQUOTE(JSON_EXTRACT(ir.normalized_payload, '$.record.resource_id')),
                    JSON_UNQUOTE(JSON_EXTRACT(ir.normalized_payload, '$.attributes.record.resource_id'))
                ) AS resource_name,
                CAST(
                    COALESCE(
                        JSON_UNQUOTE(JSON_EXTRACT(ir.raw_payload, '$.record.requests_30d')),
                        JSON_UNQUOTE(JSON_EXTRACT(ir.normalized_payload, '$.record.requests_30d')),
                        JSON_UNQUOTE(JSON_EXTRACT(ir.normalized_payload, '$.attributes.record.requests_30d')),
                        '0'
                    ) AS SIGNED
                ) AS requests_30d,
                CAST(
                    COALESCE(
                        JSON_UNQUOTE(JSON_EXTRACT(ir.raw_payload, '$.record.size_bytes')),
                        JSON_UNQUOTE(JSON_EXTRACT(ir.normalized_payload, '$.record.size_bytes')),
                        JSON_UNQUOTE(JSON_EXTRACT(ir.normalized_payload, '$.attributes.record.size_bytes')),
                        '0'
                    ) AS UNSIGNED
                ) AS size_bytes,
                COALESCE(
                    JSON_UNQUOTE(JSON_EXTRACT(ir.raw_payload, '$.record.current_tier')),
                    JSON_UNQUOTE(JSON_EXTRACT(ir.raw_payload, '$.record.tier_class')),
                    JSON_UNQUOTE(JSON_EXTRACT(ir.normalized_payload, '$.record.current_tier')),
                    JSON_UNQUOTE(JSON_EXTRACT(ir.normalized_payload, '$.record.tier_class')),
                    JSON_UNQUOTE(JSON_EXTRACT(ir.normalized_payload, '$.attributes.record.current_tier')),
                    JSON_UNQUOTE(JSON_EXTRACT(ir.normalized_payload, '$.attributes.record.tier_class'))
                ) AS current_tier
            FROM ingested_records ir
        ) x
        WHERE x.resource_name IS NOT NULL
    )
    SELECT
        sr.id AS resource_record_id,
        sr.user_id,
        sr.provider,
        GREATEST(0, COALESCE(li.requests_30d, 0)) AS requests_30d,
        GREATEST(0, COALESCE(li.size_bytes, 0)) AS size_bytes,
        COALESCE(NULLIF(li.current_tier, ''), sr.temperature) AS tier_class
    FROM storage_records sr
    INNER JOIN users u
        ON u.id = sr.user_id
       AND u.is_active = 1
    LEFT JOIN latest_ingest li
        ON li.user_id = sr.user_id
       AND li.resource_name = sr.resource_name
       AND li.rn = 1
    LEFT JOIN metric_history mh_any
        ON mh_any.resource_record_id = sr.id
    WHERE mh_any.history_id IS NULL;

    SELECT COUNT(*) INTO v_resources_onboarded FROM tmp_ghost_resources;

    IF v_resources_onboarded > 0 THEN
        INSERT IGNORE INTO metric_history (
            resource_record_id,
            provider,
            snapshot_date,
            requests_24h,
            size_bytes,
            tier_class,
            raw_telemetry,
            created_at
        )
        WITH RECURSIVE day_seq AS (
            SELECT CURRENT_DATE - INTERVAL 29 DAY AS snapshot_date
            UNION ALL
            SELECT snapshot_date + INTERVAL 1 DAY
            FROM day_seq
            WHERE snapshot_date < CURRENT_DATE
        )
        SELECT
            g.resource_record_id,
            g.provider,
            d.snapshot_date,
            GREATEST(
                0,
                FLOOR(
                    (COALESCE(g.requests_30d, 0) / 30.0)
                    * (
                        0.8
                        + (
                            RAND(CRC32(CONCAT(g.resource_record_id, '|', d.snapshot_date)))
                            * 0.4
                        )
                    )
                )
            ) AS requests_24h,
            g.size_bytes,
            g.tier_class,
            JSON_OBJECT(
                'method', 'linear_backfill_with_variance',
                'noise_range', '0.8x-1.2x',
                'base_requests_30d', COALESCE(g.requests_30d, 0),
                'generated_window_days', 30
            ) AS raw_telemetry,
            UTC_TIMESTAMP()
        FROM tmp_ghost_resources g
        CROSS JOIN day_seq d
        LEFT JOIN metric_history mh
            ON mh.resource_record_id = g.resource_record_id
           AND mh.snapshot_date = d.snapshot_date
        WHERE mh.history_id IS NULL;

        SET v_rows_generated = ROW_COUNT();

        INSERT INTO circuit_breaker_events (
            resource_record_id,
            user_id,
            migration_plan_id,
            action_attempted,
            outcome,
            failure_code,
            failure_details,
            rollback_reason,
            occurred_at,
            backoff_until
        )
        SELECT
            g.resource_record_id,
            g.user_id,
            NULL,
            'MIGRATE_TO_STANDARD_IA',
            'BLOCKED_PRE_FLIGHT',
            'ONBOARDING_SUCCESS',
            JSON_OBJECT(
                'action_attempted', 'DATA_IMPUTATION',
                'method', 'linear_backfill_with_variance'
            ),
            'Cold-start onboarding completed',
            UTC_TIMESTAMP(),
            UTC_TIMESTAMP()
        FROM tmp_ghost_resources g;
    END IF;

    COMMIT;

    DROP TEMPORARY TABLE IF EXISTS tmp_ghost_resources;

    SELECT
        'Success' AS status,
        v_resources_onboarded AS resources_onboarded,
        v_rows_generated AS history_rows_generated;
END $$

DELIMITER ;

