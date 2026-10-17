"""your own feeds

Revision ID: b9d7e1f3a5c8
Revises: a8c6d0e2f4b7
Create Date: 2026-10-17 13:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b9d7e1f3a5c8'
down_revision: Union[str, Sequence[str], None] = 'a8c6d0e2f4b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'feeds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('item_count', sa.Integer(), nullable=False),
        sa.Column('last_read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url'),
    )
    op.create_table(
        'feed_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('feed_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['feed_id'], ['feeds.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('feed_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_feed_items_feed_id'), ['feed_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_feed_items_published_at'), ['published_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('feed_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_feed_items_published_at'))
        batch_op.drop_index(batch_op.f('ix_feed_items_feed_id'))
    op.drop_table('feed_items')
    op.drop_table('feeds')
