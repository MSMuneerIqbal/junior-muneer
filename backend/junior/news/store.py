"""Articles that were really read: the fact guard checks digest items against these."""

from datetime import timedelta

from sqlalchemy import delete, select

from junior.db import NewsArticle, session_scope
from junior.db.models import utcnow
from junior.news.reader import Article

KEEP_DAYS = 30


def save_articles(articles: list[Article]) -> dict[str, int]:
    """Save (or refresh) articles; returns url -> id. Articles older than 30 days are removed."""
    ids: dict[str, int] = {}
    with session_scope() as s:
        s.execute(delete(NewsArticle).where(NewsArticle.published_at < utcnow() - timedelta(days=KEEP_DAYS)))
        existing = {
            a.url: a
            for a in s.scalars(select(NewsArticle).where(NewsArticle.url.in_([x.url for x in articles])))
        }
        for a in articles:
            row = existing.get(a.url)
            if row is None:
                row = NewsArticle(url=a.url)
                s.add(row)
                existing[a.url] = row
            row.topic, row.source, row.title = a.topic, a.source, a.title[:300]
            row.published_at, row.summary, row.extra = a.published, a.summary, a.extra
            row.fetched_at = utcnow()
        s.flush()
        for a in articles:
            ids[a.url] = existing[a.url].id
    return ids
