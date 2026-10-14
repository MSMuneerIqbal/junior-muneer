# Junior Muneer: Project Plan (v7: safe workflow, no browser bots)

> Status: plan complete. Development starts with Phase 0 once you give the go-ahead.
>
> **What changed in v7:** no browser automation anywhere. Data comes from official APIs, email alerts, RSS or text you paste in.
> Anything without an official API is copy and paste: you post or submit it yourself in your normal browser.
> Also: the terminal is always Ask, memory is saved only from your own words, and safety tests are written with each task (see section 18).

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
LEVEL 2  SOCIAL MEDIA    FREELANCE       EMAIL AGENT     DEVELOPER AGENT     + future subagents
         MANAGER         MANAGER                         (GitHub, terminal)  (research, invoices...)
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

### 6.4 Adding new subagents later

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
Global switch: **Ask everything** · **Use my rules** · **Pause everything**.

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
proposal draft → you approve → **you copy it, open the job on Upwork, paste and press Submit.**

**E. Client messages (Upwork/Fiverr):** a notification email arrives → you paste the conversation (the email usually holds only part of it) →
reply draft (the Checker checks red lines) → you approve → **you copy and send it.**

**F. Fiverr orders:** deadlines and revisions tracked from notification emails (and pastes), reminders on the dashboard, delivery message drafts.

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
- API keys and tokens stay in the backend `.env` (never in Git). The browser page never sees them; live voice uses short-lived keys made by the backend
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
| **3. Official social APIs** | Facebook Page and Instagram professional (Meta), LinkedIn posts; comments on Page/IG posts through the API | An approved post goes live through the API, and a reply to a real comment is sent |
| **4. Email** | Email Agent: inbox summary, sorting, reply drafts, sending | You answer a real email from the dashboard |
| **5. Freelance** | Upwork job scoring from alert emails and pastes, proposals, Fiverr orders and messages, client replies: all copy and paste | A real proposal, drafted from a real job alert, is ready for you to paste into Upwork |
| **6. Developer Agent** | GitHub MCP (read, then approved actions through the Dev Executor), then the terminal (always Ask) | You ask "what changed in my repo this week?" and get a correct answer; an approved issue gets created |
| **7. Junior Muneer, full power** | Multi-step tasks across subagents, daily briefing, combined reports, smarter memory | "What happened today?" gives a full, correct summary |
| **8. WhatsApp + VPS** | Chat, voice notes and approvals on WhatsApp (in the same chat history); Docker, HTTPS, login, 24/7 server | It runs for a week without your PC |

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

- **v7.1 (2026-10-14):** web search moved to a small web-researcher helper after live testing showed the built-in tool adds ~4,400 tokens to every message (a hello cost $0.011; now $0.0023).
- **v7:** safe workflow (section 2): all browser automation removed (Browser Reader, Browser Executor, agent Chrome profile, Playwright). Added the Paste box and copy-and-paste items.
  API senders are plain code. Terminal locked to Ask. Memory only from your own words. "Always allow" hidden on outside-content items. LinkedIn comments come in by paste (no API).
  Noted that Upwork's job RSS is gone. Safety tests written with each task. The browser phase was removed; later phases were renumbered (0–8).
- **v6:** all open questions answered.
