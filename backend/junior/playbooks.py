"""Platform playbooks: one expert file per platform in playbooks/.

A playbook is Markdown with a YAML header. The header holds the hard limits that
code checks; the text holds the advice the writing team reads.

    ---
    platform: linkedin        # must match the file name
    label: LinkedIn
    max_chars: 3000           # the platform's own limit
    words: [120, 250]         # a good length
    hashtags: [3, 5]          # how many hashtags
    needs_image: false        # true: a draft waits for an image
    links: ok                 # ok · avoid (put links in a comment, not the post)
    ---
    ## Structure
    ## Tone
    ## Hashtags
    ## Red lines

    GET /api/playbooks   every playbook (header and text)
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from fastapi import APIRouter, Request

from junior.config import REPO_DIR

log = logging.getLogger(__name__)
router = APIRouter()

PLAYBOOKS_DIR = REPO_DIR / "playbooks"
# Phase 2 can't write for a platform without its playbook.
REQUIRED = ("linkedin", "facebook", "instagram", "x")
SECTIONS = ("Structure", "Tone", "Hashtags", "Red lines")
NOT_PLAYBOOK_FILES = {"README.md"}

_HEADER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
_FIELDS = {"platform", "label", "max_chars", "words", "hashtags", "needs_image", "links"}
_HASHTAG = re.compile(r"(?<!\w)#\w+")


class PlaybookError(Exception):
    """A playbook is broken. The message names the file and the problem."""


@dataclass(frozen=True)
class Playbook:
    platform: str
    label: str
    text: str
    max_chars: int
    words: tuple[int, int]
    hashtags: tuple[int, int]
    needs_image: bool = False
    links: str = "ok"
    path: Path | None = field(default=None, compare=False)

    def check(self, draft: str) -> list[str]:
        """Hard-limit problems with a draft, in plain words. Empty when it fits."""
        problems = []
        if len(draft) > self.max_chars:
            problems.append(f"Too long for {self.label}: {len(draft)} characters, the limit is {self.max_chars}.")
        words = len(_HASHTAG.sub("", draft).split())
        low, high = self.words
        if words < low:
            problems.append(f"Short for {self.label}: {words} words, aim for {low} to {high}.")
        elif words > high:
            problems.append(f"Long for {self.label}: {words} words, aim for {low} to {high}.")
        tags = len(_HASHTAG.findall(draft))
        low, high = self.hashtags
        if not low <= tags <= high:
            problems.append(f"{tags} hashtags; {self.label} posts should have {low} to {high}.")
        if self.links == "avoid" and re.search(r"https?://", draft):
            problems.append(f"Links in a {self.label} post get less reach: put the link in a comment.")
        return problems


def _pair(value, key: str, fail) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in value)
        or value[0] > value[1]
    ):
        raise fail(f"'{key}' must be [min, max] with whole numbers, e.g. {key}: [3, 5].")
    return value[0], value[1]


def parse_playbook(text: str, filename: str) -> Playbook:
    def fail(msg: str) -> PlaybookError:
        return PlaybookError(f"playbooks/{filename}: {msg}")

    match = _HEADER.match(text.replace("\r\n", "\n"))
    if not match:
        raise fail("must start with a header between two '---' lines.")
    try:
        header = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as e:
        raise fail(f"the header is not valid YAML: {e}") from None
    if not isinstance(header, dict):
        raise fail("the header must be 'key: value' lines.")

    unknown = set(header) - _FIELDS
    if unknown:
        raise fail(f"unknown header field(s) {sorted(unknown)}; allowed: {sorted(_FIELDS)}.")
    missing = sorted({"platform", "label", "max_chars", "words", "hashtags"} - set(header))
    if missing:
        raise fail(f"missing header field(s) {missing}.")

    platform = header["platform"]
    if platform != Path(filename).stem:
        raise fail(f"'platform' is {platform!r} but the file is called {filename}; they must match.")
    label = header["label"]
    if not isinstance(label, str) or not label.strip():
        raise fail("'label' must be the platform's name, e.g. LinkedIn.")
    max_chars = header["max_chars"]
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars <= 0:
        raise fail("'max_chars' must be a whole number above 0.")
    needs_image = header.get("needs_image", False)
    if not isinstance(needs_image, bool):
        raise fail("'needs_image' must be true or false.")
    links = header.get("links", "ok")
    if links not in ("ok", "avoid"):
        raise fail("'links' must be ok or avoid.")

    body = match.group(2).strip()
    headings = {h.strip().lower() for h in re.findall(r"^##\s+(.+)$", body, re.MULTILINE)}
    absent = [s for s in SECTIONS if s.lower() not in headings]
    if absent:
        raise fail(f"missing section(s) {absent}; each playbook needs ## {', ## '.join(SECTIONS)}.")

    return Playbook(
        platform=platform,
        label=label.strip(),
        text=body,
        max_chars=max_chars,
        words=_pair(header["words"], "words", fail),
        hashtags=_pair(header["hashtags"], "hashtags", fail),
        needs_image=needs_image,
        links=links,
    )


def load_playbooks(directory: Path = PLAYBOOKS_DIR) -> dict[str, Playbook]:
    """Load every playbook. A broken or missing one stops startup with a clear error."""
    books: dict[str, Playbook] = {}
    for path in sorted(directory.glob("*.md")):
        if path.name in NOT_PLAYBOOK_FILES:
            continue
        book = parse_playbook(path.read_text(encoding="utf-8"), path.name)
        books[book.platform] = Playbook(**{**book.__dict__, "path": path})
    missing = [p for p in REQUIRED if p not in books]
    if missing:
        raise PlaybookError(f"playbooks missing for {missing} (looked in {directory}).")
    log.info("Playbooks loaded: %s", ", ".join(sorted(books)))
    return books


@router.get("/api/playbooks")
def get_playbooks(request: Request) -> list[dict]:
    return [
        {
            "platform": b.platform,
            "label": b.label,
            "max_chars": b.max_chars,
            "words": list(b.words),
            "hashtags": list(b.hashtags),
            "needs_image": b.needs_image,
            "links": b.links,
            "text": b.text,
        }
        for b in request.app.state.playbooks.values()
    ]
