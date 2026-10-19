"""emails the watcher sorted (Phase 4)

Revision ID: d1f9a3b5c7e0
Revises: c0e8f2a4b6d9
Create Date: 2026-10-19 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd1f9a3b5c7e0'
down_revision: Union[str, Sequence[str], None] = 'c0e8f2a4b6d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'emails',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('gmail_id', sa.String(length=40), nullable=False),
        sa.Column('thread_id', sa.String(length=40), nullable=False),
        sa.Column('from_name', sa.String(length=200), nullable=False),
        sa.Column('from_address', sa.String(length=200), nullable=False),
        sa.Column('subject', sa.String(length=300), nullable=False),
        sa.Column('snippet', sa.Text(), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('category', sa.String(length=20), nullable=False),
        sa.Column('important', sa.Boolean(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('why', sa.String(length=300), nullable=False),
        sa.Column('notified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('gmail_id'),
    )
    with op.batch_alter_table('emails', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_emails_received_at'), ['received_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('emails', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_emails_received_at'))
    op.drop_table('emails')
