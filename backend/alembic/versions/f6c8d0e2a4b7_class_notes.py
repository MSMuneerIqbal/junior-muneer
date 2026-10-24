"""Dated class-notes library and source provenance."""
from alembic import op
import sqlalchemy as sa

revision = "f6c8d0e2a4b7"
down_revision = "f4b6c8d0e2a5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("notes_folders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("name_key", sa.String(100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("class_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("folder_id", sa.Integer(), sa.ForeignKey("notes_folders.id"), nullable=False),
        sa.Column("subject", sa.String(120), nullable=False),
        sa.Column("class_date", sa.String(10), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("background_tasks.id", ondelete="SET NULL"), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_class_notes_class_date", "class_notes", ["class_date"])
    op.create_index("ix_class_notes_archived", "class_notes", ["archived"])
    op.create_index("ix_class_notes_folder_id", "class_notes", ["folder_id"])


def downgrade():
    op.drop_table("class_notes")
    op.drop_table("notes_folders")
