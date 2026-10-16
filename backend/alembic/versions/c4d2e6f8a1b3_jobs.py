"""freelance jobs

Revision ID: c4d2e6f8a1b3
Revises: b3c1d5e7f9a2
Create Date: 2026-10-16 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c4d2e6f8a1b3'
down_revision: Union[str, Sequence[str], None] = 'b3c1d5e7f9a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(length=30), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('budget', sa.String(length=100), nullable=False),
        sa.Column('skills', sa.JSON(), nullable=False),
        sa.Column('client', sa.JSON(), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('verdict', sa.String(length=10), nullable=False),
        sa.Column('reasons', sa.JSON(), nullable=False),
        sa.Column('concerns', sa.JSON(), nullable=False),
        sa.Column('scam_signs', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('paste_id', sa.Integer(), nullable=True),
        sa.Column('approval_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['approval_id'], ['approvals.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['paste_id'], ['pastes.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_jobs_status'), ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_jobs_status'))
    op.drop_table('jobs')
