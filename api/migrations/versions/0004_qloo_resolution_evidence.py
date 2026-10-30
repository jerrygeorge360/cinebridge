"""Persist Qloo resolution type and a safe unresolved explanation.

Revision ID: 0004_qloo_resolution_evidence
Revises: 0003_tmdb_title_preferences
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_qloo_resolution_evidence"
down_revision = "0003_tmdb_title_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("attendee_preferences")
    }
    if "qloo_entity_type" not in existing:
        op.add_column("attendee_preferences", sa.Column("qloo_entity_type", sa.String(length=40)))
    if "qloo_resolution_reason" not in existing:
        op.add_column("attendee_preferences", sa.Column("qloo_resolution_reason", sa.String(length=160)))


def downgrade() -> None:
    with op.batch_alter_table("attendee_preferences") as batch:
        batch.drop_column("qloo_resolution_reason")
        batch.drop_column("qloo_entity_type")
