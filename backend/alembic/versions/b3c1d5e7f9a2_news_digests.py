"""news digests

Revision ID: b3c1d5e7f9a2
Revises: a2b9c4d6e8f1
Create Date: 2026-10-15 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b3c1d5e7f9a2'
down_revision: Union[str, Sequence[str], None] = 'a2b9c4d6e8f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'news_digests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('topic', sa.String(length=20), nullable=False),
        sa.Column('built_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('cost_usd', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('news_digests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_news_digests_built_at'), ['built_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_news_digests_topic'), ['topic'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('news_digests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_news_digests_topic'))
        batch_op.drop_index(batch_op.f('ix_news_digests_built_at'))
    op.drop_table('news_digests')
