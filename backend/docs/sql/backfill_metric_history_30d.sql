-- ========================================================
-- Cloudteck: 30-day synthetic metric_history backfill
-- MySQL 8.0+
-- ========================================================
-- Purpose:
-- - Backfill daily telemetry for active resources so observation window >= 30 days.
-- - Uses existing storage_records + latest ingested_records payload values.
-- - Idempotent: skips dates already present in metric_history.
--
-- Notes:
-- - Generates exactly 30 rows/resource for CURRENT_DATE-29 ... CURRENT_DATE.
-- - Daily requests = (requests_30d / 30) with deterministic +/-20% noise.
-- ========================================================

START TRANSACTION;

INSERT INTO metric_history (
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
),
latest_ingest AS (
    SELECT
        ir.user_id,
        JSON_UNQUOTE(JSON_EXTRACT(ir.raw_payload, '$.record.resource_id')) AS resource_name,
        CAST(
            COALESCE(
                JSON_UNQUOTE(JSON_EXTRACT(ir.raw_payload, '$.record.requests_30d')),
                '0'
            ) AS SIGNED
        ) AS requests_30d,
        CAST(
            COALESCE(
                JSON_UNQUOTE(JSON_EXTRACT(ir.raw_payload, '$.record.size_bytes')),
                '0'
            ) AS UNSIGNED
        ) AS size_bytes,
        JSON_UNQUOTE(JSON_EXTRACT(ir.raw_payload, '$.record.tier_class')) AS current_tier,
        ROW_NUMBER() OVER (
            PARTITION BY
                ir.user_id,
                JSON_UNQUOTE(JSON_EXTRACT(ir.raw_payload, '$.record.resource_id'))
            ORDER BY ir.created_at DESC, ir.id DESC
        ) AS rn
    FROM ingested_records ir
    WHERE JSON_EXTRACT(ir.raw_payload, '$.record.resource_id') IS NOT NULL
),
resource_base AS (
    SELECT
        sr.id AS resource_record_id,
        sr.provider,
        COALESCE(li.requests_30d, 0) AS requests_30d,
        COALESCE(li.size_bytes, 0) AS size_bytes,
        COALESCE(NULLIF(li.current_tier, ''), sr.temperature) AS tier_class
    FROM storage_records sr
    INNER JOIN users u
        ON u.id = sr.user_id
       AND u.is_active = 1
    LEFT JOIN latest_ingest li
        ON li.user_id = sr.user_id
       AND li.resource_name = sr.resource_name
       AND li.rn = 1
)
SELECT
    rb.resource_record_id,
    rb.provider,
    ds.snapshot_date,
    GREATEST(
        0,
        FLOOR(
            (COALESCE(rb.requests_30d, 0) / 30.0)
            * (
                0.8
                + (
                    RAND(CRC32(CONCAT(rb.resource_record_id, '|', ds.snapshot_date)))
                    * 0.4
                )
            )
        )
    ) AS requests_24h,
    rb.size_bytes,
    rb.tier_class,
    JSON_OBJECT(
        'source', 'synthetic_backfill',
        'backfill_window_days', 30,
        'base_requests_30d', COALESCE(rb.requests_30d, 0),
        'noise_band', '+/-20%'
    ) AS raw_telemetry,
    UTC_TIMESTAMP()
FROM resource_base rb
CROSS JOIN day_seq ds
LEFT JOIN metric_history mh
    ON mh.resource_record_id = rb.resource_record_id
   AND mh.snapshot_date = ds.snapshot_date
WHERE mh.history_id IS NULL;

COMMIT;

-- ========================================================
-- Verification
-- ========================================================
-- 1) Total rows and affected resources
SELECT
    COUNT(*) AS total_history_rows,
    COUNT(DISTINCT resource_record_id) AS resources_affected
FROM metric_history;

-- 2) Resource count with >=30 observed days in last 30-day window
SELECT
    COUNT(*) AS resources_with_observation_window_ge_30
FROM (
    SELECT
        mh.resource_record_id
    FROM metric_history mh
    WHERE mh.snapshot_date BETWEEN CURRENT_DATE - INTERVAL 29 DAY AND CURRENT_DATE
    GROUP BY mh.resource_record_id
    HAVING COUNT(DISTINCT mh.snapshot_date) >= 30
) q;

-- 3) Optional: resources still below threshold (should be 0)
SELECT
    sr.id AS resource_record_id,
    sr.resource_name,
    COUNT(DISTINCT mh.snapshot_date) AS observed_days
FROM storage_records sr
INNER JOIN users u
    ON u.id = sr.user_id
   AND u.is_active = 1
LEFT JOIN metric_history mh
    ON mh.resource_record_id = sr.id
   AND mh.snapshot_date BETWEEN CURRENT_DATE - INTERVAL 29 DAY AND CURRENT_DATE
GROUP BY sr.id, sr.resource_name
HAVING COUNT(DISTINCT mh.snapshot_date) < 30
ORDER BY observed_days ASC, sr.id ASC;
