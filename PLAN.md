# Junior Muneer: Project Plan (v9: safe workflow, no browser bots, more providers)

> Status: Phases 0, 1, 2, 2b, 4, 5 and 7 built; Phase 8 (WhatsApp + server) in progress; 3 and 6 paused. See TASK.md.
>
> **What changed in v7:** no browser automation anywhere. Data comes from official APIs, email alerts, RSS or text you paste in.
> Anything without an official API is copy and paste: you post or submit it yourself in your normal browser.
> Also: the terminal is always Ask, memory is saved only from your own words, and safety tests are written with each task (see section 18).

## What changed since v8 (October 2026)

The safe workflow below still holds. What was added while building (details per feature in TASK.md):

- **More AI providers, your choice in Settings.** Chat: OpenAI or **DeepSeek** (V4.1 Flash, V4 Pro). Web search: OpenAI
  or **DeepSeek's Search API**. Reading photos: OpenAI or **DeepSeek V4.1 Flash**. Live calls: **OpenAI Realtime** or
  **Google Gemini Live** (3.8 Live, 2.5 Flash Live) through the backend, with a Pakistani Urdu/English voice instruction.
  Each choice falls back to OpenAI when the other provider fails; spend is shown by provider.
- **Google through Google's own APIs** (not the Workspace MCP servers, which need a paid Workspace account): Docs, Sheets,
  Calendar, Drive and Gmail, with one "Connect Google" sign-in and the narrowest permissions that do the job.
- **Phase 4 (Gmail) built**: an inbox watcher sorts new mail and sends important emails to WhatsApp; emails to other
  people are drafts that go out only after Approve (new emails can be set to Auto; replies always wait).
- **The gate** (`backend/junior/gate.py`): every action a tool takes passes one check (your words, your rule, pause,
  Plan mode, a per-message limit), is logged, and anything read from outside is fenced. New apps plug into it.
- **Two modes**: "Junior …" makes him a professional junior (no emojis); anything else, a relaxed friend.
- **The Polisher**: emails, docs and messages are rewritten to read like a careful human wrote them; facts are checked
  in code so polishing can't change them.
- **WhatsApp** (Phase 8, before the server): text, voice notes, photos and documents, draft cards with buttons, alerts.

## 1. Goal

**Junior Muneer** is your personal AI assistant and friend. You talk to him by text, voice messages or a live voice call.
He chats about anything and helps with your work. Through his specialist subagents, he helps with your freelance work, social media and email on
**Upwork, Fiverr, LinkedIn, Facebook, Instagram, X and Gmail**, and helps with your code on **GitHub**.
He speaks **English and Urdu**.
He reads, plans, drafts and checks the work. **You decide what goes out.** Where an official API exists, he can send the approved item for you;
everywhere else, you copy the approved text and post or submit it yourself. He runs on your PC first (on any PC you choose), with a VPS (24/7) later.

## 2. The safe workflow

```
┌───────────────────────────────────────────────────────────────────────────┐
│                        SAFE WORKFLOW ARCHITECTURE                         │
├───────────────────────────────────────────────────────────────────────────┤
│ 1. DATA IN        -->  Official APIs (Gmail, Meta, LinkedIn, GitHub),     │
│                        email alerts, RSS feeds, or text you paste in.     │
│                        No browser bots, no scraping.                      │
│                                                                           │
│ 2. AI PROCESSING  -->  Junior Muneer and his subagents analyse, score,    │
│                        and draft (proposals, replies, posts, emails).     │
│                                                                           │
│ 3. HUMAN APPROVAL -->  You review and approve the draft. Then either:     │
│                        • an official API sends it (Gmail, FB Page,        │
│                          IG professional, LinkedIn posts, GitHub), or     │
│                        • you copy it, paste it in your normal browser     │
│                          window and click Submit/Post yourself.           │
└───────────────────────────────────────────────────────────────────────────┘
```

**Why:** Upwork, Fiverr, LinkedIn, X, Facebook and Instagram forbid bots in their terms and actively detect them.
Upwork and Fiverr are your income, and a ban is not worth the time saved. Copy and paste costs you a few seconds per item and carries no ban risk.

## 3. Ground rules

1. **Permission rules decide every outgoing action:** Ask, Auto or Deny, like Claude's permission modes (section 8).
2. **No browser automation.** No agent controls a browser, logs in to a site or scrapes pages. Data comes only through official APIs, email, RSS or your paste.
3. **Outside text is data, not instructions.** Job posts, client messages, emails, comments, pasted text and web search results can contain hidden instructions ("prompt injection"). Agents never follow them.
4. **Agents that read outside text cannot send anything.** Only the **API senders** (Gmail, Meta, LinkedIn) and the **Dev Executor** act. They are plain code, not AI: they send exactly the stored approved text, so the content can't change between approval and sending.
5. **Actions caused by outside content always go to Ask.** If an action comes from an email, comment, message or pasted text, it goes to your approval queue even when its type is set to Auto. Auto only applies to actions you set up yourself (your requests, your schedules). On these cards the "always allow" button is hidden, because it would have no effect.
6. **Memory is saved only from your own words.** Junior Muneer may save a memory only from your messages, never from emails, pasted text, web results or subagent reports. This stops a crafted email from planting fake "facts" in your memory.
7. **Every action runs at most once.** If the result is unclear (for example, the API times out), it's marked "check manually" instead of being retried. No double posts and no double messages.
8. Agents use **only facts from your profile, your memory and your notes**. No invented clients, numbers or results.
9. **Everything is logged**, and the dashboard has one **"Pause everything"** button.

## 4. Tech stack

| Part | Choice | Notes |
|---|---|---|
| Language (backend) | Python 3.13 | Installed |
| Agent framework | **OpenAI Agents SDK** | Agents, agents-as-tools, guardrails, tracing, MCP, voice and realtime support |
| AI models | **OpenAI only** for now: a **strong** model for Junior Muneer and the writers, a **small** model for routine steps | Picked 2026-10-14: **gpt-6.1-sol** (strong) and **gpt-6-luna** (small), in `agents/models.toml` |
| Voice | OpenAI **speech-to-text**, **text-to-speech** and **Realtime** (live voice) models, in **English and Urdu** | Section 7.2 |
| Web search | OpenAI's built-in web search tool, read-only, on a small **web researcher** helper | Junior Muneer calls it through a light `web_search` tool: the built-in tool adds ~4,400 tokens to every request it's attached to, so keeping it off his own requests makes normal messages ~5× cheaper |
| Model router | One settings file: which model each agent uses | Claude or others can be added later without rewrites |
| Backend | **FastAPI** | REST API + **WebSocket** for live streaming chat and voice |
| Frontend | **Next.js (React)** | Chat, voice and live updates need a real app UI. You already know Next.js |
| Email | **Gmail API**: read, and send through the permission rules | Also the main source of Upwork and Fiverr alerts |
| Official APIs | Meta Graph API (Facebook **Page**, Instagram **professional**), LinkedIn API (posts to your profile) | Everything else is copy and paste |
| RSS | A small RSS reader | For any source that offers a feed (blogs, news, job boards that still have one) |
| GitHub | GitHub's official **MCP server** + a **fine-grained token** limited to the repos you choose | Official API, not a browser |
| Terminal (later) | A **command runner** limited to a projects folder and an allowed-commands list | **Always Ask**, never Auto (section 8) |
| Database | SQLite (one file) | Chats, memory, drafts, approvals, rules, clients, logs, costs |
| Scheduler | Built into the backend | Checks every few minutes, runs scheduled API posts and reminders. Times are stored in UTC and shown in your time zone |
| Code storage | **Git** (private GitHub repo) | History of every change; easy to move to another PC or the VPS |
| Later | WhatsApp; Docker + VPS | Last phase |

**Not used:** Playwright, browser control, computer use, an agent Chrome profile. Agents never see or use your site logins.

## 5. Your accounts and how data gets in and out

| Account | Data in | Going out |
|---|---|---|
| Upwork | **Job alert and message notification emails** (Gmail API) + **paste** a job post or client message | **Copy and paste.** You submit proposals and send messages yourself |
| Fiverr | **Notification emails** (orders, messages) + **paste** | **Copy and paste.** You send messages and deliveries yourself |
| LinkedIn (personal) | **Paste** (posts to comment on, comments on your posts) | **LinkedIn API** for your own posts; copy and paste for comments and replies |
| Facebook **personal profile** | **Paste** | **Copy and paste** (no API for personal profiles) |
| Facebook **Page** | **Meta API** (posts, comments) | **Meta API** |
| Instagram **personal** | **Paste** | **Copy and paste** (no API for personal accounts) |
| Instagram **professional** | **Meta API** (posts, comments) | **Meta API** |
| X | **Paste** | **Copy and paste** (X's API is paid; it can be added later if worth it) |
| Gmail | Gmail API | Gmail API |
| GitHub | GitHub MCP (read-only tools) | Dev Executor through the GitHub MCP |

**Notes:**
- **Upwork removed its public job RSS feeds in 2024**, so email alerts from your saved searches are the main source. Upwork has an official API, but it needs an application approved by Upwork. We can apply later as an option; the plan doesn't depend on it.
- **LinkedIn's API can post to your profile but cannot read comments on personal posts** (that needs a restricted partner API). Comments on your LinkedIn posts come in by paste.
- **Instagram professional** can use either the Facebook-linked API or the newer "Instagram API with Instagram Login" (no Facebook Page needed). We pick the simpler one in phase 3.

### 5.1 The Paste box

One place in the dashboard (and in the chat: just paste) where you drop in text from any site: a job post, a client message, a post you want to comment on, comments on your post.
You pick (or Junior Muneer guesses) what it is and which platform it's from. It's saved as **outside content**: data, never instructions, and anything drafted from it goes to Ask.

### 5.2 Copy-and-paste items

For platforms without an API, an approved item gets: **Copy text** · **Open platform** (opens the right page in your normal browser) · **Mark as posted / sent**.
Marking it posted records it in history and style memory. Nothing is sent by the system.

## 6. The team

### 6.1 Junior Muneer (orchestrator and friend) + subagents

You always talk to **Junior Muneer**, and he always answers you.

```
                       YOU (text · voice message · live call · paste)
                            │  ▲
                  message   │  │  one answer, from Junior Muneer
                            ▼  │
LEVEL 1             ┌────────────────┐  • Chats like a friend about anything
ORCHESTRATOR        │ JUNIOR MUNEER  │  • Answers simple questions himself
                    └───────┬────────┘    (memory, web search, database: chats, queue, stats, logs)
                            │ calls subagents only when needed (several at once if useful)
     ┌───────────────┬──────┴────────┬───────────────┬──────────────────┐
LEVEL 2  SOCIAL MEDIA    FREELANCE       EMAIL AGENT     DEVELOPER AGENT     NEWS AGENTS
         MANAGER         MANAGER                         (GitHub, terminal)  (AI news, Pakistan news)
                                                                             + future subagents
     └───────────────┴──────┬────────┴───────────────┴──────────────────┘
LEVEL 3  SHARED WORKERS:  Writing team (Writer → Checker → Humanizer)
                          API senders: Gmail · Meta · LinkedIn (code, approved items only)
                          Dev Executor (approved GitHub/terminal actions)
                          Safety Guard (code, not AI)
```

**How Junior Muneer decides:**
- **Not related to any subagent** (general chat, advice, ideas, tech questions, "how was my week?") → **he answers you himself, like a friend.**
- **Needs a specialist** ("write a LinkedIn post", "here's a job post, write a proposal") → he calls the right subagent(s), then answers you with the result.
- **Simple data question** ("how many proposals this week?") → he answers from the database. No subagent needed.

**His personality** (it lives in one editable file, `agents/junior_muneer.md`):
- friendly, warm, a bit of humour, simple language;
- speaks **English and Urdu**, both Urdu script and Roman Urdu, and replies in the language you use. Client work (posts, proposals, messages) stays in English unless you ask otherwise;
- calls you by your name and remembers what you tell him (section 11);
- honest: he says when he doesn't know, and pushes back when an idea is risky;
- always clear that he is an AI. No pretending to be human.

**Agent-as-tool, not handoff:** subagents work for Junior Muneer and report back to him; they never take over your chat.
So you get one clear answer in one voice, and he can combine several subagents ("What happened today?" = email + freelance + social).

**He cannot act on his own.** He has no send tools. Every action goes through the approval queue, the permission rules and an API sender, or through you (copy and paste).

**Long tasks don't block the chat.** If a subagent needs more than a few seconds, Junior Muneer says "I'm on it", keeps chatting with you,
and posts the result in the chat when it's ready.

### 6.2 The subagents and workers

| Agent | Job | Tools | Can it act? |
|---|---|---|---|
| **Junior Muneer** | Your friend and chief: chats, answers, plans, delegates | Memory, web search, database (read), subagents | No |
| **Social Media Manager** | Plans content, picks pasted posts worth commenting on, handles comments on your posts | Meta API (read), pasted content | No, drafts only |
| **Freelance Manager** | Scores Upwork jobs from alert emails and pastes, tracks Fiverr orders and deadlines, drafts client replies | Email (read), pasted content | No, drafts only |
| **Email Agent** | Reads, sorts and summarizes your inbox; drafts replies; turns Upwork/Fiverr alerts into tasks | Gmail API (read) | No, drafts only |
| **AI News Agent** | The last 15 days of AI news, straight from the big companies' own pages: new models, how they work, benchmarks and who is on top in each field (coding, reasoning, agents, voice, image and video, open models), plus big business moves. Gives you a short, sourced summary | Official RSS feeds and newsroom pages (plain HTTP reads, no browser bots), official leaderboards, web search as a fallback | No, read and summarize only |
| **Social News Agent** | Pakistan only: what is happening in the country and what people are talking about online, in the last 15 days (newest first). Neutral, no political opinions | RSS feeds of big Pakistani news sites, Google Trends for Pakistan, web search as a fallback | No, read and summarize only |
| **Developer Agent** | Your GitHub helper: lists repos, summarizes issues, PRs and commits, reviews code, drafts issues, PR descriptions and commit messages. Later it proposes terminal commands | GitHub MCP (read-only tools) | No, it drafts and plans; the Dev Executor runs approved actions |
| **Dev Executor** | Runs **one approved** GitHub action (create an issue, push a branch...) or terminal command, exactly as approved | GitHub MCP (write tools), terminal (later) | **Yes, approved items only** |
| **Writer** | Writes posts, comments, proposals, messages and emails, using the platform's playbook | None | No |
| **Checker** | Checks facts, voice, platform rules and red lines, then gives a score out of 10 | None | No |
| **Humanizer** | Rewrites in simple, natural English | None | No |
| **API senders** (Gmail, Meta, LinkedIn) | **Plain code, not AI.** Sends one approved item with the exact stored text, records the result, never retries an unclear result | Official APIs | **Yes, approved items only** |
| **Safety Guard** | A rule check, not AI. It runs before every action and blocks anything that breaks a red line, a limit or the budget. It also checks that the text being sent is exactly the approved text | n/a | It can block |

### 6.3 Three ways work starts

1. **You ask Junior Muneer** (text, voice, live call; later WhatsApp).
2. **You paste** something (a job post, a client message, a post to comment on).
3. **Triggers:** schedules, new emails and new API comments go **straight to the right manager**. The results land in the dashboard, and Junior Muneer tells you about them when you ask, or greets you with them ("3 things need your OK").

### 6.4 The news agents

Two read-only subagents that keep you in touch with the market and your country. Junior Muneer sends them every news question:
"what's new in AI?", "which model is best for coding now?", "what happened with GPT and Gemini this week?" go to the **AI News Agent**;
"what's going on in Pakistan?", "what's trending today?" go to the **Social News Agent**. Other news questions still use his normal web search.

- **Where the news comes from:** the sources' own pages (all checked live on 2026-10-15). AI: the official blogs and newsrooms of OpenAI, Anthropic,
  Google DeepMind, Google AI, Google Research, Meta AI and Meta's newsroom, Microsoft, NVIDIA, Apple, Amazon and AWS, Mistral, DeepSeek, Hugging Face
  and Arena (LMArena). Not readable without a browser, so not used: xAI (blocks automated readers, no feed), Qwen (app-only site), Arena's leaderboard page.
  Rankings ("who's on top" in coding, reasoning, math, voice, image, video) come from **Artificial Analysis's official API**, copied by code exactly as
  published; it needs a free key (`ARTIFICIAL_ANALYSIS_API_KEY`), and without it the digest says rankings are off.
  Pakistan: Dawn, Geo, The Express Tribune, ARY, Business Recorder and ProPakistani, plus Google Trends (Pakistan) for what's trending.
  (The News was dropped: its feeds stopped updating in 2025.)
  Read with plain HTTP (RSS, Atom or the page itself), the same way a feed reader does: **no browser bots, no logins**.
  The list lives in one editable file, `news/sources.toml`, so you can add or remove sources.
- **Only real news from official sources (no fakes, no rumours):**
  - Only sources on the allowed list in `news/sources.toml` are read: the companies' own sites for AI news, and the official leaderboards for rankings.
    Pakistan news comes only from established news organisations, never from social media posts, blogs or forwarded messages.
  - Every item in a digest must point to an article that was actually fetched from an allowed source. **Code checks this, not the AI:**
    an item whose link isn't in the fetched list, or whose date is outside the 15 days, is dropped before you see it.
  - The AI only summarizes what the article says. No guessing, no "reportedly", no numbers that aren't in the source.
    Benchmark scores and rankings are quoted from the official leaderboard or the company's own release, with the source named ("OpenAI says…", "LMArena shows…").
  - A claim only one source makes is shown as that source's claim. Web search is used only to find an official page, and its result must also be on the allowed list.
  - If a source can't be read, the digest says so ("Anthropic's news page couldn't be read today") instead of filling the gap.
- **What you get:** a short summary in sections (AI: new models and releases · benchmarks and who's on top, by field · agents and tools · business moves;
  Pakistan: top stories · trending online · tech, internet and freelancing · economy that affects you), each item with its date and a link to the source.
  Facts only from the sources; when sources disagree, both are given. In English, or Urdu if you ask.
- **Fast and cheap:** each agent builds one digest a day (07:30 by default; on/off and time in Settings) with the small model and keeps it
  (about $0.003 and 40 seconds a digest). The AI agent's articles are grouped by company so every company's news is seen; news sites' feeds only carry their
  latest stories, so each digest also keeps the important stories of earlier digests in the 15 days. Questions are answered from the digest in seconds;
  if a question isn't covered, web search may only search the official sites (`[search]` in `news/sources.toml`). "Refresh" fetches again.
  News pages are **outside content**: never followed as instructions, never saved to memory. Switching the news agents to the strong model gives richer
  digests for about $0.06 each (one line in `agents/models.toml`).
- **Where you see it:** in the chat and live calls (Junior Muneer reads you the summary), and on a **News** page with two tabs (AI · Pakistan).

### 6.5 Adding new subagents later

Every subagent is **one file** in `agents/`, the same idea as Claude Code subagents: name, description (Junior Muneer reads it to decide when to call),
instructions, model, tools, and action types (each follows the Ask / Auto / Deny rules).
An **agent registry** loads them all at startup. To add a new subagent you add one file, and Junior Muneer can use it straight away.

## 7. The dashboard (where you talk to Junior Muneer)

### 7.1 Layout

```
┌───────────────┬──────────────────────────────────────────────┬──────────────────┐
│ JUNIOR MUNEER │  Chat: "Weekly planning"            [📞 Live] │ TODAY            │
│               │                                              │ Mode: [Ask ▾]    │
│ + New chat    │  You: [pasted Upwork job post]               │ ⏸ Pause all      │
│ 🔍 Search     │       Write a proposal for this              │                  │
│               │                                              │ Needs your OK: 3 │
│ Today         │  Junior Muneer:                              │  • LinkedIn post │
│  • Weekly pl… │  ▸ Asked Freelance Manager… (show work)      │  • Fiverr reply  │
│  • LinkedIn … │  Good match: 8/10. Client is verified, $800… │  • Email to Ali  │
│ Yesterday     │  ┌────────────────────────────────────────┐  │                  │
│  • Fiverr cl… │  │ Proposal draft · Upwork · 9/10         │  │ Inbox: 5 new     │
│  • 🎙 Voice…  │  │ [Copy] [Open Upwork] [Edit] [Posted ✓] │  │ Spend: $0.42     │
│ Last week     │  └────────────────────────────────────────┘  │                  │
│  • …          │                                              │ Alerts           │
│───────────────│  ┌──────────────────────────────────┐ 🎙 ➤   │  • Order due in  │
│ 💬 Chat       │  │ Message or paste…                │        │    6 hours       │
│ ✅ Approvals  │  └──────────────────────────────────┘        │                  │
│ 📥 Inbox      │                                              │                  │
│ 📣 Social     │                                              │                  │
│ 💼 Freelance  │                                              │                  │
│ 🧠 Memory     │                                              │                  │
│ 📜 Activity   │                                              │                  │
│ ⚙ Settings    │                                              │                  │
└───────────────┴──────────────────────────────────────────────┴──────────────────┘
```

On a phone the side panels fold away and the chat fills the screen.

### 7.2 Three ways to talk

| Mode | How it works | Best for |
|---|---|---|
| **Text chat (live)** | Answers stream in word by word. While he works you see live steps ("Asking Freelance Manager…") | Most work, and pasting |
| **Voice message** | Hold the 🎙 button and speak → your speech becomes text → Junior Muneer answers in text **and** reads it aloud (auto-play on/off) | Quick questions, hands busy |
| **Live call** | Press 📞 for a hands-free, real-time conversation, like a phone call. You can interrupt him. A live transcript shows on screen | Talking things through, planning |

- **Text and voice messages** use exactly the same Junior Muneer, with speech converted to text and back.
- **Live calls** use OpenAI's real-time voice model, set up with **the same personality, memory and tools**. For work that needs subagents
  he says "let me check", and the result arrives in the call and in the chat.
- **Approvals need a click, not your voice** (at least at first). Voice can be misheard, so during a call any approval card appears on screen for you to tap.
- **Settings:** voice choice, speaking speed, auto-play replies, language (**English / Urdu / match me**).
- **Cost:** text is cheapest, voice messages cost a little more, and live calls cost the most per minute. The dashboard shows spend per mode, and live calls have a daily minutes limit.

### 7.3 All chats in one place

- **Every conversation is saved:** text chats, voice messages (transcript + audio), live calls (full transcript) and, later, WhatsApp.
- The **sidebar lists all chats** by date, with a 🎙 / 📞 icon for voice and calls. You can search, rename, pin and delete them.
- Every answer has **"Show work"**: which subagents he asked, what they did, and the cost of that answer.
- Approval cards appear **inside the chat** and on the **Approvals** page. Both are the same item, so approving in one place updates the other.
- **Browser notifications** for new approvals and important alerts (until WhatsApp is added).

### 7.4 Pages

1. **Chat:** talk to Junior Muneer, and paste anything into it
2. **Approvals:** every item waiting for your OK. API items: Approve · Approve + always allow · Edit · Reject. Copy-and-paste items: Copy · Open platform · Edit · Mark as posted · Reject
3. **Inbox:** email summaries and reply drafts
4. **Social:** posts, ideas, suggested comments and replies, per account
5. **Freelance:** scored Upwork jobs, proposals, client conversations, Fiverr orders
6. **Memory:** what Junior Muneer remembers about you; view, edit or delete
7. **Activity:** the audit log of every read and action
8. **Settings:** permission rules, models per agent, voice, daily limits, budget cap, time zone, profile and playbooks

## 8. Permissions: Ask / Auto / Deny (like Claude)

Every outgoing action has a type, for example `facebook.page.post`, `linkedin.post`, `gmail.send`, `github.issue.create`. Each type has one rule:

| Rule | What happens |
|---|---|
| **Ask** | It goes into your approval queue. Nothing happens until you click |
| **Auto** | It runs by itself; it is still logged, checked by the Safety Guard and limited per day |
| **Deny** | It never runs |

Approval buttons: **Approve · Approve + always allow this kind** (switches the rule to Auto; hidden on locked types and on items caused by outside content) **· Edit · Reject**.
**Mode menu** (under the message box, like Claude's permission modes; also in Settings):

| Mode | What happens |
|---|---|
| **Auto** | Each action follows its Ask / Auto / Deny rule above |
| **Manual** | Every action waits for your OK, even ones set to Auto |
| **Plan** | He shows a short plan first; nothing is drafted or queued until you switch to Auto or Manual |
| **Pause everything** (on/off) | Nothing is sent and no background work runs; chat still works |

There is no "bypass permissions": locked types and anything caused by outside content always wait for you.

| Action | Default | Can change to Auto? |
|---|---|---|
| Read emails, API comments, RSS; your pastes | Auto | n/a |
| Create drafts, summaries, ideas; chat; web search | Auto | n/a |
| Post through an API (Facebook Page, Instagram professional, LinkedIn) | Ask | Yes |
| Reply to a comment through an API (Facebook Page, Instagram professional) | Ask (comes from outside content) | No (ground rule 5) |
| Send email | Ask | Yes for your own new emails (not recommended); replies are always Ask |
| **Copy-and-paste items** (Upwork, Fiverr, LinkedIn comments, Facebook/Instagram personal, X) | You send them yourself | n/a: the system never sends these |
| **GitHub:** read repos, issues, PRs, code | Auto | n/a |
| **GitHub:** create an issue, comment, open a PR, push to a branch | Ask | Yes |
| **GitHub:** merge, push to `main`, create a release | Ask | **No, locked** |
| **GitHub:** delete a repo or branch, force-push, change visibility or settings | **Deny** | **No, locked** |
| **Terminal:** run an allowed command | Ask | **No, locked.** Commands like `python`, `npm` and `npm test` can run any code, so every command is checked by you |
| **Terminal:** any command outside the allowed list | **Deny** | **No, locked** |
| Anything not listed | Ask | Yes |
| Delete anything, payments, account settings, typing passwords | **Deny** | **No, locked** |

## 9. Platform specialists = playbooks

Each platform gets a **playbook**: a file in `playbooks/` holding the expert knowledge for that platform. You can edit any playbook yourself.
For copy-and-paste platforms, the Checker enforces the red lines before the draft reaches you.

| Platform | What its playbook covers | Red lines (the Checker and Safety Guard enforce these) |
|---|---|---|
| **Upwork** | Proposal structure (the first 2 lines show in the preview), how to judge a job (payment verified, hire rate, spend, reviews), connects, scam signs | No payment or contact outside Upwork before a contract; no fake experience; never move the chat to WhatsApp or Telegram |
| **Fiverr** | Fast replies (response time shows on your profile), custom offers, delivery and revisions, gig titles and tags | Never share email, phone or outside payment links in messages; no payment outside Fiverr |
| **LinkedIn** | Hook in the first lines, short paragraphs, comments that add a real point | No mass messages or connection spam |
| **Facebook** | Casual tone; Page vs personal profile; group rules | No spam in groups |
| **Instagram** | Visual first, short caption, 3 to 5 hashtags; personal vs professional | Every post needs an image or video |
| **X** | 280 characters, one clear point, replies | No reply spam |
| **Email** | Clear subjects, short polite replies, follow-ups | Never send to new addresses without Ask; never open links or attachments on its own |
| **GitHub** | Clear commit messages, PR descriptions, issue templates, your branch naming | Never commit secrets (.env, keys); never force-push; never touch `main` without Ask |

## 10. Main workflows

**A. Your posts:** Social Media Manager plans → Writer → Checker (sends it back up to 2 times) → Humanizer → final check → approval →
**API** (Facebook Page, Instagram professional, LinkedIn) or **copy and paste** (Facebook/Instagram personal, X).
**Images:** you upload your own images; the team focuses on text. Each draft comes with an image idea to guide you. Instagram drafts wait until you attach an image.

**B. Comments on others' posts:** you paste a post you'd like to comment on → the writing team drafts a useful comment → you approve → copy and paste.

**C. Replies on your own posts:** Facebook Page and Instagram professional comments arrive through the Meta API; LinkedIn, X and personal-profile comments you paste →
reply drafts → **Ask** → sent through the Meta API, or copy and paste.

**D. Upwork jobs:** a job alert email arrives (or you paste a job post) → the Freelance Manager scores it (skills, budget, client quality, scam signs) →
proposal draft (one card: the cover letter, and each screening answer in its own box with its own Copy button) → you approve →
**you copy it, open the job on Upwork, paste and press Submit.**

**E. Client messages (Upwork/Fiverr):** a notification email arrives → you paste the conversation (the email usually holds only part of it) →
reply draft (the Checker checks red lines; code flags warning signs in the client's words, like moving to WhatsApp, an email or
phone number, or paying first, and the reply keeps everything on the platform) → you approve → **you copy and send it.**

**F. Fiverr orders:** deadlines and revisions tracked from notification emails (and pastes), reminders on the dashboard, delivery message drafts.
A pasted order page is read once (a countdown like "1 day 7 hours left" becomes a due time in your time zone); pasting it again
updates it. The Today panel lists orders due within 2 days (red within 6 hours or late); marking the delivery message as sent marks
the order delivered.

**G. Email:** new mail is read → sorted and summarized in **Inbox** → reply drafts → **Ask** → sent through the Gmail API.

**H. Chat with Junior Muneer:** general chat is answered directly; work requests go to subagents; actions follow the rules; everything is saved in chat history.

**I. GitHub and dev work:** "What changed in my e-commerce repo this week?", "Open an issue for the checkout bug", "Write a PR description for my branch" →
the Developer Agent reads through the GitHub MCP → drafts → **Ask** → the Dev Executor does it. Terminal commands (later) follow the same path and are always Ask.

## 11. Data and memory

- **Chat history:** every conversation and message (text, voice transcript + audio, call transcript) and the subagent steps behind each answer.
- **Long-term memory about you:** facts and preferences you share ("I prefer short proposals", "my rate is $25/hr"). Junior Muneer saves them on his own
  **only from your own messages** (ground rule 6), and shows a small "Memory updated" note in the chat, which you can undo. You can see, edit and delete everything on the Memory page.
- **Conversation memory:** recent messages go to the model; older parts of a long chat are summarized to save cost.
- `my_profile`: skills, services, rates, real projects and results, writing voice. The source of facts for all writing.
- `playbooks/`: one expert file per platform.
- **Pasted content:** saved with its platform and type, marked as outside content.
- **Style memory:** every text you approve (or mark as posted) becomes a style example for future drafts.
- **Clients and contacts:** name, platform or email, history, notes.
- **Approval queue, permission rules, audit log, usage and cost.**
- **Backups:** the data folder is copied automatically every day (the last 14 days are kept), because your chats and memory are valuable.

## 12. Safety, limits, cost and privacy

- The permission rules (section 8) and a Safety Guard check before every action
- **No browser automation:** no agent logs in to, clicks on or scrapes any site. Your site logins stay only in your own browser
- Daily caps (for example API posts per platform, live-call minutes)
- **Budget:** no fixed monthly budget, because you'll watch usage yourself. A **safety cap of $5/day** (editable) stops runaway loops caused by bugs. Also set a monthly limit in your OpenAI account settings.
- API keys and tokens stay in the backend `.env` (never in Git). The browser page never sees them. Live calls use OpenAI's "unified" WebRTC set-up: the backend passes the browser's call offer to OpenAI, so the browser gets no key at all (not even a short-lived one), and the backend stays attached to the call to run tools, save the transcript and track cost
- The dashboard is local-only on your PC; on the VPS it gets a login and HTTPS
- **Microphone note:** browsers allow the mic only on `localhost` or HTTPS. On your PC it works; **voice from your phone needs HTTPS**, so it comes with the VPS phase or a secure tunnel
- **Biggest cost:** live calls (per minute). Capped and shown on the dashboard
- **GitHub:** a **fine-grained token** that you create and paste into `.env`, limited to the repos you pick. It is not your main GitHub login,
  so the agent can never reach repos you didn't give it
- **Terminal:** only inside your projects folder, only allowed commands, **every command needs your OK**, every command logged; dangerous commands (delete, format, system changes) are always denied
- **Privacy:** chats, emails, pasted text and client messages are sent to OpenAI for processing. By default OpenAI doesn't train on API data, but check its current data policy. Everything else stays in your local database

## 13. How we test

- **Safety tests are written with each task, not at the end.** The task that builds a safety part also adds its tests: permission rules, locked types,
  the "outside content → Ask" rule, the "memory only from your words" rule, the Safety Guard, daily limits, "run at most once" and the budget cap.
  These must never break, so every change runs them.
- **Fake-AI tests for every workflow**, so we can test flows without spending money.
- **Fake-API tests** for the Gmail, Meta, LinkedIn and GitHub senders, so nothing real is sent during tests.
- **Your test at the end of each phase**, using the "done when" goal in the roadmap.

## 14. Roadmap

Each phase ends with you testing it. We only move on when it works for you.

| Phase | What you get | Done when |
|---|---|---|
| **0. Foundation + text chat** | Git repo, FastAPI backend, Next.js dashboard shell, OpenAI Agents SDK, model router, agent registry, **Junior Muneer text chat with live streaming**, chat history, memory, web search, audit log, cost tracking, $5/day cap, Pause, daily backups | You chat with Junior Muneer like a friend; the chats are saved and show in the sidebar |
| **1. Voice** | Voice messages (speak, and he answers aloud) + **live call** mode + transcripts saved in history, in English and Urdu | You hold a 5-minute live call in English and one in Urdu, and both show in the chat history |
| **2. Writing team, approvals + Paste** | Social Media Manager (planner), Writer, Checker, Humanizer, playbooks, **permission rules (Ask/Auto/Deny), approval queue, approval cards in chat**, **Paste box**, **copy-and-paste items**, image upload | You approve 5 posts you'd really publish, and draft one comment from a pasted post |
| **2b. News agents** | **AI News Agent** (last 15 days of AI news from the big companies' own pages, benchmarks and who's on top) and **Social News Agent** (Pakistan news and what's trending), a daily digest, a News page, used in chat and calls | "What's new in AI?" and "What's happening in Pakistan?" give correct, sourced summaries of the last 15 days |
| **3. Official social APIs** | Facebook Page and Instagram professional (Meta), LinkedIn posts; comments on Page/IG posts through the API | An approved post goes live through the API, and a reply to a real comment is sent |
| **4. Email** | Email Agent: inbox summary, sorting, reply drafts, sending | You answer a real email from the dashboard |
| **5. Freelance** | Upwork job scoring from alert emails and pastes, proposals, Fiverr orders and messages, client replies: all copy and paste | A real proposal, drafted from a real job alert, is ready for you to paste into Upwork |
| **6. Developer Agent** | GitHub MCP (read, then approved actions through the Dev Executor), then the terminal (always Ask) | You ask "what changed in my repo this week?" and get a correct answer; an approved issue gets created |
| **7. Junior Muneer, full power** | Multi-step tasks across subagents, daily briefing, combined reports, smarter memory | "What happened today?" gives a full, correct summary |
| **8. WhatsApp + VPS** | Chat, voice notes and approvals on WhatsApp (in the same chat history); Docker, HTTPS, login, 24/7 server | It runs for a week without your PC |
| **9. Your computer** | The Computer Agent reads, writes, moves, deletes (to the Recycle Bin) and runs terminal commands on your PC, only in folders you allow and through your Ask/Auto/Deny rules; built locally first, then the PC Helper for the VPS (section 14c) | From WhatsApp you ask for a file on your PC and get it; an approved change and an approved command run, and a refused one doesn't |

Text chat (phase 0) and voice (phase 1) come first, as you chose. You can still change the order of the later phases.
The old browser phase is gone, so there is one phase fewer.

**Existing code:** the backend parts already written (database, approval flow, platform rules, AI-phrase checks) get reused.
The HTML pages get replaced by the Next.js dashboard, and the AI part switches from the Claude SDK to the OpenAI Agents SDK.

**Needed from you:**
- **Phase 0:** an OpenAI API key, which you paste into `.env` yourself
- **Phase 3:** a Meta developer app and a LinkedIn developer app (I'll guide you). Notes:
  - **LinkedIn** API logins expire after about 60 days, so you reconnect with one click every 2 months.
  - The **Instagram** API needs the image at a public web address. While on your PC, we'll use a temporary image host; on the VPS it's simple.
- **Phase 4:** a Google Cloud project for Gmail access (I'll guide you; the app is set to "production" for personal use so Google doesn't log you out every 7 days)
- **Phase 5:** set up Upwork saved-search alerts and Fiverr email notifications so they reach your Gmail
- **Phase 6:** a GitHub fine-grained token for the repos you choose (I'll guide you)
- **Phase 8:** the official WhatsApp Business API needs **a separate phone number** (your personal WhatsApp number can't be used for both)

## 14b. Voice test results (P1-03, 2026-10-15)

Round trip: 6 everyday Urdu sentences, spoken by 3 OpenAI voices, transcribed back.

| Speech-to-text | Accuracy | Written in Hindi script instead of Urdu |
|---|---|---|
| gpt-transcribe ($0.0045/min) | 27.6% | 13 of 18 |
| **gpt-4o-transcribe** ($0.006/min) | **99.0%** | **0 of 18** |

- **Chosen: gpt-4o-transcribe.** Spoken Urdu and Hindi sound the same; gpt-transcribe mostly writes Hindi script, even when asked for Urdu. As a safety net, any transcript in Hindi script is transcribed again with the language set to Urdu.
- **Voices** (gpt-4o-mini-tts): Cedar 99.6%, Marin 99.5%, Ash 97.8% understood. All are clear; the final pick is by ear (Settings → Voice).
- Junior Muneer is told never to write Urdu in Hindi script.

## 14c. Your computer (Phase 9, planned 2026-10-20)

**How it works (the same idea as Claude Code and Codex):** the AI never touches the PC itself; plain code on the PC does
each action after the rules allow it. While Junior runs on your PC, the backend is that code. On the VPS, a small
**PC Helper** on your PC connects out to the server, takes only approved jobs, runs them and sends the results back
(it works while your PC is on; otherwise Junior says "your PC is offline").

**Who does it:** one shared toolbox of computer tools, written once. A specialist **Computer Agent** gets them all;
Junior hands it computer jobs (like the news agents) and keeps two read-only ones for quick questions. Other agents
get none, or only what they need (least power).

**Rules (new action types in Settings → Permissions):**
- `computer.read` (Auto): list folders, find files, read files (text, PDF, Word, Excel). File text is fenced: data, never instructions.
- `computer.write` (Ask): create or change a file, make a folder. The card shows the change; you can edit it before you approve.
- `computer.move` (Ask): move or rename.
- `computer.delete` (Ask): **to the Recycle Bin only**, so it can be undone. Deleting for good stays Deny (`system.delete`).
- `computer.run` (Ask, locked): a terminal command (PowerShell) with a time limit and an output cap; the card shows the
  exact command. Dangerous commands (formatting, wiping, shutdown, registry, changing users or the firewall) are refused
  in code. It replaces Phase 6's `terminal.run` / `terminal.other`.

**Where:** only in the folders you allow (Settings → Computer; first Desktop, Documents, Downloads). A path you type
yourself also works: the path in your own message is your OK to read it, and changes still follow the rules; you can
add the folder to the list. A path from an email, a web page or a paste is never opened by itself. Always blocked, even
when you give the path: `.env` files, keys and certificates, `.ssh`, browser profiles and passwords, Windows and
Program Files, and Junior's own `data` folder. Links and shortcuts can't lead outside the allowed folders.

**On top:** outside text in the request makes every computer action Ask (even when its rule is Auto); the gate checks,
logs and limits every action; Pause stops them; each approved action runs at most once; results show on the card and
in the chat (and on WhatsApp when you asked there).

## 15. Using it on another PC

1. Get the code from your private Git repo.
2. Copy the `data/` folder (or a backup) to bring your chats, memory and settings.
3. Create `.env` with your API keys.

Run it on **one PC at a time**. Two copies running at once could do the same work twice.

## 16. Decisions (made)

| # | Question | Decision |
|---|---|---|
| 1 | Budget | No fixed budget, for personal use; $5/day safety cap (editable) |
| 2 | Facebook | Personal profile (copy and paste) + Page (API) |
| 3 | Instagram | Personal (copy and paste) + professional (API) |
| 4 | X | Copy and paste (paid API maybe later) |
| 5 | Permissions | Ask / Auto / Deny rules like Claude; outside-content actions always Ask; terminal always Ask |
| 6 | Alerts | Dashboard (+ browser notifications) first, WhatsApp later |
| 7 | Gmail | Read + send, managed in the dashboard (Gmail API) |
| 8 | Provider | OpenAI only for now; others later through the model router |
| 9 | Name and role | **Junior Muneer**: a friend who answers anything himself and uses subagents only when needed |
| 10 | Talking | Text chat (live streaming), voice messages, live call; all chats saved and shown |
| 11 | Frontend | Next.js (React) dashboard + FastAPI backend |
| 12 | Live chat | A live voice call (hands-free, real-time); text chat also streams live |
| 13 | Language | English and Urdu (Urdu script and Roman Urdu); he replies in the language you use; client work stays in English |
| 14 | Phase order | Text chat first, then voice, then the rest |
| 15 | Images | You upload your own; the agents focus on text. No AI-made images |
| 16 | Code storage | Private GitHub repo: https://github.com/MSMuneerIqbal/junior-muneer |
| 17 | GitHub agent | A Developer Agent through GitHub's official MCP server + a fine-grained token; terminal later, always Ask |
| 18 | Browser automation | **None.** Official APIs, email, RSS and paste in; API or copy and paste out (v7) |
| 19 | Memory source | Memories are saved only from your own messages (v7) |

## 17. Known risks

- **Account restrictions:** much lower now that no bots touch Upwork, Fiverr, LinkedIn, X or personal profiles. Remaining risk: API posting on the Page, Instagram and LinkedIn, kept within daily caps.
- **Upwork and Fiverr emails change format:** the email parser may miss fields. When unsure, the item is shown with the raw email so you can paste the full job.
- **Less automation:** you copy and paste for most platforms. This is a deliberate trade: a few seconds per item for no ban risk.
- **AI mistakes:** this is why Ask is the default and the checker exists.
- **Prompt injection through email, comments, pasted text and web results:** handled by ground rules 3 to 6. The risk is reduced, not zero, so locked types stay locked.
- **Costs:** live calls cost the most; they are capped.
- **Expiring connections:** LinkedIn (every 60 days) and Meta tokens need reconnecting. The dashboard warns you before they expire.
- **Urdu voice quality:** speech recognition and the speaking voice may be weaker in Urdu than in English. We test this early in phase 1 and pick the best voice and model.
- **Terminal access** is powerful. It stays limited to one folder and an allowed-commands list, every command needs your OK, and dangerous commands are always denied.

## 18. Change log

- **v9.1 (2026-10-20):** Phase 9 planned (section 14c): the Computer Agent works on your PC through shared computer tools,
  allowed folders, an always-blocked list and the Ask/Auto/Deny rules; deletes go to the Recycle Bin; terminal commands
  are always Ask. Built and live-checked locally first; the PC Helper (for the VPS) comes after. Phase 6's terminal runner
  (P6-05) moves here.
- **v8.0 (2026-10-17):** Phase 6 paused by Muneer after P6-01 (GitHub connects in the app with GitHub's device login, or the
  GitHub CLI login; read-only, two locks). Phase 7 built:
  - P7-01: a request with several parts gets a live checklist (like Claude's to-do list); its parts run together.
  - P7-02: long work runs in the background: Junior says he's on it, you keep chatting, and the result (with its cards) is posted
    to the same chat. At most 3 at a time, not while paused; tasks cut off by a restart are marked failed.
  - P7-03: "What happened today?" (or yesterday, this week) is answered from a report built by code from the database, and a
    morning briefing (☀, Settings → News) says what needs you, what got done yesterday and the news, from those facts only.
  - P7-04: memories show the date they were saved; past 100, Junior gets the newest plus the ones that fit your message and can
    search the rest; a weekly tidy-up archives duplicates and outdated memories (code-checked, restorable, never rewritten).
  - P7-05: your own RSS/Atom feeds (News → Your feeds), read every 3 hours by the same safe reader, kept apart from the official
    news, and outside content for Junior.
  - Every tool failure is now logged with the real error and audited as an error (the SDK hid it).
- **v7.9 (2026-10-16):** P5-04 to P5-06 built: the Freelance Manager scores pasted jobs (a scam is always skip, in code) and writes one
  proposal card per job, with each screening answer in its own box (code keeps only answers to the job's own questions). Proposals
  hold only the text to paste, and the Checker flags lines that undersell you. Every AI request now gives up after 2 minutes of
  silence (AI_TIMEOUT_SECONDS) and is tried once more, so a hung request can't freeze a chat.
  P5-07: paste a client conversation (the Paste box knows Upwork and Fiverr message links) and get a reply card that answers
  the client's newest message; warning signs in their words show live and on the card. Plan and Add image are for posts only.
  P5-08: Fiverr orders by paste (due time, revisions, reminders, delivery messages); the Checker's notes for you ("Note for you: …")
  show on the card without failing a draft whose text is right.
  P5-09 (clients store) skipped by Muneer's choice. P5-10: the Freelance page (Upwork and Fiverr tabs): orders to deliver with
  Mark delivered / completed / cancelled and "Write delivery message", drafts waiting, scored jobs with "Write a proposal"
  (uses the saved post, no new paste) and Skip, and finished orders.
- **v7.8 (2026-10-16):** Muneer's choice: API posting (Phase 3) and Gmail (Phase 4) wait; posting stays copy and paste for now. Next is
  Phase 5 (Freelance) by paste: job posts and client messages you paste are scored and answered; the email parts follow after Gmail.
- **v7.7 (2026-10-16):** P3-01 sender base: the Safety Guard (code) checks every send (rule and mode, your own OK where needed, pause,
  exactly the approved text, hard limits, no keys/tokens/passwords/placeholders, a daily limit of 5 API posts per platform). Each send is claimed
  once and never retried by itself: "failed" stays approved for a retry by hand, "unclear" (or a send cut off by a restart) becomes "check manually".
  Drafts become API items only when their platform is connected; FAKE_AI mode has a fake Facebook Page to try it safely.
- **v7.6 (2026-10-16):** Phase 2b built: news agents with 26 verified official sources, a code fact guard (links and dates from real articles only; invented
  items, old stories and made-up numbers removed), rankings from Artificial Analysis's API (optional free key), morning digests, a News page, and news
  questions in chat and live calls. xAI, Qwen and Arena's leaderboard can't be read without a browser, so they're not used.
- **v7.5 (2026-10-15):** Phase 2 built: Social Media Manager with an idea list, images on drafts (Instagram waits for one), style memory,
  the Social page and planned posts (the scheduler now checks every minute, so reminders are on time).
- **v7.4 (2026-10-15):** mode menu like Claude's (section 8): Auto, Manual and a new Plan mode, with Pause everything in the same menu.
  The writing team's Checker uses the strong model (the small one flagged true profile facts as invented in a live test). Writing-team steps show live in the chat and in Show work.
- **v7.3 (2026-10-15):** added phase 2b, the news agents (section 6.4): the AI News Agent and the Social News Agent (Pakistan), reading official RSS feeds and pages, with a daily digest.
- **v7.2 (2026-10-15):** voice: gpt-4o-transcribe for speech-to-text after the Urdu test (section 14b); spoken replies stream.
- **v7.1 (2026-10-14):** web search moved to a small web-researcher helper after live testing showed the built-in tool adds ~4,400 tokens to every message (a hello cost $0.011; now $0.0023).
- **v7:** safe workflow (section 2): all browser automation removed (Browser Reader, Browser Executor, agent Chrome profile, Playwright). Added the Paste box and copy-and-paste items.
  API senders are plain code. Terminal locked to Ask. Memory only from your own words. "Always allow" hidden on outside-content items. LinkedIn comments come in by paste (no API).
  Noted that Upwork's job RSS is gone. Safety tests written with each task. The browser phase was removed; later phases were renumbered (0–8).
- **v6:** all open questions answered.
