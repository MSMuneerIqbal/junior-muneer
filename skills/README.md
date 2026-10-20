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
