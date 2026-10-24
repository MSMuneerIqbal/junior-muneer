"""Task progress, outputs and per-task limits (P10-03/04)."""
from alembic import op
import sqlalchemy as sa

revision = "f4b6c8d0e2a5"
down_revision = "e2a4c6e8f0b1"
branch_labels = None
depends_on = None


def upgrade():
    columns = [
        sa.Column("worker", sa.String(30), nullable=False, server_default="junior_muneer"),
        sa.Column("output_format", sa.String(20), nullable=False, server_default="text"),
        sa.Column("stage", sa.String(200), nullable=False, server_default="Queued"),
        sa.Column("completed_steps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_steps", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("cost_limit_usd", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("time_limit_seconds", sa.Integer(), nullable=False, server_default="600"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("retries_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_ids", sa.JSON(), nullable=False, server_default="[]"),
    ]
    with op.batch_alter_table("background_tasks") as batch:
        for column in columns:
            batch.add_column(column)


def downgrade():
    with op.batch_alter_table("background_tasks") as batch:
        for name in ("worker", "output_format", "stage", "completed_steps", "total_steps", "started_at",
                     "updated_at", "cost_limit_usd", "time_limit_seconds", "max_retries", "retries_used", "file_ids"):
            batch.drop_column(name)
