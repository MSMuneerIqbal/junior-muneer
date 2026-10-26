"""Sample news for FAKE_AI mode: no network, no cost.

Small feeds for a few of the real sources, dated relative to now (so they're always inside the
three days); every other source answers with an empty feed. The real reader, fact guard and
digest code run on them.
"""

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx

EMPTY = b'<?xml version="1.0"?><rss version="2.0"><channel><title>empty</title></channel></rss>'


def _rss(items: list[tuple[str, str, str, timedelta]]) -> bytes:
    now = datetime.now(UTC)
    body = "".join(
        f"<item><title>{title}</title><link>{link}</link><description>{text}</description>"
        f"<pubDate>{format_datetime(now - ago)}</pubDate></item>"
        for title, link, text, ago in items
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>sample</title>{body}</channel></rss>'.encode()


def _trends() -> bytes:
    now = datetime.now(UTC)
    return (
        '<?xml version="1.0"?><rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>'
        f"<item><title>babar azam</title><ht:approx_traffic>50K+</ht:approx_traffic>"
        f"<pubDate>{format_datetime(now - timedelta(hours=3))}</pubDate>"
        "<ht:news_item><ht:news_item_title>Babar Azam named captain for the T20 series</ht:news_item_title>"
        "<ht:news_item_source>Dawn</ht:news_item_source></ht:news_item></item>"
        "</channel></rss>"
    ).encode()


def _routes() -> dict[str, bytes]:
    h, d = timedelta(hours=1), timedelta(days=1)
    return {
        "https://openai.com/news/rss.xml": _rss(
            [
                ("Introducing GPT-7 (sample)", "https://openai.com/index/sample-gpt-7/", "A sample model release.", 5 * h),
                ("Codex for teams (sample)", "https://openai.com/index/sample-codex-teams/", "A sample tools update.", d),
            ]
        ),
        "https://deepmind.google/blog/rss.xml": _rss(
            [("Gemini 4 Ultra (sample)", "https://deepmind.google/blog/sample-gemini/", "A sample Gemini post.", 2 * d)]
        ),
        "https://www.dawn.com/feeds/pakistan": _rss(
            [
                ("Petrol price cut (sample)", "https://www.dawn.com/news/sample-petrol", "A sample economy story.", 4 * h),
                ("Broadband users grow (sample)", "https://www.dawn.com/news/sample-broadband", "A sample tech story.", 2 * d),
            ]
        ),
        "https://trends.google.com/trending/rss?geo=PK": _trends(),
    }


def sample_transport() -> httpx.MockTransport:
    routes = _routes()
    return httpx.MockTransport(lambda request: httpx.Response(200, content=routes.get(str(request.url), EMPTY)))
