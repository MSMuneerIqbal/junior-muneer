"""background tasks

Revision ID: f7a5b9c1d4e6
Revises: e6f4a8b0c3d5
Create Date: 2026-10-17 11:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f7a5b9c1d4e6'
down_revision: Union[str, Sequence[str], None] = 'e6f4a8b0c3d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'background_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('request', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('error', sa.Text(), nullable=False),
        sa.Column('cost_usd', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('background_tasks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_background_tasks_conversation_id'), ['conversation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_background_tasks_status'), ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('background_tasks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_background_tasks_status'))
        batch_op.drop_index(batch_op.f('ix_background_tasks_conversation_id'))
    op.drop_table('background_tasks')
