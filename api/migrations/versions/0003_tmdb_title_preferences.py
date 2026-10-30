"""Store explicit TMDB selections separately from Qloo resolution metadata.

Revision ID: 0003_tmdb_title_preferences
Revises: 0002_programming_agent_and_artwork
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_tmdb_title_preferences"
down_revision = "0002_programming_agent_and_artwork"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("attendee_preferences")
    }
    for column in (
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("media_type", sa.String(length=12), nullable=True),
        sa.Column("release_date", sa.String(length=10), nullable=True),
        sa.Column("poster_path", sa.String(length=500), nullable=True),
        sa.Column("qloo_entity_id", sa.String(length=160), nullable=True),
        sa.Column(
            "qloo_resolution_status",
            sa.String(length=16),
            nullable=False,
            server_default="legacy",
        ),
    ):
        if column.name not in existing:
            op.add_column("attendee_preferences", column)


def downgrade() -> None:
    with op.batch_alter_table("attendee_preferences") as batch:
        batch.drop_column("qloo_resolution_status")
        batch.drop_column("qloo_entity_id")
        batch.drop_column("poster_path")
        batch.drop_column("release_date")
        batch.drop_column("media_type")
        batch.drop_column("tmdb_id")
