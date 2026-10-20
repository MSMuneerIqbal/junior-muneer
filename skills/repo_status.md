---
name: repo_status
description: 'Checks a git repo''s working state fast: changed files and the last 5 commits, then a 3-line summary. Use when Muneer asks for a repo''s status.'
---
## When to use
Muneer asks for the status of a repo ("repo status for Desktop\myapp", "what's the state of my RAG project").

## Steps
1. Get the folder he named. Use his path exactly as he wrote it ("Desktop\reports" stays that). Never invent a full path or user name. If he gave a repo name only and not a folder, ask which folder it is in (or find it with `pc_find` first).
2. Call `ask_computer_agent` once with both commands for that folder, e.g.:
   - `git status --short`
   - `git log --oneline -5`
   Write the task in plain words and include the exact path. These are read-only commands. If the agent shows an approval card, tell him it is waiting for his Approve.
3. If the result says it is not a git repo, or git is not installed, say that in one line and stop.

## What to report (keep it to 3 short lines)
- **Line 1:** how many files changed, and what kind (modified / new / deleted), with the main folders or file names if they matter.
- **Line 2:** what is not committed (the staged vs unstaged picture from `git status --short`); if the tree is clean, say "everything is committed".
- **Line 3:** the last commit in one line (its message and hash) and whether the branch is behind or ahead if the output shows it.

## Rules
- No emojis. Plain, everyday English.
- Only report what git actually printed. Do not guess commits, branches or file contents.
- Do not run `git add`, `commit`, `push`, `pull`, `checkout` or anything that changes the repo unless he separately asks.
