"""Google Search discovers candidates; only fetched official pages with publication metadata become news."""
import asyncio
from datetime import timedelta
from urllib.parse import urljoin, urlsplit

import httpx

from junior.config import get_settings
from junior.news.reader import Article, ReadError, WINDOW_DAYS, USER_AGENT, article_details, download, normalize_url, _Meta, parse_date
from junior.news.sources import Source, official_sites
from junior.websearch import gemini_search, SearchError


async def discover_news(topic, context, now, sources, *, transport=None):
    if get_settings().fake_ai:
        return [], None
    if not get_settings().gemini_api_key:
        return [], "Google Search is not configured; only official feeds were checked."
    start = now - timedelta(days=WINDOW_DAYS)
    sites = official_sites(topic)
    prefer = " OR ".join("site:" + site for site in sites[:6])
    query = (f"Latest {'AI model releases agents tools announcements' if topic == 'ai' else 'Pakistan national technology economy news'} "
             f"after:{start.date().isoformat()} before:{(now + timedelta(days=1)).date().isoformat()}. "
             f"({prefer}). Original publication dates only; exclude older stories and updated old pages.")
    context.research_sources.clear()
    try:
        await gemini_search(query, context)
    except SearchError as e:
        return [], f"{e}; official feeds were still checked."
    urls = list(context.research_sources)[:12]
    if not urls:
        return [], "Google Search returned no grounded article links; search text was not used as news."
    allowed = Source("Official Google Search result", topic, "page", "https://" + sites[0], domains=tuple(sites))
    semaphore = asyncio.Semaphore(4)

    async with httpx.AsyncClient(timeout=12, follow_redirects=False, headers={"User-Agent": USER_AGENT}, transport=transport) as client:
        async def one(url):
            async with semaphore:
                try:
                    # Google's grounding URLs are redirects. No arbitrary third-party redirect is fetched.
                    for _ in range(4):
                        if allowed.allows(url):
                            break
                        parsed = urlsplit(url)
                        if parsed.scheme != "https" or parsed.hostname != "vertexaisearch.cloud.google.com" or not parsed.path.startswith("/grounding-api-redirect/") or parsed.username or parsed.password:
                            return None
                        response = await client.get(url)
                        if not response.is_redirect:
                            return None
                        url = urljoin(url, response.headers.get("location", ""))
                    if not allowed.allows(url):
                        return None
                    source = next((s for s in sources if s.topic == topic and s.allows(url)), allowed)
                    final, body = await download(client, url, source)
                    text = body.decode("utf-8", errors="replace")
                    meta = _Meta(); meta.feed(text)
                    # A date in arbitrary page text, a footer, or dateModified is not publication evidence.
                    import re
                    ld = re.search(r'"datePublished"\s*:\s*"([^"]+)"', " ".join(meta.ld_json))
                    published = parse_date(meta.meta.get("article:published_time") or meta.meta.get("datepublished") or (ld.group(1) if ld else ""))
                    if published is None or not start <= published <= now:
                        return None
                    title, _, summary = article_details(text, "", source)
                    if not title:
                        return None
                    return Article(source.name if source is not allowed else urlsplit(final).hostname, topic, title, final, published, summary)
                except (httpx.HTTPError, ReadError, ValueError, TimeoutError):
                    return None
        found = await asyncio.gather(*(asyncio.wait_for(one(url), 25) for url in urls), return_exceptions=True)
    unique = {normalize_url(a.url): a for a in found if isinstance(a, Article)}
    return list(unique.values()), None
