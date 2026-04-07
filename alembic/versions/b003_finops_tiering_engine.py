"""Expand finops resources for tiering signals and relax recommendation classification.

Revision ID: b003_finops_tiering_engine
Revises: b002_recommendations_dataset
Create Date: 2026-03-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "b003_finops_tiering_engine"
down_revision = "b002_recommendations_dataset"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column, inspector: sa.Inspector) -> None:
    columns = {col["name"] for col in inspector.get_columns(table)}
    if column.name in columns:
        return
    op.add_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "finops_resources" in inspector.get_table_names():
        _add_column_if_missing(
            "finops_resources",
            sa.Column("region", sa.String(length=80), nullable=True),
            inspector,
        )
        _add_column_if_missing(
            "finops_resources",
            sa.Column("intent_tier", sa.String(length=120), nullable=True),
            inspector,
        )
        _add_column_if_missing(
            "finops_resources",
            sa.Column("object_size_bytes", sa.Integer(), nullable=True),
            inspector,
        )
        _add_column_if_missing(
            "finops_resources",
            sa.Column("object_age_days", sa.Integer(), nullable=True),
            inspector,
        )
        _add_column_if_missing(
            "finops_resources",
            sa.Column("last_access_days", sa.Integer(), nullable=True),
            inspector,
        )
        _add_column_if_missing(
            "finops_resources",
            sa.Column("requests_90d", sa.Integer(), nullable=True),
            inspector,
        )
        _add_column_if_missing(
            "finops_resources",
            sa.Column("read_write_ratio", sa.Float(), nullable=True),
            inspector,
        )
        _add_column_if_missing(
            "finops_resources",
            sa.Column("access_std_dev", sa.Float(), nullable=True),
            inspector,
        )
        _add_column_if_missing(
            "finops_resources",
            sa.Column("storage_cost_per_gb", sa.Float(), nullable=True),
            inspector,
        )
        _add_column_if_missing(
            "finops_resources",
            sa.Column("retrieval_cost_per_gb", sa.Float(), nullable=True),
            inspector,
        )
        _add_column_if_missing(
            "finops_resources",
            sa.Column("estimated_monthly_cost_usd", sa.Float(), nullable=True),
            inspector,
        )
        _add_column_if_missing(
            "finops_resources",
            sa.Column("billing_realism", sa.String(length=20), nullable=True),
            inspector,
        )
        _add_column_if_missing(
            "finops_resources",
            sa.Column("integration_permission", sa.String(length=20), nullable=True),
            inspector,
        )

    if "finops_recommendations" in inspector.get_table_names():
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("finops_recommendations", recreate="always") as batch:
                batch.alter_column(
                    "classification",
                    type_=sa.String(length=32),
                    existing_nullable=False,
                )
        else:
            op.alter_column(
                "finops_recommendations",
                "classification",
                type_=sa.String(length=32),
                existing_nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "finops_recommendations" in inspector.get_table_names():
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("finops_recommendations", recreate="always") as batch:
                batch.alter_column(
                    "classification",
                    type_=sa.String(length=32),
                    existing_nullable=False,
                )
        else:
            op.alter_column(
                "finops_recommendations",
                "classification",
                type_=sa.String(length=32),
                existing_nullable=False,
            )

    if "finops_resources" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("finops_resources")}
        for column_name in [
            "integration_permission",
            "billing_realism",
            "estimated_monthly_cost_usd",
            "retrieval_cost_per_gb",
            "storage_cost_per_gb",
            "access_std_dev",
            "read_write_ratio",
            "requests_90d",
            "last_access_days",
            "object_age_days",
            "object_size_bytes",
            "intent_tier",
            "region",
        ]:
            if column_name in columns:
                op.drop_column("finops_resources", column_name)
