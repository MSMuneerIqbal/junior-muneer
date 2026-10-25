"""Expose original uploads and documents in the folder gallery, without extracting their contents."""
from alembic import op
import sqlalchemy as sa

revision = "f8d0e2a4b6c9"
down_revision = "f6c8d0e2a4b7"
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table("received_files") as batch:
        batch.add_column(sa.Column("library_folder_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("library_archived", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch.create_foreign_key("fk_received_files_library_folder", "notes_folders", ["library_folder_id"], ["id"])
        batch.create_index("ix_received_files_library_folder_id", ["library_folder_id"])
    for name, condition in (("Uploads", "source IN ('chat','whatsapp','library')"), ("Documents", "source='generated'"),
                            ("Archives", "id IN (SELECT json_extract(meta,'$.snapshot_id') FROM approvals WHERE action_type='files.archive_whatsapp')")):
        op.execute(sa.text("INSERT OR IGNORE INTO notes_folders(name,name_key,created_at) SELECT :name,:key,CURRENT_TIMESTAMP WHERE EXISTS (SELECT 1 FROM received_files WHERE " + condition + ")").bindparams(name=name, key=name.casefold()))
    op.execute("""UPDATE received_files SET library_folder_id=(SELECT id FROM notes_folders WHERE name_key='uploads') WHERE source IN ('chat','whatsapp','library')""")
    op.execute("""UPDATE received_files SET library_folder_id=(SELECT id FROM notes_folders WHERE name_key='documents')
        WHERE source='generated' AND id NOT IN (SELECT json_extract(meta,'$.snapshot_id') FROM approvals WHERE json_extract(meta,'$.snapshot_id') IS NOT NULL)""")
    op.execute("""UPDATE received_files SET library_folder_id=(SELECT id FROM notes_folders WHERE name_key='archives')
        WHERE id IN (SELECT json_extract(meta,'$.snapshot_id') FROM approvals WHERE action_type='files.archive_whatsapp')""")


def downgrade():
    with op.batch_alter_table("received_files") as batch:
        batch.drop_index("ix_received_files_library_folder_id")
        batch.drop_constraint("fk_received_files_library_folder", type_="foreignkey")
        batch.drop_column("library_archived")
        batch.drop_column("library_folder_id")
