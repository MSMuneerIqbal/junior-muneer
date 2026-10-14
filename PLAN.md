# Junior Muneer: Project Plan (v6: all questions answered)

> Status: plan complete. Development starts with Phase 0 once you give the go-ahead.

## 1. Goal

**Junior Muneer** is your personal AI assistant and friend. You talk to him by text, voice messages or a live voice call.
He chats about anything and helps with your work. Through his specialist subagents, he manages your freelance work, social media and email on
**Upwork, Fiverr, LinkedIn, Facebook, Instagram, X and Gmail**, and helps with your code on **GitHub**.
He speaks **English and Urdu**.
He finds, reads, plans, drafts, checks and prepares the work. **You decide what goes out**, by approving items or by switching an
action type to Auto (section 7). He runs on your PC first (on any PC you choose), with a VPS (24/7) later.

## 2. Ground rules

1. **Permission rules decide every outgoing action:** Ask, Auto or Deny, like Claude's permission modes (section 7).
2. **Outside text is data, not instructions.** Job posts, client messages, emails, comments, web pages and web search results can contain hidden instructions ("prompt injection"). Agents never follow them.
3. **Agents that read outside text cannot send anything.** Only the **Browser Executor**, the **Gmail sender** and the **Dev Executor** act. They perform exactly one approved action with the exact approved content, and they cannot write or change content themselves.
4. **Actions caused by outside content always go to Ask.** If an action comes from an email, web page, comment or message, it goes to your approval queue even when its type is set to Auto. Auto only applies to actions you set up yourself (your requests, your schedules).
5. **Every action runs at most once.** If the result is unclear (for example, the page didn't confirm), it's marked "check manually" instead of being retried. No double posts and no double messages.
6. The browser works **only on allowed sites**, with **daily limits**.
7. Agents use **only facts from your profile, your memory and your notes**. No invented clients, numbers or results.
8. **Everything is logged**, and the dashboard has one **"Pause everything"** button.

## 3. Tech stack

| Part | Choice | Notes |
|---|---|---|
| Language (backend) | Python 3.13 | Installed |
| Agent framework | **OpenAI Agents SDK** | Agents, agents-as-tools, guardrails, tracing, MCP, voice and realtime support |
| AI models | **OpenAI only** for now: a **strong** model for Junior Muneer and the writers, a **small** model for routine steps | Exact models picked from OpenAI's current list at build time |
| Voice | OpenAI **speech-to-text**, **text-to-speech** and **Realtime** (live voice) models, in **English and Urdu** | Section 6.2 |
| Web search | OpenAI's built-in web search tool, read-only | So Junior Muneer can answer questions about current events |
| Model router | One settings file: which model each agent uses | Claude or others can be added later without rewrites |
| Backend | **FastAPI** | REST API + **WebSocket** for live streaming chat and voice |
| Frontend | **Next.js (React)** | Chat, voice and live updates need a real app UI. You already know Next.js |
| Browser control | **Playwright MCP** + **one separate Chrome profile** for the agent | You log in once to every account in that profile. Node.js v22 is installed |
| Email | **Gmail API**: read, and send through the permission rules | Browser as backup |
| Official APIs | Meta Graph API (Facebook **Page**, Instagram **professional**), LinkedIn API | Everything else goes through the browser |
| GitHub | GitHub's official **MCP server** + a **fine-grained token** limited to the repos you choose | More reliable than Chrome, and safer than handing over your full GitHub login |
| Terminal (later) | A **command runner** limited to a projects folder and an allowed-commands list (`git`, `gh`, `npm`, `python`...) | For dev tasks the GitHub API can't do |
| Database | SQLite (one file) | Chats, memory, drafts, approvals, rules, clients, logs, costs |
| Scheduler | Built into the backend | Checks every few minutes, runs scheduled posts. Times are stored in UTC and shown in your time zone |
| Code storage | **Git** (private GitHub repo) | History of every change; easy to move to another PC or the VPS |
| Later | WhatsApp; Docker + VPS | Last phase |

## 4. Your accounts and how the agent reaches each one

| Account | Read | Post / send |
|---|---|---|
| Upwork | Email alerts + Browser Reader | Browser Executor (prepare proposals; messages through the permission rules) |
| Fiverr | Email alerts + Browser Reader | Browser Executor |
| LinkedIn (personal) | Browser Reader | LinkedIn API for your posts; Browser Executor for comments |
| Facebook **personal profile** | Browser Reader | **Browser Executor** (the API can't post to personal profiles) |
| Facebook **Page** | Meta API | **Meta API** |
| Instagram **personal** | Browser Reader | **Browser Executor** |
| Instagram **professional** | Meta API | **Meta API** (needs the account linked to your Facebook Page) |
| X | Browser Reader | **Browser Executor** |
| Gmail | Gmail API | Gmail API |
| GitHub | GitHub MCP (read-only tools) | Dev Executor through the GitHub MCP |

## 5. The team

### 5.1 Junior Muneer (orchestrator and friend) + subagents

You always talk to **Junior Muneer**, and he always answers you.

```
                       YOU (text · voice message · live call)
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
                          Browser Reader (read only) · Browser Executor (approved actions only)
                          Gmail sender · Dev Executor (approved GitHub/terminal actions)
                          Safety Guard (code, not AI)
```

**How Junior Muneer decides:**
- **Not related to any subagent** (general chat, advice, ideas, tech questions, "how was my week?") → **he answers you himself, like a friend.**
- **Needs a specialist** ("write a LinkedIn post", "any new client messages?") → he calls the right subagent(s), then answers you with the result.
- **Simple data question** ("how many proposals this week?") → he answers from the database. No subagent needed.

**His personality** (it lives in one editable file, `agents/junior_muneer.md`):
- friendly, warm, a bit of humour, simple language;
- speaks **English and Urdu**, both Urdu script and Roman Urdu, and replies in the language you use. Client work (posts, proposals, messages) stays in English unless you ask otherwise;
- calls you by your name and remembers what you tell him (section 10);
- honest: he says when he doesn't know, and pushes back when an idea is risky;
- always clear that he is an AI. No pretending to be human.

**Agent-as-tool, not handoff:** subagents work for Junior Muneer and report back to him; they never take over your chat.
So you get one clear answer in one voice, and he can combine several subagents ("What happened today?" = email + freelance + social).

**He cannot act on his own.** He has no click or send tools. Every action goes through a subagent, the approval queue and the permission rules.

**Long tasks don't block the chat.** If a subagent needs more than a few seconds, Junior Muneer says "I'm on it", keeps chatting with you,
and posts the result in the chat when it's ready.

### 5.2 The subagents and workers

| Agent | Job | Tools | Can it act? |
|---|---|---|---|
| **Junior Muneer** | Your friend and chief: chats, answers, plans, delegates | Memory, web search, database (read), subagents | No |
| **Social Media Manager** | Plans content, reads feeds and notifications, picks posts worth commenting on, watches comments on your posts | Browser Reader, Meta API (read) | No, drafts only |
| **Freelance Manager** | Finds and scores Upwork jobs, tracks Fiverr orders and deadlines, handles client conversations | Browser Reader, email (read) | No, drafts only |
| **Email Agent** | Reads, sorts and summarizes your inbox; drafts replies; turns Upwork/Fiverr alerts into tasks | Gmail API (read) | No, drafts only |
| **Developer Agent** | Your GitHub helper: lists repos, summarizes issues, PRs and commits, reviews code, drafts issues, PR descriptions and commit messages. Later it runs allowed terminal commands in your projects folder | GitHub MCP (read-only tools) | No, it drafts and plans; the Dev Executor runs approved actions |
| **Dev Executor** | Runs **one approved** GitHub action (create an issue, push a branch...) or terminal command, exactly as approved | GitHub MCP (write tools), terminal (later) | **Yes, approved items only** |
| **Writer** | Writes posts, comments, proposals, messages and emails, using the platform's playbook | None | No |
| **Checker** | Checks facts, voice, platform rules and red lines, then gives a score out of 10 | None | No |
| **Humanizer** | Rewrites in simple, natural English | None | No |
| **Browser Reader** | Opens pages and reads them as text. It can navigate and scroll, but cannot type, click buttons that change anything, or submit | Playwright MCP (read-only tools) | No |
| **Browser Executor** (computer-use) | Performs **one approved action** with the exact approved text (post, comment, message, fill in a form), then takes a screenshot and confirms the result. It can't change the text | Playwright MCP (full) | **Yes, approved items only** |
| **Safety Guard** | A rule check, not AI. It runs before every action and blocks anything that breaks a red line, a limit, the budget or the allowed-sites list. It also checks that the text being sent is exactly the approved text | n/a | It can block |

**Computer use:** browser control first (it covers every account above). Desktop-app control comes later, only if a real need appears.

### 5.3 Two ways work starts

1. **You ask Junior Muneer** (text, voice, live call; later WhatsApp).
2. **Triggers:** schedules and new emails go **straight to the right manager**. The results land in the dashboard, and Junior Muneer tells you about them when you ask, or greets you with them ("3 things need your OK").

### 5.4 Adding new subagents later

Every subagent is **one file** in `agents/`, the same idea as Claude Code subagents: name, description (Junior Muneer reads it to decide when to call),
instructions, model, tools, and action types (each follows the Ask / Auto / Deny rules).
An **agent registry** loads them all at startup. To add a new subagent you add one file, and Junior Muneer can use it straight away.

## 6. The dashboard (where you talk to Junior Muneer)

### 6.1 Layout

```
┌───────────────┬──────────────────────────────────────────────┬──────────────────┐
│ JUNIOR MUNEER │  Chat: "Weekly planning"            [📞 Live] │ TODAY            │
│               │                                              │ Mode: [Ask ▾]    │
│ + New chat    │  You: Any new Upwork jobs for me?            │ ⏸ Pause all      │
│ 🔍 Search     │                                              │                  │
│               │  Junior Muneer:                              │ Needs your OK: 3 │
│ Today         │  ▸ Asked Freelance Manager… (show work)      │  • LinkedIn post │
│  • Weekly pl… │  Found 4 good matches. The best one is a     │  • Fiverr reply  │
│  • LinkedIn … │  Next.js store for a shoe brand, $800…       │  • Email to Ali  │
│ Yesterday     │  ┌────────────────────────────────────────┐  │                  │
│  • Fiverr cl… │  │ Proposal draft · Upwork · 9/10         │  │ Inbox: 5 new     │
│  • 🎙 Voice…  │  │ [Approve] [Edit] [Reject]              │  │ Spend: $0.42     │
│ Last week     │  └────────────────────────────────────────┘  │                  │
│  • …          │                                              │ Alerts           │
│───────────────│  ┌──────────────────────────────────┐ 🎙 ➤   │  • Order due in  │
│ 💬 Chat       │  │ Message Junior Muneer…           │        │    6 hours       │
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

### 6.2 Three ways to talk

| Mode | How it works | Best for |
|---|---|---|
| **Text chat (live)** | Answers stream in word by word. While he works you see live steps ("Asking Freelance Manager…") | Most work |
| **Voice message** | Hold the 🎙 button and speak → your speech becomes text → Junior Muneer answers in text **and** reads it aloud (auto-play on/off) | Quick questions, hands busy |
| **Live call** | Press 📞 for a hands-free, real-time conversation, like a phone call. You can interrupt him. A live transcript shows on screen | Talking things through, planning |

- **Text and voice messages** use exactly the same Junior Muneer, with speech converted to text and back.
- **Live calls** use OpenAI's real-time voice model, set up with **the same personality, memory and tools**. For work that needs subagents
  he says "let me check", and the result arrives in the call and in the chat.
- **Approvals need a click, not your voice** (at least at first). Voice can be misheard, so during a call any approval card appears on screen for you to tap.
- **Settings:** voice choice, speaking speed, auto-play replies, language (**English / Urdu / match me**).
- **Cost:** text is cheapest, voice messages cost a little more, and live calls cost the most per minute. The dashboard shows spend per mode, and live calls have a daily minutes limit.

### 6.3 All chats in one place

- **Every conversation is saved:** text chats, voice messages (transcript + audio), live calls (full transcript) and, later, WhatsApp.
- The **sidebar lists all chats** by date, with a 🎙 / 📞 icon for voice and calls. You can search, rename, pin and delete them.
- Every answer has **"Show work"**: which subagents he asked, what they did, and the cost of that answer.
- Approval cards appear **inside the chat** and on the **Approvals** page. Both are the same item, so approving in one place updates the other.
- **Browser notifications** for new approvals and important alerts (until WhatsApp is added).

### 6.4 Pages

1. **Chat:** talk to Junior Muneer (above)
2. **Approvals:** every item waiting for your OK, with Approve · Approve + always allow · Edit · Reject
3. **Inbox:** email summaries and reply drafts
4. **Social:** posts, ideas, suggested comments and replies, per account
5. **Freelance:** ranked Upwork jobs, proposals, client conversations, Fiverr orders
6. **Memory:** what Junior Muneer remembers about you; view, edit or delete
7. **Activity:** the audit log of every read and action
8. **Settings:** permission rules, models per agent, voice, daily limits, budget cap, allowed sites, time zone, profile and playbooks

## 7. Permissions: Ask / Auto / Deny (like Claude)

Every outgoing action has a type, for example `linkedin.comment`, `facebook.page.post`, `gmail.send`, `fiverr.message.send`. Each type has one rule:

| Rule | What happens |
|---|---|
| **Ask** | It goes into your approval queue. Nothing happens until you click |
| **Auto** | It runs by itself; it is still logged, checked by the Safety Guard and limited per day |
| **Deny** | It never runs |

Approval buttons: **Approve · Approve + always allow this kind** (switches the rule to Auto; this button is hidden on locked types) **· Edit · Reject**.
Global switch: **Ask everything** · **Use my rules** · **Pause everything**.

| Action | Default | Can change to Auto? |
|---|---|---|
| Read pages, notifications, emails (allowed sites) | Auto | n/a |
| Create drafts, summaries, ideas; chat; web search | Auto | n/a |
| Post on your profiles and pages | Ask | Yes |
| Comment or reply on social media (max 10/day per platform) | Ask | Yes |
| Send email | Ask | Yes (not recommended) |
| **Upwork:** fill in the proposal form (you press Submit yourself) | Ask | **No, locked** |
| **Upwork / Fiverr:** send a message to a client | Ask | **No, locked** |
| **GitHub:** read repos, issues, PRs, code | Auto | n/a |
| **GitHub:** create an issue, comment, open a PR, push to a branch | Ask | Yes |
| **GitHub:** merge, push to `main`, create a release | Ask | **No, locked** |
| **GitHub:** delete a repo or branch, force-push, change visibility or settings | **Deny** | **No, locked** |
| **Terminal:** run an allowed command (e.g. `git status`, `npm test`) | Ask | Yes, read-only commands only |
| **Terminal:** any command outside the allowed list | **Deny** | **No, locked** |
| Anything not listed | Ask | Yes |
| Delete anything, payments, account settings, typing passwords | **Deny** | **No, locked** |

Remember ground rule 4: an action caused by outside content (email, comment, message, web page) **always goes to Ask**, even if its type is set to Auto.

## 8. Platform specialists = playbooks

Each platform gets a **playbook**: a file in `playbooks/` holding the expert knowledge for that platform. You can edit any playbook yourself.

| Platform | What its playbook covers | Red lines (the Safety Guard enforces these) |
|---|---|---|
| **Upwork** | Proposal structure (the first 2 lines show in the preview), how to judge a job (payment verified, hire rate, spend, reviews), connects, scam signs | No payment or contact outside Upwork before a contract; no fake experience; never move the chat to WhatsApp or Telegram |
| **Fiverr** | Fast replies (response time shows on your profile), custom offers, delivery and revisions, gig titles and tags | Never share email, phone or outside payment links in messages; no payment outside Fiverr |
| **LinkedIn** | Hook in the first lines, short paragraphs, comments that add a real point | No mass messages or connection spam |
| **Facebook** | Casual tone; Page vs personal profile; group rules | No spam in groups |
| **Instagram** | Visual first, short caption, 3 to 5 hashtags; personal vs professional | Every post needs an image or video |
| **X** | 280 characters, one clear point, replies | No reply spam |
| **Email** | Clear subjects, short polite replies, follow-ups | Never send to new addresses without Ask; never open unknown links or attachments on its own |
| **GitHub** | Clear commit messages, PR descriptions, issue templates, your branch naming | Never commit secrets (.env, keys); never force-push; never touch `main` without Ask |

## 9. Main workflows

**A. Your posts:** Social Media Manager plans → Writer → Checker (sends it back up to 2 times) → Humanizer → final check → permission rule → API or Browser Executor.
**Images:** you upload your own images; the team focuses on text. Each draft comes with an image idea to guide you. Instagram drafts wait
until you attach an image.

**B. Comments on others' posts:** the Browser Reader reads your feeds a few times a day → the Social Media Manager picks posts worth engaging with → the writing team drafts a useful comment → **Ask** (it comes from outside content) → the Browser Executor posts it. Daily limit applies.

**C. Replies on your own posts:** new comments are read → reply drafts → **Ask** → posted.

**D. Upwork jobs:** job alert emails + a Browser Reader pass over your saved searches → the Freelance Manager scores each job → proposal → **you approve** → the Browser Executor fills in the form → **you press Submit**.

**E. Client messages (Upwork/Fiverr):** a notification email arrives → task → the Browser Reader reads the conversation → reply draft (the Safety Guard checks red lines) → **you approve** → the Browser Executor sends it.

**F. Fiverr orders:** deadlines and revisions tracked, reminders on the dashboard, delivery message drafts.

**G. Email:** new mail is read → sorted and summarized in **Inbox** → reply drafts → **Ask** → sent through the Gmail API.

**H. Chat with Junior Muneer:** general chat is answered directly; work requests go to subagents; actions follow the rules; everything is saved in chat history.

**I. GitHub and dev work:** "What changed in my e-commerce repo this week?", "Open an issue for the checkout bug", "Write a PR description for my branch" →
the Developer Agent reads through the GitHub MCP → drafts → **Ask** → the Dev Executor does it. Terminal commands (later) follow the same path,
limited to your projects folder and the allowed-commands list.

## 10. Data and memory

- **Chat history:** every conversation and message (text, voice transcript + audio, call transcript) and the subagent steps behind each answer.
- **Long-term memory about you:** facts and preferences you share ("I prefer short proposals", "my rate is $25/hr"). Junior Muneer saves them on his own
  and shows a small "Memory updated" note in the chat, which you can undo. You can see, edit and delete everything on the Memory page.
- **Conversation memory:** recent messages go to the model; older parts of a long chat are summarized to save cost.
- `my_profile`: skills, services, rates, real projects and results, writing voice. The source of facts for all writing.
- `playbooks/`: one expert file per platform.
- **Style memory:** every text you approve becomes a style example for future drafts.
- **Clients and contacts:** name, platform or email, history, notes.
- **Approval queue, permission rules, audit log** (with a screenshot after each browser action), **usage and cost**.
- **Backups:** the data folder is copied automatically every day (the last 14 days are kept), because your chats and memory are valuable.

## 11. Safety, limits, cost and privacy

- The permission rules (section 7) and a Safety Guard check before every action
- An allowed-sites list for the browser, plus daily caps (for example 10 comments per platform, live-call minutes)
- **Budget:** no fixed monthly budget, because you'll watch usage yourself. A **safety cap of $5/day** (editable) stops runaway loops caused by bugs. Also set a monthly limit in your OpenAI account settings.
- **You log in to each site yourself** in the agent's Chrome profile. Agents never see or type passwords
- API keys stay in the backend `.env` (never in Git). The browser page never sees them; live voice uses short-lived keys made by the backend
- The dashboard is local-only on your PC; on the VPS it gets a login and HTTPS
- **Microphone note:** browsers allow the mic only on `localhost` or HTTPS. On your PC it works; **voice from your phone needs HTTPS**, so it comes with the VPS phase or a secure tunnel
- **Biggest costs:** the Browser Reader and Executor (page snapshots) and live calls (per minute). Both have caps and show on the dashboard
- **GitHub:** a **fine-grained token** that you create and paste into `.env`, limited to the repos you pick. It is not your main GitHub login,
  so the agent can never reach repos you didn't give it
- **Terminal:** only inside your projects folder, only allowed commands, every command logged; dangerous commands (delete, format, system changes) are always denied
- **Privacy:** chats, emails and client messages are sent to OpenAI for processing. By default OpenAI doesn't train on API data, but check its current data policy. Everything else stays in your local database

## 12. How we test

- **Automated tests for the safety parts:** the permission rules, the Safety Guard red lines, daily limits, "run at most once" and the budget cap. These must never break, so every change runs these tests.
- **Fake-AI tests for every workflow**, so we can test flows without spending money.
- **Your test at the end of each phase**, using the "done when" goal in the roadmap.

## 13. Roadmap

Each phase ends with you testing it. We only move on when it works for you.

| Phase | What you get | Done when |
|---|---|---|
| **0. Foundation + text chat** | Git repo, FastAPI backend, Next.js dashboard shell, OpenAI Agents SDK, model router, agent registry, **Junior Muneer text chat with live streaming**, chat history, memory, web search, audit log, cost tracking, $5/day cap, Pause, daily backups | You chat with Junior Muneer like a friend; the chats are saved and show in the sidebar |
| **1. Voice** | Voice messages (speak, and he answers aloud) + **live call** mode + transcripts saved in history, in English and Urdu | You hold a 5-minute live call in English and one in Urdu, and both show in the chat history |
| **2. Social writing team + approvals** | Social Media Manager (planner), Writer, Checker, Humanizer, playbooks, **permission rules (Ask/Auto/Deny), approval queue, approval cards in chat**, image upload; posts with copy and paste | You approve 5 posts you'd really publish |
| **3. Browser** | Browser Reader + Browser Executor with the agent's Chrome profile, Safety Guard. Read first, then actions on LinkedIn, Facebook personal, Instagram personal, X | It reads notifications on every account and posts one approved comment |
| **4. Official APIs** | Facebook Page and Instagram professional (Meta), LinkedIn posts | An approved post goes live through the API |
| **5. Email** | Email Agent: inbox summary, sorting, reply drafts, sending | You answer a real email from the dashboard |
| **6. Freelance** | Upwork job scoring + proposals (prepare mode), Fiverr messages and orders, client replies | A real proposal is prepared in the Upwork form for you to submit |
| **7. Developer Agent** | GitHub MCP (read, then approved actions through the Dev Executor), then the terminal with allowed commands | You ask "what changed in my repo this week?" and get a correct answer; an approved issue gets created |
| **8. Junior Muneer, full power** | Multi-step tasks across subagents, daily briefing, combined reports, smarter memory | "What happened today?" gives a full, correct summary |
| **9. WhatsApp + VPS** | Chat, voice notes and approvals on WhatsApp (in the same chat history); Docker, HTTPS, login, 24/7 server | It runs for a week without your PC |

Text chat (phase 0) and voice (phase 1) come first, as you chose. You can still change the order of the later phases.

**Existing code:** the backend parts already written (database, approval flow, platform rules, AI-phrase checks) get reused.
The HTML pages get replaced by the Next.js dashboard, and the AI part switches from the Claude SDK to the OpenAI Agents SDK.

**Needed from you:**
- **Phase 0:** an OpenAI API key, which you paste into `.env` yourself
- **Phase 3:** log in to your accounts in the agent's Chrome profile
- **Phase 4:** a Meta developer app and a LinkedIn developer app (I'll guide you). Notes:
  - **LinkedIn** API logins expire after about 60 days, so you reconnect with one click every 2 months.
  - The **Instagram** API needs the image at a public web address. While on your PC, we'll use a temporary image host; on the VPS it's simple.
- **Phase 5:** a Google Cloud project for Gmail access (I'll guide you; set up so Google doesn't log you out every 7 days)
- **Phase 7:** a GitHub fine-grained token for the repos you choose (I'll guide you)
- **Phase 9:** the official WhatsApp Business API needs **a separate phone number** (your personal WhatsApp number can't be used for both)

## 14. Using it on another PC

1. Get the code from your private Git repo.
2. Copy the `data/` folder (or a backup) to bring your chats, memory and settings.
3. Create `.env` with your API key.
4. Log in to your accounts once in the agent's Chrome profile on that PC. Browser logins don't move between PCs.

Run it on **one PC at a time**. Two copies running at once could do the same work twice.

## 15. Decisions (made)

| # | Question | Decision |
|---|---|---|
| 1 | Budget | No fixed budget, for personal use; $5/day safety cap (editable) |
| 2 | Facebook | Personal profile (browser) + Page (API) |
| 3 | Instagram | Personal (browser) + professional (API) |
| 4 | X | Browser |
| 5 | Permissions | Ask / Auto / Deny rules like Claude; Upwork/Fiverr sends locked to Ask; outside-content actions always Ask |
| 6 | Alerts | Dashboard (+ browser notifications) first, WhatsApp later |
| 7 | Gmail | Read + send, managed in the dashboard (Gmail API, browser as backup) |
| 8 | Provider | OpenAI only for now; others later through the model router |
| 9 | Name and role | **Junior Muneer**: a friend who answers anything himself and uses subagents only when needed |
| 10 | Talking | Text chat (live streaming), voice messages, live call; all chats saved and shown |
| 11 | Frontend | Next.js (React) dashboard + FastAPI backend |
| 12 | Live chat | A live voice call (hands-free, real-time); text chat also streams live |
| 13 | Language | English and Urdu (Urdu script and Roman Urdu); he replies in the language you use; client work stays in English |
| 14 | Phase order | Text chat first, then voice, then the rest |
| 15 | Images | You upload your own; the agents focus on text. No AI-made images |
| 16 | Code storage | Private GitHub repo: https://github.com/MSMuneerIqbal/junior-muneer |
| 17 | GitHub agent | A Developer Agent through GitHub's official MCP server + a fine-grained token; terminal later, limited to allowed commands |

## 16. Open questions

None. The plan is complete.

## 17. Known risks

- **Account restrictions:** permission rules, limits and official APIs lower the risk but don't remove it. Upwork and Fiverr are the most sensitive. Browser posting on personal profiles and X carries more risk than API posting.
- **Websites change their layout**, which can break browser steps. When the Browser Executor isn't sure, it stops and marks the item "check manually".
- **AI mistakes:** this is why Ask is the default and the checker exists.
- **Prompt injection through email, messages, comments and web results:** handled by ground rules 2 to 4. The risk is reduced, not zero, so locked types stay locked.
- **Costs:** the browser and live calls cost the most; both are capped.
- **Expiring connections:** LinkedIn (every 60 days) and some site logins need reconnecting. The dashboard warns you before they expire.
- **VPS move:** logins from a new server or country may trigger verification on Upwork and Fiverr.
- **Urdu voice quality:** speech recognition and the speaking voice may be weaker in Urdu than in English. We test this early in phase 1 and pick the best voice and model.
- **Terminal access** is powerful. It stays limited to one folder and an allowed-commands list, and dangerous commands are always denied.
