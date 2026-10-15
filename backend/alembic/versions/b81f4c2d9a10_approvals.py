"""approvals queue

Revision ID: b81f4c2d9a10
Revises: a7c3d9e1f2b4
Create Date: 2026-10-15 13:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b81f4c2d9a10'
down_revision: Union[str, Sequence[str], None] = 'a7c3d9e1f2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'approvals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('platform', sa.String(length=30), nullable=False),
        sa.Column('item_type', sa.String(length=40), nullable=False),
        sa.Column('action_type', sa.String(length=100), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('original_text', sa.Text(), nullable=False),
        sa.Column('edits', sa.JSON(), nullable=False),
        sa.Column('meta', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('from_outside', sa.Boolean(), nullable=False),
        sa.Column('reason', sa.String(length=300), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('approvals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_approvals_message_id'), ['message_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_approvals_platform'), ['platform'], unique=False)
        batch_op.create_index(batch_op.f('ix_approvals_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_approvals_updated_at'), ['updated_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('approvals', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_approvals_updated_at'))
        batch_op.drop_index(batch_op.f('ix_approvals_status'))
        batch_op.drop_index(batch_op.f('ix_approvals_platform'))
        batch_op.drop_index(batch_op.f('ix_approvals_message_id'))
    op.drop_table('approvals')
