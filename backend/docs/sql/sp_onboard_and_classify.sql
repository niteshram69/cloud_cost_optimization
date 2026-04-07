-- ========================================================
-- Cloudteck Cold-Start Onboarding + Classification
-- MySQL 8.0+
-- Stored Procedure: sp_onboard_and_classify
-- ========================================================
-- IMPORTANT:
-- - Current Cloudteck schema uses `storage_records` (not `resources`)
-- - metric_history FK is `resource_record_id`
-- - circuit_breaker_events.action_attempted enum does not include DATA_IMPUTATION,
--   so that logical action is captured in failure_details JSON.
-- ========================================================

DELIMITER $$

DROP PROCEDURE IF EXISTS sp_onboard_and_classify $$

CREATE PROCEDURE sp_onboard_and_classify()
BEGIN
    DECLARE v_history_rows_generated BIGINT DEFAULT 0;
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
        resource_name VARCHAR(255) NOT NULL,
        provider ENUM('AWS', 'AZURE', 'GCP', 'MULTI') NOT NULL,
        region VARCHAR(80) NOT NULL,
        requests_30d BIGINT NOT NULL DEFAULT 0,
        size_bytes BIGINT UNSIGNED NOT NULL DEFAULT 0,
        target_class ENUM('HOT', 'COLD', 'ARCHIVE') NOT NULL
    ) ENGINE=InnoDB;

    -- 1) Detect ghost resources (active user resources with zero metric_history rows)
    INSERT INTO tmp_ghost_resources (
        resource_record_id,
        user_id,
        resource_name,
        provider,
        region,
        requests_30d,
        size_bytes,
        target_class
    )
    WITH latest_ingest AS (
        SELECT
            x.user_id,
            x.resource_name,
            x.requests_30d,
            x.size_bytes,
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
                ) AS size_bytes
            FROM ingested_records ir
        ) x
        WHERE x.resource_name IS NOT NULL
    )
    SELECT
        sr.id AS resource_record_id,
        sr.user_id,
        sr.resource_name,
        sr.provider,
        sr.region,
        GREATEST(0, COALESCE(li.requests_30d, 0)) AS requests_30d,
        GREATEST(0, COALESCE(li.size_bytes, 0)) AS size_bytes,
        CASE
            WHEN GREATEST(0, COALESCE(li.requests_30d, 0)) > 100 THEN 'HOT'
            WHEN GREATEST(0, COALESCE(li.requests_30d, 0)) BETWEEN 10 AND 100 THEN 'COLD'
            ELSE 'ARCHIVE'
        END AS target_class
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
        -- 2) Backfill synthetic last 30 days: CURRENT_DATE-30 to CURRENT_DATE-1
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
        WITH RECURSIVE calendar AS (
            SELECT CURRENT_DATE - INTERVAL 30 DAY AS history_date
            UNION ALL
            SELECT history_date + INTERVAL 1 DAY
            FROM calendar
            WHERE history_date < CURRENT_DATE - INTERVAL 1 DAY
        )
        SELECT
            g.resource_record_id,
            g.provider,
            c.history_date,
            GREATEST(
                0,
                FLOOR(
                    (COALESCE(g.requests_30d, 0) / 30.0)
                    * (
                        0.8
                        + (
                            RAND(CRC32(CONCAT(g.resource_record_id, '|', c.history_date)))
                            * 0.4
                        )
                    )
                )
            ) AS requests_24h,
            g.size_bytes,
            g.target_class AS tier_class,
            JSON_OBJECT(
                'method', 'linear_backfill_with_variance',
                'noise_range', '0.8x-1.2x',
                'requests_30d', COALESCE(g.requests_30d, 0)
            ) AS raw_telemetry,
            UTC_TIMESTAMP()
        FROM tmp_ghost_resources g
        CROSS JOIN calendar c
        LEFT JOIN metric_history mh
            ON mh.resource_record_id = g.resource_record_id
           AND mh.snapshot_date = c.history_date
        WHERE mh.history_id IS NULL;

        SET v_history_rows_generated = ROW_COUNT();

        -- 3) Force class alignment in metric_history for the backfilled 30-day window
        UPDATE metric_history mh
        INNER JOIN tmp_ghost_resources g
            ON g.resource_record_id = mh.resource_record_id
        SET mh.tier_class = g.target_class
        WHERE mh.snapshot_date BETWEEN CURRENT_DATE - INTERVAL 30 DAY AND CURRENT_DATE - INTERVAL 1 DAY;

        -- 4) Update primary resource classification
        UPDATE storage_records sr
        INNER JOIN tmp_ghost_resources g
            ON g.resource_record_id = sr.id
        SET
            sr.temperature = g.target_class,
            sr.updated_at = UTC_TIMESTAMP();

        -- 5) Ensure bucket object references reflect traffic + observation window
        UPDATE bucket_object_references bor
        INNER JOIN tmp_ghost_resources g
            ON (
                bor.storage_record_id = g.resource_record_id
                OR (bor.user_id = g.user_id AND bor.resource_name = g.resource_name)
            )
        SET
            bor.requests_30d = g.requests_30d,
            bor.created_at = LEAST(bor.created_at, TIMESTAMP(CURRENT_DATE - INTERVAL 30 DAY)),
            bor.last_observed_at = GREATEST(bor.last_observed_at, TIMESTAMP(CURRENT_DATE - INTERVAL 1 DAY)),
            bor.updated_at = UTC_TIMESTAMP();

        -- 6) Refresh bucket-level class/counters for touched buckets
        UPDATE bucket_aggregates ba
        INNER JOIN (
            SELECT
                bor.user_id,
                bor.bucket_id,
                bor.cloud_provider,
                bor.region,
                bor.storage_class,
                COUNT(*) AS total_objects,
                SUM(GREATEST(bor.requests_30d, 0)) AS total_requests_30d,
                AVG(GREATEST(bor.requests_30d, 0)) AS avg_requests_per_object
            FROM bucket_object_references bor
            INNER JOIN tmp_ghost_resources g
                ON (
                    bor.storage_record_id = g.resource_record_id
                    OR (bor.user_id = g.user_id AND bor.resource_name = g.resource_name)
                )
            GROUP BY
                bor.user_id,
                bor.bucket_id,
                bor.cloud_provider,
                bor.region,
                bor.storage_class
        ) agg
            ON ba.user_id = agg.user_id
           AND ba.bucket_id = agg.bucket_id
           AND ba.cloud_provider = agg.cloud_provider
           AND ba.region = agg.region
           AND ba.storage_class = agg.storage_class
        SET
            ba.total_objects = agg.total_objects,
            ba.total_requests_30d = agg.total_requests_30d,
            ba.avg_requests_per_object = agg.avg_requests_per_object,
            ba.temperature = CASE
                WHEN agg.total_requests_30d > 100 THEN 'HOT'
                WHEN agg.total_requests_30d BETWEEN 10 AND 100 THEN 'COLD'
                ELSE 'ARCHIVE'
            END,
            ba.classification_confidence = GREATEST(ba.classification_confidence, 0.95),
            ba.observation_days = GREATEST(ba.observation_days, 30),
            ba.updated_at = UTC_TIMESTAMP();

        -- 7) Audit onboarding action (one event per onboarded resource)
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
                'method', 'linear_backfill_with_variance',
                'target_class', g.target_class,
                'requests_30d', g.requests_30d
            ),
            'Cold-start auto-heal completed',
            UTC_TIMESTAMP(),
            UTC_TIMESTAMP()
        FROM tmp_ghost_resources g;
    END IF;

    COMMIT;

    DROP TEMPORARY TABLE IF EXISTS tmp_ghost_resources;

    SELECT
        'SUCCESS' AS status,
        v_resources_onboarded AS resources_onboarded,
        v_history_rows_generated AS history_rows_generated;
END $$

DELIMITER ;

