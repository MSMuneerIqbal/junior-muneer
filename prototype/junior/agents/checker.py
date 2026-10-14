"""Quality Checker: scores a draft and lists exactly what to fix. Rule-based checks run first and are passed in as hints."""

from dataclasses import dataclass

from ..llm import ask
from ..style import lint, over_limit
from .common import Brief, Review, about_owner, task_block

SYSTEM = """You are the Quality Checker on {name}'s social media team. You review every post before {name} sees it. Be strict but fair: a post passes only if {name} could publish it as-is.

{about}

What you check:
1. Facts: every claim about {name} (projects, clients, numbers, results, tools) must be backed by the profile or the notes. List anything else under invented_facts.
2. Voice: simple English that a non-native reader understands, sounding like a real person, not AI or marketing copy. It follows the voice rules.
3. Platform fit: length, format and hashtags follow the platform rules.
4. Value: one clear point that is useful or interesting to {name}'s audience.
5. Topic: it covers what was asked."""


@dataclass
class CheckResult:
    score: int
    passes: bool
    issues: list[str]


def review(brief: Brief, text: str) -> CheckResult:
    auto = lint(text, brief.platform)
    hints = "\n".join(f"- {a}" for a in auto) or "- nothing"
    prompt = (
        f"{task_block(brief)}\n\n"
        f"Post to review:\n<post>\n{text}\n</post>\n\n"
        f"Automatic checks flagged:\n{hints}\n"
        "Include the flags you agree with in your issues; ignore any that are wrong in this context."
    )
    result = ask("checker", SYSTEM.format(name=brief.profile.name, about=about_owner(brief.profile)), prompt, Review)

    issues = [f"Not backed by your profile: {fact}" for fact in result.invented_facts] + result.issues
    too_long = over_limit(text, brief.platform)
    if too_long and too_long not in issues:
        issues.append(too_long)
    passes = result.passes and result.score >= 8 and not result.invented_facts and not too_long
    return CheckResult(score=max(1, min(10, result.score)), passes=passes, issues=issues)
