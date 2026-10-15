"""images on drafts

Revision ID: e3f7b2c8d4a5
Revises: d9e4a1b7c3f2
Create Date: 2026-10-15 17:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e3f7b2c8d4a5'
down_revision: Union[str, Sequence[str], None] = 'd9e4a1b7c3f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'images',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('approval_id', sa.Integer(), nullable=True),
        sa.Column('file', sa.String(length=100), nullable=False),
        sa.Column('original_name', sa.String(length=200), nullable=False),
        sa.Column('content_type', sa.String(length=50), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['approval_id'], ['approvals.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('images', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_images_approval_id'), ['approval_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('images', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_images_approval_id'))
    op.drop_table('images')
