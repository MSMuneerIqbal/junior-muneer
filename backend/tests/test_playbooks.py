import pytest
from fastapi.testclient import TestClient

from junior.main import create_app
from junior.playbooks import REQUIRED, PlaybookError, load_playbooks, parse_playbook

GOOD = """---
platform: linkedin
label: LinkedIn
max_chars: 300
words: [5, 30]
hashtags: [1, 3]
links: avoid
---
## Structure
Hook first.
## Tone
Friendly.
## Hashtags
A few.
## Red lines
Nothing invented.
"""


def test_real_playbooks_load_and_cover_every_platform():
    books = load_playbooks()
    assert set(REQUIRED) <= set(books)
    assert books["x"].max_chars == 280
    assert books["instagram"].needs_image is True
    assert "Red lines" in books["linkedin"].text


def test_parses_a_good_playbook():
    book = parse_playbook(GOOD, "linkedin.md")
    assert book.label == "LinkedIn"
    assert book.words == (5, 30) and book.hashtags == (1, 3)
    assert book.links == "avoid" and book.needs_image is False


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("no header", "must start with a header"),
        (GOOD.replace("platform: linkedin", "platform: facebook"), "must match"),
        (GOOD.replace("label: LinkedIn\n", ""), "missing header field(s) ['label']"),
        (GOOD.replace("max_chars: 300", "max_chars: lots"), "'max_chars' must be"),
        (GOOD.replace("words: [5, 30]", "words: [30, 5]"), "'words' must be [min, max]"),
        (GOOD.replace("links: avoid", "links: never"), "'links' must be ok or avoid"),
        (GOOD.replace("links: avoid", "colour: blue"), "unknown header field(s) ['colour']"),
        (GOOD.replace("## Red lines", "## Other"), "missing section(s) ['Red lines']"),
        (GOOD.replace("label: LinkedIn", "label: [oops"), "not valid YAML"),
    ],
)
def test_broken_playbook_gives_a_clear_error(text, message):
    with pytest.raises(PlaybookError) as e:
        parse_playbook(text, "linkedin.md")
    assert "playbooks/linkedin.md" in str(e.value)
    assert message in str(e.value)


def test_a_missing_platform_stops_loading(tmp_path):
    (tmp_path / "linkedin.md").write_text(GOOD, encoding="utf-8")
    with pytest.raises(PlaybookError, match="missing for"):
        load_playbooks(tmp_path)


def test_check_finds_hard_limit_problems():
    book = parse_playbook(GOOD, "linkedin.md")
    good = "I built an agent that books calls for a clinic. It saved the team hours. #AI"
    assert book.check(good) == []
    problems = book.check("Too short. https://example.com")
    assert any("Short for LinkedIn" in p for p in problems)
    assert any("0 hashtags" in p for p in problems)
    assert any("put the link in a comment" in p for p in problems)
    assert any("Too long" in p for p in book.check("word " * 100))


def test_api_lists_playbooks():
    with TestClient(create_app(model_provider=lambda: (lambda n: None))) as client:
        books = {b["platform"]: b for b in client.get("/api/playbooks").json()}
    assert set(REQUIRED) <= set(books)
    assert books["x"]["max_chars"] == 280 and "## Structure" in books["x"]["text"]
