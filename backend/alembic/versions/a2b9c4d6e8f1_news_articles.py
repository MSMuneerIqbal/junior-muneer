"""news articles

Revision ID: a2b9c4d6e8f1
Revises: f1a8c3d5e9b2
Create Date: 2026-10-15 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a2b9c4d6e8f1'
down_revision: Union[str, Sequence[str], None] = 'f1a8c3d5e9b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'news_articles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('topic', sa.String(length=20), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('url', sa.String(length=1000), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('extra', sa.JSON(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url'),
    )
    with op.batch_alter_table('news_articles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_news_articles_published_at'), ['published_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_news_articles_topic'), ['topic'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('news_articles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_news_articles_topic'))
        batch_op.drop_index(batch_op.f('ix_news_articles_published_at'))
    op.drop_table('news_articles')
