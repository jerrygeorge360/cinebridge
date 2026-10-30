"""Persist private candidate contributor provenance.

Revision ID: 0005_candidate_contributor_provenance
Revises: 0004_qloo_resolution_evidence
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_candidate_contributor_provenance"
down_revision = "0004_qloo_resolution_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("recommendation_candidates")
    }
    if "contributor_provenance" not in existing:
        op.add_column(
            "recommendation_candidates",
            sa.Column(
                "contributor_provenance",
                sa.Text(),
                nullable=False,
                server_default="[]",
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("recommendation_candidates") as batch:
        batch.drop_column("contributor_provenance")
