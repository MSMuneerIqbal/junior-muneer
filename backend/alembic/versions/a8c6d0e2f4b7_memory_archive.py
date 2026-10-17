"""memories can be archived (tidy-up)

Revision ID: a8c6d0e2f4b7
Revises: f7a5b9c1d4e6
Create Date: 2026-10-17 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a8c6d0e2f4b7'
down_revision: Union[str, Sequence[str], None] = 'f7a5b9c1d4e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('memories', schema=None) as batch_op:
        batch_op.add_column(sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('archive_reason', sa.String(length=300), nullable=False, server_default=''))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('memories', schema=None) as batch_op:
        batch_op.drop_column('archive_reason')
        batch_op.drop_column('archived_at')
