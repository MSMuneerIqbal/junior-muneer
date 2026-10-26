"""Claim before SMTP; uncertain delivery is never automatically sent again."""
import uuid
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from junior.db import session_scope
from junior.db.models import NewsDelivery
from junior.news.freshness import story_keys
from junior.news.guard import top_stories


def claim(digest):
    batch = uuid.uuid4().hex
    try:
        with session_scope() as s:
            seen = set(s.scalars(select(NewsDelivery.story_key).where(NewsDelivery.channel == "email", NewsDelivery.topic == "ai")))
            selected = []
            for item in top_stories(digest["sections"], n=100):
                keys = story_keys(item)
                if not keys or keys & seen:
                    continue
                selected.append(item); seen.update(keys)
                for key in keys:
                    s.add(NewsDelivery(channel="email", topic="ai", story_key=key, batch_id=batch, digest_id=digest.get("id"), state="sending"))
                if len(selected) == 5:
                    break
        return batch, selected
    except IntegrityError:
        return batch, []  # another request reserved these stories first


def finish(batch, state):
    with session_scope() as s:
        s.execute(update(NewsDelivery).where(NewsDelivery.batch_id == batch).values(state=state))
