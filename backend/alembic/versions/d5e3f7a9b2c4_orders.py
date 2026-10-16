"""fiverr orders

Revision ID: d5e3f7a9b2c4
Revises: c4d2e6f8a1b3
Create Date: 2026-10-16 19:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd5e3f7a9b2c4'
down_revision: Union[str, Sequence[str], None] = 'c4d2e6f8a1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(length=30), nullable=False),
        sa.Column('number', sa.String(length=40), nullable=False),
        sa.Column('buyer', sa.String(length=100), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('price', sa.String(length=50), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revisions_included', sa.Integer(), nullable=True),
        sa.Column('revisions_used', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('requirements', sa.JSON(), nullable=False),
        sa.Column('history', sa.JSON(), nullable=False),
        sa.Column('reminder_stage', sa.Integer(), nullable=False),
        sa.Column('paste_id', sa.Integer(), nullable=True),
        sa.Column('approval_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['approval_id'], ['approvals.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['paste_id'], ['pastes.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_orders_due_at'), ['due_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_orders_number'), ['number'], unique=False)
        batch_op.create_index(batch_op.f('ix_orders_status'), ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_orders_status'))
        batch_op.drop_index(batch_op.f('ix_orders_number'))
        batch_op.drop_index(batch_op.f('ix_orders_due_at'))
    op.drop_table('orders')
