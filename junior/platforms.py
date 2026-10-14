"""Rules for each social network. The writer, checker and humanizer all follow these."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Platform:
    key: str
    name: str
    max_chars: int
    max_hashtags: int
    length_hint: str
    style: str
    open_url: str
    # When set, the post text is appended (URL-encoded) to prefill the platform's composer.
    share_url: str = ""


PLATFORMS: dict[str, Platform] = {
    p.key: p
    for p in [
        Platform(
            key="linkedin",
            name="LinkedIn",
            max_chars=3000,
            max_hashtags=3,
            length_hint="80 to 200 words",
            style=(
                "Professional but warm, like talking to a client. The first line shows before "
                "'see more', so make it plain and interesting. Short paragraphs of 1 or 2 lines "
                "with a blank line between them. Share a real lesson, result or story from your "
                "work. 0 to 3 hashtags, only at the very end."
            ),
            open_url="https://www.linkedin.com/feed/",
        ),
        Platform(
            key="facebook",
            name="Facebook",
            max_chars=5000,
            max_hashtags=2,
            length_hint="40 to 120 words",
            style=(
                "Casual and friendly, like talking to people who already know you. "
                "One clear point. 0 to 2 hashtags."
            ),
            open_url="https://www.facebook.com/",
        ),
        Platform(
            key="instagram",
            name="Instagram",
            max_chars=2200,
            max_hashtags=5,
            length_hint="40 to 120 words, then hashtags",
            style=(
                "A caption that goes with an image or carousel. The first line must make people "
                "stop scrolling. Use line breaks so it is easy to read on a phone. Up to 5 "
                "relevant hashtags at the end."
            ),
            open_url="https://www.instagram.com/",
        ),
        Platform(
            key="x",
            name="X (Twitter)",
            max_chars=280,
            max_hashtags=1,
            length_hint="under 260 characters",
            style="One clear thought. Plain and punchy. No thread. No hashtags, or 1 at most.",
            open_url="https://x.com/",
            share_url="https://twitter.com/intent/tweet?text=",
        ),
    ]
}


def enabled_platforms(keys: list[str] | None) -> list[Platform]:
    """Platforms listed in the profile, or all of them if the list is empty."""
    chosen = [PLATFORMS[k] for k in (keys or []) if k in PLATFORMS]
    return chosen or list(PLATFORMS.values())
