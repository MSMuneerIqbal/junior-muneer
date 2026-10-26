"""Learning is a reviewed configuration change, never permission escalation or executable training."""

import yaml

from junior.approvals import ApprovalError, create_item
from junior.audit import audit
from junior import gate, skills
from junior.permissions import plan_mode_refusal
from junior.senders.base import SendResult


def propose(context, name, description, instructions, your_words):
    if refusal := plan_mode_refusal():
        return refusal
    if context.outside_content_seen or context.memory_locked:
        return "NOT saved: this turn includes outside text or an unverified live transcript. Describe the workflow in your own new message."
    if not gate.you_said(context, your_words):
        return "NOT saved: copy their own words asking for this skill into your_words (word for word). Only when they ask."
    if context.skill_drafts >= 2:
        return "NOT saved: at most two skill drafts per message. Continue in a new message."
    try:
        skills.secret_free(name + description + instructions)
    except skills.SkillError as error:
        return f"NOT saved: {error}"
    name = (name or "").strip().lower().replace(" ", "_").replace("-", "_")
    try:
        path = skills._path(name, skills.SKILLS_DIR)
        if path.exists():
            return "NOT saved: that skill already exists. Edit it in Settings → Skills, where previous versions are available."
        header = {"name": name, "description": description, "for": ["junior_muneer"]}
        skills.parse_skill(f"---\n{yaml.safe_dump(header, sort_keys=False, allow_unicode=True)}---\n{instructions}\n", f"{name}.md")
        item = create_item(kind="api", platform="skills", item_type="skill", action_type="skills.learn",
                           text=instructions.strip(), title=f"Learn: {name.replace('_', ' ')}",
                           from_outside=False, conversation_id=context.conversation_id,
                           meta={"op": "learn_skill", "name": name, "description": description, "agents": ["junior_muneer"]})
    except (skills.SkillError, ApprovalError) as error:
        return f"NOT saved: {error}"
    context.skill_drafts += 1
    context.approval_ids.append(item.id)
    context.emit({"type": "approval", "item": item.model_dump(mode="json")})
    audit("action", "skill_proposed", detail={"skill": name}, conversation_id=context.conversation_id)
    return f"NOT saved yet: skill {name!r} is ready on card {item.id}, waiting for approval. You can edit its steps before approving."


class SkillSender:
    label = "Skills"
    action_types = ("skills.learn",)

    def is_connected(self):
        return True

    async def send(self, out):
        try:
            if out.action_type != "skills.learn" or out.meta.get("op") != "learn_skill":
                return SendResult("failed", "That is not a reviewed skill draft.")
            name = out.meta.get("name", "")
            skills._path(name, skills.SKILLS_DIR)
            path = skills.save_skill(name, out.meta.get("description", ""), out.text,
                                     agents=tuple(out.meta.get("agents", ["junior_muneer"])))
            audit("action", "skill_saved", detail={"skill": path.stem})
            return SendResult("sent", f"Saved skill {path.stem}. It is available in Settings → Skills and future matching tasks.")
        except (skills.SkillError, OSError):
            return SendResult("failed", "Couldn't save this reviewed skill. Check the name, content and current Skills list; nothing was overwritten.")
