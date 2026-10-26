"""Reserve emailed story identities across restarts; do not recycle old digests after upgrade."""
from alembic import op
import sqlalchemy as sa
import hashlib
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

revision = "fa2c4e6a8b0d"
down_revision = "f8d0e2a4b6c9"
branch_labels = depends_on = None


def upgrade():
    op.create_table("news_deliveries",
        sa.Column("channel", sa.String(20), primary_key=True), sa.Column("topic", sa.String(20), primary_key=True),
        sa.Column("story_key", sa.String(64), primary_key=True), sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("digest_id", sa.Integer(), sa.ForeignKey("news_digests.id", ondelete="SET NULL")),
        sa.Column("state", sa.String(20), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_news_deliveries_batch_id", "news_deliveries", ["batch_id"])
    db = op.get_bind()
    marker = db.execute(sa.text("SELECT value,updated_at FROM settings WHERE key='news_emailed_on'")).first()
    if not marker or not json.loads(marker[0]):
        return
    for number, raw in db.execute(sa.text("SELECT id,data FROM news_digests WHERE topic='ai' AND built_at <= :sent"), {"sent": marker[1]}):
        data = json.loads(raw)
        for section in data.get("sections", []):
            for item in section.get("items", []):
                for source in item.get("sources", []):
                    values = []
                    if source.get("url"):
                        p = urlsplit(source["url"])
                        host = (p.hostname or "").lower().removeprefix("www.")
                        url = urlunsplit((p.scheme.lower(), host, p.path.rstrip("/") or "/", urlencode([(k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith("utm_")]), p.fragment if host == "trends.google.com" else ""))
                        values.append("url:" + url)
                    title = re.sub(r"\W+", " ", source.get("title", "").casefold()).strip()
                    if title:
                        values.append("title:" + title)
                    for value in values:
                        db.execute(sa.text("INSERT OR IGNORE INTO news_deliveries(channel,topic,story_key,batch_id,digest_id,state,created_at) VALUES ('email','ai',:key,'legacy',:id,'sent',:at)"),
                                   {"key": hashlib.sha256(value.encode()).hexdigest(), "id": number, "at": marker[1]})


def downgrade():
    op.drop_table("news_deliveries")
