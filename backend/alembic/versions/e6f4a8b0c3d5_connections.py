"""connected accounts

Revision ID: e6f4a8b0c3d5
Revises: d5e3f7a9b2c4
Create Date: 2026-10-17 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e6f4a8b0c3d5'
down_revision: Union[str, Sequence[str], None] = 'd5e3f7a9b2c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'connections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=30), nullable=False),
        sa.Column('account', sa.String(length=100), nullable=False),
        sa.Column('token_enc', sa.Text(), nullable=False),
        sa.Column('scopes', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('connections')
