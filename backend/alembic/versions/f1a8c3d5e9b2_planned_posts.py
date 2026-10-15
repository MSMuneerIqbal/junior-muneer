"""planned posts

Revision ID: f1a8c3d5e9b2
Revises: e3f7b2c8d4a5
Create Date: 2026-10-15 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f1a8c3d5e9b2'
down_revision: Union[str, Sequence[str], None] = 'e3f7b2c8d4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('approvals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('planned_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('reminded_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(batch_op.f('ix_approvals_planned_at'), ['planned_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('approvals', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_approvals_planned_at'))
        batch_op.drop_column('reminded_at')
        batch_op.drop_column('planned_at')
