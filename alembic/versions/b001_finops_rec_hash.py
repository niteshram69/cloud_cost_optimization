"""Add resource_id + recommendation_hash to finops_recommendations with uniqueness.

Revision ID: b001_finops_rec_hash
Revises:
Create Date: 2026-03-10
"""

from __future__ import annotations

import hashlib
import json

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b001_finops_rec_hash"
down_revision = None
branch_labels = ("backend",)
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "finops_recommendations" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("finops_recommendations")}

    if "resource_id" not in columns:
        op.add_column(
            "finops_recommendations",
            sa.Column("resource_id", sa.String(length=255), nullable=True),
        )
        op.create_index(
            "ix_finops_recommendations_resource_id",
            "finops_recommendations",
            ["resource_id"],
        )

    if "recommendation_hash" not in columns:
        op.add_column(
            "finops_recommendations",
            sa.Column("recommendation_hash", sa.String(length=64), nullable=True),
        )
        op.create_index(
            "ix_finops_recommendations_recommendation_hash",
            "finops_recommendations",
            ["recommendation_hash"],
        )

    backfill_rows = bind.execute(
        sa.text(
            """
            SELECT r.id,
                   r.resource_pk,
                   fr.resource_id AS resource_id_value,
                   r.action,
                   r.decision_state,
                   r.classification,
                   r.recommended_provider,
                   r.recommended_storage_tier
            FROM finops_recommendations r
            JOIN finops_resources fr ON fr.id = r.resource_pk
            WHERE r.resource_id IS NULL
               OR r.resource_id = ''
               OR r.recommendation_hash IS NULL
               OR r.recommendation_hash = ''
            """
        )
    ).mappings().all()

    for row in backfill_rows:
        resource_id = row["resource_id_value"]
        payload = {
            "action": str(row["action"]),
            "decision_state": str(row["decision_state"]),
            "classification": str(row["classification"]),
            "recommended_provider": str(row["recommended_provider"]),
            "recommended_storage_tier": str(row["recommended_storage_tier"]),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        recommendation_hash = hashlib.sha256(encoded).hexdigest()
        bind.execute(
            sa.text(
                """
                UPDATE finops_recommendations
                SET resource_id = :resource_id,
                    recommendation_hash = :recommendation_hash
                WHERE id = :row_id
                """
            ),
            {
                "resource_id": resource_id,
                "recommendation_hash": recommendation_hash,
                "row_id": row["id"],
            },
        )

    duplicate_groups = bind.execute(
        sa.text(
            """
            SELECT resource_id, recommendation_hash, MIN(id) AS keep_id
            FROM finops_recommendations
            WHERE resource_id IS NOT NULL
              AND recommendation_hash IS NOT NULL
            GROUP BY resource_id, recommendation_hash
            HAVING COUNT(*) > 1
            """
        )
    ).mappings().all()

    for group in duplicate_groups:
        bind.execute(
            sa.text(
                """
                DELETE FROM finops_recommendations
                WHERE resource_id = :resource_id
                  AND recommendation_hash = :recommendation_hash
                  AND id <> :keep_id
                """
            ),
            {
                "resource_id": group["resource_id"],
                "recommendation_hash": group["recommendation_hash"],
                "keep_id": group["keep_id"],
            },
        )

    op.alter_column(
        "finops_recommendations",
        "resource_id",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.alter_column(
        "finops_recommendations",
        "recommendation_hash",
        existing_type=sa.String(length=64),
        nullable=False,
    )

    unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("finops_recommendations")
    }
    if "uq_finops_recommendation_resource_hash" not in unique_constraints:
        op.create_unique_constraint(
            "uq_finops_recommendation_resource_hash",
            "finops_recommendations",
            ["resource_id", "recommendation_hash"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "finops_recommendations" not in inspector.get_table_names():
        return

    unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("finops_recommendations")
    }
    if "uq_finops_recommendation_resource_hash" in unique_constraints:
        op.drop_constraint(
            "uq_finops_recommendation_resource_hash",
            "finops_recommendations",
            type_="unique",
        )

    indexes = {index["name"] for index in inspector.get_indexes("finops_recommendations")}
    if "ix_finops_recommendations_recommendation_hash" in indexes:
        op.drop_index("ix_finops_recommendations_recommendation_hash", table_name="finops_recommendations")
    if "ix_finops_recommendations_resource_id" in indexes:
        op.drop_index("ix_finops_recommendations_resource_id", table_name="finops_recommendations")

    columns = {column["name"] for column in inspector.get_columns("finops_recommendations")}
    if "recommendation_hash" in columns:
        op.drop_column("finops_recommendations", "recommendation_hash")
    if "resource_id" in columns:
        op.drop_column("finops_recommendations", "resource_id")
