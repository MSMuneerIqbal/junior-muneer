"""pastes

Revision ID: c5d2e8f3a7b1
Revises: b81f4c2d9a10
Create Date: 2026-10-15 14:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c5d2e8f3a7b1'
down_revision: Union[str, Sequence[str], None] = 'b81f4c2d9a10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pastes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(length=30), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('source_url', sa.String(length=500), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('pastes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pastes_message_id'), ['message_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pastes_platform'), ['platform'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('pastes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pastes_platform'))
        batch_op.drop_index(batch_op.f('ix_pastes_message_id'))
    op.drop_table('pastes')
