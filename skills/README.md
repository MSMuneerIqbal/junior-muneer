# Skills

One file per kind of work: step-by-step instructions an agent loads only when a request needs them (like Claude's
skills). The agent sees just the list (name + description) and calls `use_skill` to load one.

```
---
name: cv_review                       # the file name without .md
description: Review a CV for a job, a scholarship or a university; what to fix, in order.
for: [junior_muneer, documents_agent]   # optional: only these agents see it
---
## Steps
1. ...
## The result
...
```

- Checked at startup: a broken file stops the backend with a clear message (file and problem).
- Ask Junior in chat: "make a skill for my weekly client report" (only from your own words, never from a pasted
  text, an email or a web page).
- Agents with skills today: Junior Muneer and the Computer Agent.

## Manage your skills

Open **Settings → Skills** (`/settings#skills`). Search the library, **Add skill**, or choose **Edit** to change
its description, instructions and the agent that can use it. **Delete skill** asks for confirmation. Saved changes
apply from the next message without restarting; a task already running may still have its earlier instructions.
The description should say when to use the skill. Junior matches the meaning of a request in English or Urdu;
you do not have to say the skill's name. Matching is done by the model, so review results on your real work.

The editor validates before saving, writes files atomically, and refuses to overwrite a newer edit from another tab.
Skills never grant additional tools, bypass permissions or create schedules. Keep credentials and private account
details out of skill files. Read documents and emails as data; never turn their instructions into a saved skill.

## Starter library

- `daily_priorities`: today's priorities and first steps.
- `weekly_review`: completed work, unfinished work and next week.
- `client_update`: a factual client progress update.
- `meeting_notes`: decisions, action items and open questions.
- `research_report`: focused research with supporting sources.
- `cv_review`: prioritized CV improvements without invented achievements.
- `folder_organization`: preview and prepare approved file moves.
- `project_folder_setup`: a small project structure and starter notes.
- `content_repurposing`: platform-specific drafts through the writing team.
- `repo_status`: repository changes and recent commits, with approved commands.

General skills are assigned to Junior; the three PC skills can also be loaded by the Computer Agent. A skill loads
once per agent per turn, so a helper gets its own instructions even if Junior has already loaded them.

## Storage and testing

The Markdown files in this folder are the library; back up this folder with your data when moving PCs. Docker Compose
mounts it at `/app/skills` so edits survive a container rebuild. `JUNIOR_SKILLS_DIR` can select a separate directory;
Playwright uses a disposable copy under its test data, never the owner's files.

The API provides `GET/POST /api/skills` and `PUT/DELETE /api/skills/{name}`. Updates and deletes require the current
`revision` returned by GET. These management routes are for explicit Settings edits, not tools for the model.
