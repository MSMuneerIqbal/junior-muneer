"""WhatsApp messages kept until answered (survive restarts, no double answers)

Revision ID: e2a4c6e8f0b1
Revises: d1f9a3b5c7e0
Create Date: 2026-10-20 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e2a4c6e8f0b1'
down_revision: Union[str, Sequence[str], None] = 'd1f9a3b5c7e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'whatsapp_inbound',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('wa_message_id', sa.String(length=200), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('wa_message_id'),
    )
    with op.batch_alter_table('whatsapp_inbound', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_whatsapp_inbound_status'), ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('whatsapp_inbound', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_whatsapp_inbound_status'))
    op.drop_table('whatsapp_inbound')
