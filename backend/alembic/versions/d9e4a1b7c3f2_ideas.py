"""content ideas

Revision ID: d9e4a1b7c3f2
Revises: c5d2e8f3a7b1
Create Date: 2026-10-15 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd9e4a1b7c3f2'
down_revision: Union[str, Sequence[str], None] = 'c5d2e8f3a7b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'ideas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(length=30), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('angle', sa.Text(), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('approval_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['approval_id'], ['approvals.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('ideas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ideas_platform'), ['platform'], unique=False)
        batch_op.create_index(batch_op.f('ix_ideas_status'), ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('ideas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ideas_status'))
        batch_op.drop_index(batch_op.f('ix_ideas_platform'))
    op.drop_table('ideas')
