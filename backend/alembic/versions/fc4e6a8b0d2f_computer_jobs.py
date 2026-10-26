"""Persist approved local PC job status and bounded output."""

from alembic import op
import sqlalchemy as sa

revision = "fc4e6a8b0d2f"
down_revision = "fa2c4e6a8b0d"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "computer_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("approval_id", sa.Integer(), sa.ForeignKey("approvals.id", ondelete="SET NULL"), unique=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id", ondelete="SET NULL")),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("folder", sa.Text(), nullable=False),
        sa.Column("seconds", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column("output_chars", sa.Integer(), nullable=False),
        sa.Column("pid", sa.Integer()),
        sa.Column("exit_code", sa.Integer()),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_computer_jobs_conversation_id", "computer_jobs", ["conversation_id"])
    op.create_index("ix_computer_jobs_state", "computer_jobs", ["state"])


def downgrade():
    op.drop_table("computer_jobs")
