"""P2b-01b: the fact guard. Code, not AI, decides what reaches you."""

from datetime import UTC, datetime

from junior.news.guard import DigestIn, guard_digest, keep_official_links, strip_links
from junior.news.reader import Article

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
ARTICLES = {
    1: Article("OpenAI", "ai", "Introducing GPT-7", "https://openai.com/index/introducing-gpt-7/",
               datetime(2026, 10, 14, 17, 0, tzinfo=UTC), "GPT-7 scores 91.2% on SWE-bench Verified."),
    2: Article("OpenAI", "ai", "Codex for teams", "https://openai.com/index/codex-for-teams/",
               datetime(2026, 10, 12, 8, 30, tzinfo=UTC), "Codex now works for whole teams."),
    3: Article("OpenAI", "ai", "An older story", "https://openai.com/index/old/",
               datetime(2026, 9, 20, tzinfo=UTC), "From last month."),
    4: Article("Google DeepMind", "ai", "Gemini 4 Ultra", "https://deepmind.google/blog/gemini-4-ultra/",
               datetime(2026, 10, 13, 9, 0, tzinfo=UTC), "Gemini 4 Ultra leads on reasoning."),
}


def item(ids, headline, summary=""):
    return {"article_ids": ids, "headline": headline, "summary": summary}


def run(sections, topic="ai", articles=ARTICLES):
    return guard_digest(DigestIn.model_validate({"sections": sections}), articles, topic, NOW)


def section(out, key):
    return next(s for s in out["sections"] if s["key"] == key)


def reasons(out):
    return {r["headline"]: r["reason"] for r in out["removed"]}


def test_a_real_item_gets_its_link_and_date_from_the_article():
    out = run([{"key": "models", "items": [item([1], "OpenAI releases GPT-7", "OpenAI says GPT-7 scores 91.2% on SWE-bench Verified.")]}])
    [kept] = section(out, "models")["items"]
    assert kept["sources"] == [
        {"name": "OpenAI", "title": "Introducing GPT-7", "url": "https://openai.com/index/introducing-gpt-7/", "date": "2026-10-14T17:00:00+00:00"}
    ]
    assert kept["date"] == "2026-10-14T17:00:00+00:00"
    assert out["removed"] == []
    # Every section is there, in order, even when empty.
    assert [s["title"] for s in out["sections"]] == [
        "New models and releases", "Benchmarks and who's on top", "Agents and tools", "Business moves"
    ]


def test_an_invented_item_is_removed():
    out = run([{"key": "models", "items": [item([99], "xAI releases Grok 9", "A model nobody read about.")]}])
    assert section(out, "models")["items"] == []
    assert reasons(out) == {"xAI releases Grok 9": "not based on an article that was read"}
    out = run([{"key": "models", "items": [item([], "No sources at all")]}])
    assert reasons(out) == {"No sources at all": "not based on an article that was read"}


def test_the_ai_cant_change_or_add_a_link():
    out = run([{"key": "agents", "items": [item([2], "Codex for teams", "Codex now works for teams. Details: https://evil.example/codex and [here](https://evil.example/x).")]}])
    [kept] = section(out, "agents")["items"]
    assert "evil.example" not in kept["summary"] and kept["summary"].startswith("Codex now works for teams")
    assert kept["sources"][0]["url"] == "https://openai.com/index/codex-for-teams/"  # the real one
    assert kept["links_removed"] == 2


def test_an_old_story_is_removed():
    out = run([{"key": "models", "items": [item([3], "An older story"), item([1, 3], "GPT-7 and an old story")]}])
    assert reasons(out) == {
        "An older story": "uses a story older than 15 days",
        "GPT-7 and an old story": "uses a story older than 15 days",
    }


def test_numbers_must_come_from_the_sources():
    out = run([{"key": "benchmarks", "items": [
        item([1], "GPT-7 on SWE-bench", "OpenAI says GPT-7 scores 99.9% on SWE-bench Verified."),
        item([1], "GPT-7 on SWE-bench", "OpenAI says GPT-7 scores 91.2% on SWE-bench Verified, released Oct 14, 2026."),
    ]}])
    assert reasons(out) == {"GPT-7 on SWE-bench": "has a number its sources don't have (99.9)"}
    [kept] = section(out, "benchmarks")["items"]
    assert "91.2%" in kept["summary"]  # real number, and the article's own date numbers are fine


def test_unknown_sections_and_full_sections():
    out = run([{"key": "gossip", "items": [item([1], "Rumour")]}])
    assert reasons(out) == {"Rumour": "unknown section 'gossip'"}
    many = [item([4], f"Gemini item {chr(65 + n)}") for n in range(10)]
    out = run([{"key": "models", "items": many}])
    assert len(section(out, "models")["items"]) == 8
    assert sum(r["reason"] == "section full" for r in out["removed"]) == 2


def test_pakistan_sections():
    pk = {7: Article("Dawn", "pakistan", "Petrol price cut by Rs5", "https://www.dawn.com/news/1",
                     datetime(2026, 10, 15, 6, 0, tzinfo=UTC), "The government cut petrol by Rs5 a litre.")}
    out = run([{"key": "economy", "items": [item([7], "Petrol cheaper by Rs5", "Dawn reports a Rs5 cut a litre.")]}], "pakistan", pk)
    assert [s["key"] for s in out["sections"]] == ["top", "trending", "tech", "economy"]
    assert section(out, "economy")["items"][0]["sources"][0]["url"] == "https://www.dawn.com/news/1"


def test_answers_keep_only_official_links():
    sites = ["openai.com", "deepmind.google"]
    text = (
        "GPT-7 is out ([OpenAI](https://openai.com/index/introducing-gpt-7/)). "
        "Some blog says more ([rumour](https://evil.example/gpt7)). "
        "See https://deepmind.google/blog/gemini-4-ultra/ and https://evil.example/fake."
    )
    out, removed = keep_official_links(text, sites)
    assert "[OpenAI](https://openai.com/index/introducing-gpt-7/)" in out
    assert "https://deepmind.google/blog/gemini-4-ultra/" in out
    assert "evil.example" not in out and "rumour" in out
    assert removed == 2
    # Look-alike sites are not official.
    out, removed = keep_official_links("[x](https://openai.com.evil.example/a)", sites)
    assert out == "x" and removed == 1


def test_strip_links():
    assert strip_links("See https://evil.example/a now") == ("See now", 1)
