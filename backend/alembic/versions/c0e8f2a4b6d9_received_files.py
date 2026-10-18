"""files you send (WhatsApp, chat), e.g. to save to your Drive

Revision ID: c0e8f2a4b6d9
Revises: b9d7e1f3a5c8
Create Date: 2026-10-18 21:40:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c0e8f2a4b6d9'
down_revision: Union[str, Sequence[str], None] = 'b9d7e1f3a5c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'received_files',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('filename', sa.String(length=200), nullable=False),
        sa.Column('mime', sa.String(length=120), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('stored_as', sa.String(length=80), nullable=False),
        sa.Column('drive_link', sa.String(length=300), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('received_files')
