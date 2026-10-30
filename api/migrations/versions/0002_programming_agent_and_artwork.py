"""Persist bounded programming briefs and deterministic TMDB artwork metadata.

Revision ID: 0002_programming_agent_and_artwork
Revises: 0001_initial_schema
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_programming_agent_and_artwork"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A prior interrupted startup may have applied an ALTER before Alembic
    # could stamp the revision.  Each additive field is therefore resumable.
    existing_run = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("recommendation_runs")}
    for column in (
        sa.Column("programming_brief", sa.Text(), nullable=True),
        sa.Column("agent_tools_used", sa.String(length=200), nullable=True),
        sa.Column("agent_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("agent_output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("agent_cost_usd_micros", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("agent_latency_ms", sa.Integer(), nullable=False, server_default="0"),
    ):
        if column.name not in existing_run:
            op.add_column("recommendation_runs", column)
    existing_candidate = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("recommendation_candidates")}
    for column in (
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("poster_path", sa.String(length=500), nullable=True),
        sa.Column("poster_looked_up_at", sa.DateTime(timezone=True), nullable=True),
    ):
        if column.name not in existing_candidate:
            op.add_column("recommendation_candidates", column)


def downgrade() -> None:
    with op.batch_alter_table("recommendation_candidates") as batch:
        batch.drop_column("poster_looked_up_at")
        batch.drop_column("poster_path")
        batch.drop_column("tmdb_id")
    with op.batch_alter_table("recommendation_runs") as batch:
        batch.drop_column("agent_latency_ms")
        batch.drop_column("agent_cost_usd_micros")
        batch.drop_column("agent_output_tokens")
        batch.drop_column("agent_input_tokens")
        batch.drop_column("agent_tools_used")
        batch.drop_column("programming_brief")
