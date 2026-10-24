"""Only search-provider evidence may enter the citation catalog; drafts cannot invent URLs."""
from urllib.parse import urlsplit


def remember_source(context, url: str, title: str = "") -> None:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            return
    except (ValueError, TypeError):
        return
    if len(context.research_sources) < 40 and len(url) <= 2000:
        context.research_sources[url] = (title or parsed.hostname)[:200]


def collect_response_sources(context, output) -> None:
    def get(obj, key, default=None):
        return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)
    for item in output:
        if get(item, "type") == "web_search_call":
            for source in get(get(item, "action"), "sources", []) or []:
                remember_source(context, get(source, "url", ""), get(source, "title", ""))
        for part in get(item, "content", []) or []:
            for annotation in get(part, "annotations", []) or []:
                if get(annotation, "type") == "url_citation":
                    remember_source(context, get(annotation, "url", ""), get(annotation, "title", ""))
