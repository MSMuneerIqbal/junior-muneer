"""Zero-model skill/memory commands. A command is only authority when it is the user's own message."""

from sqlalchemy import select

from junior.agent.runner import TurnResult
from junior.audit import audit
from junior.db import Memory, session_scope
from junior import skills
from junior.privacy import credential_present

COMMANDS = {"/learn", "/skills", "/reload-skills", "/memory", "/update"}


def handle(context, text, paste=None):
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return None
    command = parts[0].casefold()
    argument = parts[1] if len(parts) > 1 else ""
    if command not in COMMANDS:
        return None
    if paste is not None:
        reply = "Send this command in your own message without pasted outside text. Nothing was changed."
    else:
        argument = argument.strip()
        try:
            if command == "/update":
                from junior.maintenance.updates import check, propose, review_text, status
                from junior.maintenance.source import MaintenanceError
                try:
                    if argument == "--check":
                        review = check()
                        reply = review_text(review)
                        reply += "\n\n" + ("Local edits block application. " if review["dirty"] else "")
                        reply += "Use /update --apply to prepare an approval card for this exact revision."
                    elif argument == "--apply":
                        from junior.maintenance.updates import folder, read_json
                        review = read_json(folder() / "review.json", {})
                        item = propose(review.get("id"), context.conversation_id)
                        context.approval_ids.append(item.id)
                        context.emit({"type": "approval", "item": item.model_dump(mode="json")})
                        reply = "Update card prepared. Nothing installs until you approve it."
                    elif argument == "--status":
                        state = status()
                        reply = str((state.get("progress") or {}).get("step") or "No update has run.")
                    else:
                        reply = "Use /update --check, /update --apply (review card), or /update --status. No model calls."
                except MaintenanceError as error:
                    reply = str(error)
            elif command == "/learn":
                parts = [part.strip() for part in argument.split("|", 2)]
                if len(parts) != 3:
                    reply = "Use /learn name | when to use it | workflow steps (at least 40 characters). I'll prepare a skill card for your review; it is saved only after approval."
                else:
                    from junior.skill_learning import propose
                    reply = propose(context, *parts, text)
            elif command == "/skills":
                found = [skill for skill in skills.load_skills().values()
                         if argument.casefold() in f"{skill.name} {skill.description}".casefold()]
                reply = "Your skills (edit resources and versions in Settings → Skills):\n\n" + (
                    "\n".join(f"- **{skill.name}** — {skill.description}" for skill in found[:30]) or "No matching skills.")
                if len(found) > 30:
                    reply += f"\n\nShowing 30 of {len(found)}. Add a search word after /skills."
            elif command == "/reload-skills":
                if argument:
                    reply = "Use /reload-skills without arguments."
                else:
                    found = skills.load_skills()
                    reply = f"Validated {len(found)} skills. Current files are loaded when a matching task needs them. No model calls."
            else:
                with session_scope() as session:
                    query = select(Memory).where(Memory.archived_at.is_(None)).order_by(Memory.id.desc()).limit(20)
                    if argument:
                        query = query.where(Memory.content.ilike(f"%{argument[:120]}%"))
                    facts = [memory.content for memory in session.scalars(query) if not credential_present(memory.content)]
                reply = "Your saved personal memory (up to 20 facts; edit or delete on the Memory page):\n\n" + (
                    "\n".join(f"- {fact}" for fact in facts) or "No matching saved facts.")
        except (skills.SkillError, OSError):
            reply = "Could not load the current skill library. Check its files/Settings; nothing was changed."
    audit("tool_call", "local_command", detail={"command": command}, conversation_id=context.conversation_id)
    return TurnResult(text=reply, usage=[], steps=[])
