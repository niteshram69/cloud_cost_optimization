"""Add dataset scoping to recommendations.

Revision ID: b002_recommendations_dataset
Revises: b001_finops_rec_hash
Create Date: 2026-03-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b002_recommendations_dataset"
down_revision = "b001_finops_rec_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "recommendations" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("recommendations")}
    if "dataset_id" not in columns:
        op.add_column(
            "recommendations",
            sa.Column("dataset_id", sa.Integer(), nullable=True),
        )
        op.create_index("ix_recommendations_dataset_id", "recommendations", ["dataset_id"])

    if bind.dialect.name != "sqlite" and "ingestion_jobs" in inspector.get_table_names():
        fk_names = {
            fk["name"]
            for fk in inspector.get_foreign_keys("recommendations")
            if fk.get("name")
        }
        if "fk_recommendations_dataset_id_ingestion_jobs" not in fk_names:
            op.create_foreign_key(
                "fk_recommendations_dataset_id_ingestion_jobs",
                "recommendations",
                "ingestion_jobs",
                ["dataset_id"],
                ["id"],
                ondelete="SET NULL",
            )

    unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("recommendations")
    }
    if "uq_recommendations_resource_dataset" not in unique_constraints:
        op.create_unique_constraint(
            "uq_recommendations_resource_dataset",
            "recommendations",
            ["resource_name", "dataset_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "recommendations" not in inspector.get_table_names():
        return

    unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("recommendations")
    }
    if "uq_recommendations_resource_dataset" in unique_constraints:
        op.drop_constraint(
            "uq_recommendations_resource_dataset",
            "recommendations",
            type_="unique",
        )

    if bind.dialect.name != "sqlite":
        fk_names = {
            fk["name"]
            for fk in inspector.get_foreign_keys("recommendations")
            if fk.get("name")
        }
        if "fk_recommendations_dataset_id_ingestion_jobs" in fk_names:
            op.drop_constraint(
                "fk_recommendations_dataset_id_ingestion_jobs",
                "recommendations",
                type_="foreignkey",
            )

    indexes = {index["name"] for index in inspector.get_indexes("recommendations")}
    if "ix_recommendations_dataset_id" in indexes:
        op.drop_index("ix_recommendations_dataset_id", table_name="recommendations")

    columns = {column["name"] for column in inspector.get_columns("recommendations")}
    if "dataset_id" in columns:
        op.drop_column("recommendations", "dataset_id")
