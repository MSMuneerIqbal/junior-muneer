"""action runs (run at most once)

Revision ID: a7c3d9e1f2b4
Revises: e00e81b8f480
Create Date: 2026-10-15 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a7c3d9e1f2b4'
down_revision: Union[str, Sequence[str], None] = 'e00e81b8f480'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'action_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=200), nullable=False),
        sa.Column('action_type', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('detail', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key'),
    )
    with op.batch_alter_table('action_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_action_runs_action_type'), ['action_type'], unique=False)

def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('action_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_action_runs_action_type'))
    op.drop_table('action_runs')
