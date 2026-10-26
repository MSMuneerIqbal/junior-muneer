# Junior Muneer: Task List

Built from [PLAN.md](PLAN.md) v7 (safe workflow, no browser bots). This is the working checklist: we build in this order, one task at a time.

## How we use this file

- **Status:** `[ ]` to do · `[~]` in progress · `[x]` done · `[-]` skipped (with a reason)
- **One task at a time, in order.** Each task: build → **tests for that task** → short demo or summary for you → commit.
- **Safety tests come with the task that builds the safety part**, never later. They run on every change.
- **Every phase ends with your acceptance test** (the "Phase done when" line). Then we push to GitHub and start the next phase.
- **Phases 0 and 1 are broken down in detail.** Later phases list their main tasks and get detailed when we reach them, using what we learned.
- **Plan changes go into PLAN.md first**, then this file is updated.

## Before we start

- [x] Python 3.13 installed
- [x] Node.js v22 installed
- [x] Private GitHub repo: https://github.com/MSMuneerIqbal/junior-muneer
- [ ] **You:** create an OpenAI API key and paste it into `backend/.env` yourself (task P0-02 creates the file)
- [ ] **You:** set a monthly spending limit in your OpenAI account settings

## Live checks with the real OpenAI key

Built and tested with a fake AI, then checked with the real key on 2026-10-14 (all passed):

- [x] **P0-06:** `python -m junior.agent "How are you?"`, the same in Urdu, and `python -m junior.agent "What's new in Pakistan today?"` (web search)
- [x] **P1-07 (you):** a 5-minute live call in English and one in Urdu; both should show in the sidebar with 📞, a transcript and a cost.
- [x] **P1-03 (you):** send a voice message in Urdu and one in English; listen to his spoken answers, and try Marin, Cedar and Ash in Settings → Voice. Tell me which you like.
- [x] **P0-09:** tell him a fact in one chat ("my rate is $25/hr"), then ask about it in a new chat; press undo on a memory note

## Folder layout (created in P0-01)

```
junior-muneer/
├── backend/          Python: FastAPI, OpenAI Agents SDK, database, tests
├── frontend/         Next.js dashboard
├── agents/           One file per agent (personality, instructions, model, tools)
├── playbooks/        One expert file per platform (from phase 2)
├── prototype/        The early prototype, kept for reference only
├── data/             Database, backups, uploads (never in Git)
├── PLAN.md · TASK.md · README.md
└── start.bat         Starts everything with one double-click
```

---

## Phase 0: Foundation + text chat with Junior Muneer

**Phase done when:** you chat with Junior Muneer like a friend in English and Urdu, the answers stream live, and every chat is saved and shown in the sidebar.

### Setup

- [x] **P0-01 Reorganize the repo**
  - Create `backend/`, `frontend/`, `agents/`, `playbooks/`; move `junior/` to `prototype/`; update `.gitignore`.
  - *Done when:* the new folders exist and Git ignores `data/`, `.env`, `node_modules/` and `.venv/`.
- [x] **P0-02 Backend skeleton**
  - FastAPI app, settings loaded from `backend/.env` (with a `.env.example`), logging, `/health` endpoint, `requirements.txt`, virtual environment, pytest set up.
  - *Done when:* `http://127.0.0.1:8000/health` answers OK, and `pytest` runs.
- [x] **P0-03 Database**
  - SQLite with SQLAlchemy and Alembic (migrations, so the database can grow phase by phase without losing data).
  - Tables: `conversations`, `messages`, `memories`, `usage`, `audit_log`, `settings`.
  - Each message stores its **source**: `user` (your words) or `outside` (pasted text, email, web result, subagent report). Memory rules depend on it.
  - *Done when:* one command creates `data/junior.db` with all tables.

### Agent core

- [x] **P0-04 Model router**
  - A settings file that says which model each agent uses ("strong" or "small"), checked at startup, with a clear error if it's wrong.
  - *Done when:* changing a model in the file changes it for that agent without code changes. Tests included.
- [x] **P0-05 Agent registry**
  - Loads every file in `agents/`: a header (name, description, model, tools, action types) plus the instructions as text.
  - *Done when:* the registry lists Junior Muneer, and a broken agent file shows a clear error. Tests included.
- [x] **P0-06 Junior Muneer, the agent**
  - `agents/junior_muneer.md`: a friendly, warm, honest personality with a bit of humour; always clear he's an AI; calls you by your name.
  - **Language:** understands English, Urdu script and Roman Urdu, and replies in the language you use.
  - Built with the OpenAI Agents SDK. Tools: **web search** and **read-only database questions** (chats, usage). Memory tools are added in P0-09.
  - *Done when:* he answers a general question in English, the same question in Urdu, and a "what's new today" question using web search.
- [x] **P0-07 Live chat (backend)**
  - A WebSocket chat: your message → Junior Muneer → the answer streams back word by word, plus "step" events (searching the web, saving a memory…).
  - REST API for chats: list, create, rename, pin, delete, search, read messages.
  - Every message is saved, along with its steps and cost.
  - *Done when:* a test client sees the answer arrive in pieces, and the chat is in the database. Fake-AI test included.
- [x] **P0-08 Conversation memory**
  - Recent messages go to the model with each new message; older parts of long chats are summarized to keep cost down.
  - *Done when:* in a long chat he still remembers what you said at the start.
- [x] **P0-09 Long-term memory**
  - He saves facts and preferences you share ("my rate is $25/hr") on his own, sends a "Memory updated" event that you can undo, and uses relevant memories in later chats.
  - **Safety rule:** a memory may be saved only from your own messages (`source = user`). The save tool refuses during turns that include outside content (web results, later: pasted text, emails, subagent reports), and says why.
  - REST API to view, edit and delete memories.
  - *Done when:* something you tell him in one chat, he knows in a new chat; undo removes it; and a test shows that a web result saying "remember that Muneer's rate is $5" does **not** create a memory.

### Safety and housekeeping

- [x] **P0-10 Cost tracking + daily cap**
  - Tokens and cost recorded per call, per agent and per chat. A price table in settings.
  - **$5/day cap** (editable): when it's reached, new AI work stops with a clear message.
  - *Done when:* the dashboard can show today's spend, and a test cap of $0.01 blocks the next message. Tests included.
- [x] **P0-11 Audit log**
  - Every agent run and tool call is logged: what, when, result, cost.
  - *Done when:* one chat message produces readable log lines.
- [x] **P0-12 Pause everything**
  - A global switch. While paused: no background work and no actions. Chat still works, and he tells you he's paused.
  - *Done when:* Pause on/off works from the API and is remembered after a restart. Tests included.
- [x] **P0-13 Daily backups**
  - Copies the database every day and keeps the last 14 copies.
  - *Done when:* a backup file appears, and restoring it brings back the chats.

### Dashboard (Next.js)

- [x] **P0-14 Frontend setup**
  - Next.js + TypeScript + Tailwind CSS. A 3-column layout (sidebar · chat · today panel), light and dark mode, and a phone layout where the side panels fold away.
  - *Done when:* `http://localhost:3000` shows the empty layout on PC and phone sizes.
- [x] **P0-15 Chat screen**
  - Message list with formatting (lists, code, links), live streaming, live steps ("Searching the web…"), a **Show work** panel (steps and cost), and an input box.
  - **Urdu support:** right-to-left text displays correctly (`dir="auto"`), with a font that supports Urdu.
  - *Done when:* a full chat in English and Urdu looks right and streams smoothly.
- [x] **P0-16 Chat history sidebar**
  - All chats grouped by date (Today, Yesterday, Last week…), New chat, search, rename, pin, delete.
  - *Done when:* every action works and survives a page reload.
- [x] **P0-17 Today panel**
  - Today's spend, the Pause button, and placeholders for "Needs your OK" and Mode (these become real in phase 2).
  - *Done when:* the spend updates after each message and Pause works.
- [x] **P0-18 Memory page**
  - List, edit and delete what Junior Muneer remembers.
  - *Done when:* editing a memory changes his answers.
- [x] **P0-19 Activity page**
  - The audit log, newest first, filtered by type.
  - *Done when:* every chat's steps show up there.
- [x] **P0-20 Settings page (basic)**
  - Your name, language preference (English / Urdu / match me), time zone, daily cap, models per agent (view only for now).
  - *Done when:* changing the daily cap or the language takes effect.

### Finish

- [x] **P0-21 Full test run**
  - All backend tests from P0-02 to P0-20 pass with one command, plus a full chat flow with a **fake AI** (no cost).
  - Frontend: smoke test that the chat page loads and sends a message.
  - *Done when:* all tests pass with one command.
- [x] **P0-22 One-click start + README**
  - `start.bat` starts the backend and the dashboard together and opens the browser. README: setup steps for a new PC.
  - *Done when:* after a restart, double-clicking `start.bat` gets you chatting.
- [x] **P0-23 Your acceptance test + push**
  - You chat in English and Urdu, check history, memory, web search, spend and Pause. Then we push to GitHub.

---

## Phase 1: Voice (voice messages + live call)

**Phase done when:** you hold a 5-minute live call in English and one in Urdu, and both show in the chat history with full transcripts.

- [x] **P1-01 Voice messages: recording**
  - Hold the 🎙 button to record in the browser → upload → speech-to-text → it goes through the normal chat flow. The audio file is saved.
  - *Done when:* a spoken English and a spoken Urdu message both appear as correct text in the chat.
- [x] **P1-02 Spoken replies**
  - Text-to-speech for his answers. Settings: auto-play on/off, voice, speed.
  - *Done when:* he answers aloud in English and in Urdu.
- [x] **P1-03 Urdu voice test** (see PLAN.md 14b)
  - Compare the speech-to-text and voice options for Urdu, and pick the best by quality and cost. Results go into PLAN.md.
  - *Done when:* you're happy with how he sounds and understands you in Urdu.
- [x] **P1-04 Live call: backend**
  - The backend creates the call at OpenAI from the browser's WebRTC offer ("unified" set-up), so **no key ever reaches the browser**, then stays attached to the call.
  - The session is set up with Junior Muneer's personality, a summary of your memories, and tools: memory (same "only your words" rule), plus a bridge to ask the full Junior Muneer (for web search and later subagents).
  - *Done when:* a test call connects and he greets you in character.
- [x] **P1-05 Live call: screen**
  - The 📞 button opens a call view: talk hands-free, interrupt him, mute, end the call, see the live transcript.
  - *Done when:* a natural back-and-forth conversation works, including interruptions.
- [x] **P1-06 Calls in history + cost**
  - The full transcript is saved as a chat with a 📞 icon; voice messages get a 🎙 icon with playable audio. Cost per minute is tracked, with a daily live-call minutes limit.
  - *Done when:* the call shows in the sidebar, and its cost shows in Show work and the spend panel.
- [x] **P1-07 Tests + your acceptance test + push**

---

## Phase 2: Writing team, approvals + Paste

**Phase done when:** you approve 5 posts you'd really publish, and draft one comment from a pasted post.

Nothing is posted by the system in this phase: approved items are copy and paste (APIs come in phase 3).

- [x] **P2-01 Your profile** (drafted from your portfolio and GitHub; rates, audience and voice are yours to fill)
  - A Profile page: what you do, services, skills, rates, real projects and results, who you want to reach, your writing voice, things to avoid, hashtags, platforms you use.
  - It's the only source of facts for anything written about you. You fill it in (I'll help).
  - *Done when:* the writing team gets your profile as text, and an empty profile gives a clear "fill in your profile" message.
- [x] **P2-02 Playbooks**
  - `playbooks/linkedin.md`, `facebook.md`, `instagram.md`, `x.md`: structure, length, hashtags, tone, red lines. You can edit them.
  - *Done when:* each is loaded and checked at startup, and a broken one gives a clear error.
- [x] **P2-03 Permission rules**
  - Action types (e.g. `linkedin.post`, `facebook.page.post`, `gmail.send`), each Ask / Auto / Deny; locked types; "outside content always Ask"; a mode menu under the message box (Auto · Manual · Plan, plus Pause everything); "run at most once".
  - *Done when:* strict tests cover every rule, including locked types and outside content.
- [x] **P2-04 Approval queue**
  - Approval items (copy-and-paste or API), with status: waiting · approved · rejected · posted · check manually. Edits are kept.
  - Cards inside the chat and an Approvals page: Copy · Open platform · Edit · Mark as posted · Reject (API items: Approve · Always allow · Edit · Reject). "Needs your OK" and Mode in the Today panel become real.
  - *Done when:* approving in the chat updates the Approvals page and the other way round.
- [x] **P2-05 Paste box**
  - Paste text from any site (a post to comment on, a job post, a client message) with its platform and type. Saved as outside content: never followed as instructions, memory saving blocked, anything drafted from it goes to Ask.
  - *Done when:* a pasted post with hidden instructions doesn't change his behaviour, and a test proves it.
- [x] **P2-06 Writing team**
  - Writer, Checker (score out of 10, facts, voice, platform fit, red lines), Humanizer, plus the automatic AI-phrase checks from the prototype. Writer → Checker (sends back up to 2 times) → Humanizer → final check.
  - *Done when:* a draft comes back with a score, issues fixed, and every step visible in Show work.
- [x] **P2-07 Social Media Manager**
  - A subagent Junior Muneer calls for posts, comments on pasted posts, and content ideas. Drafts become approval cards.
  - *Done when:* "write a LinkedIn post about X" in chat gives an approval card with a checked draft.
- [x] **P2-08 Images**
  - Upload your own images and attach them to drafts; each draft comes with an image idea; Instagram drafts wait for an image.
- [x] **P2-09 Style memory**
  - Approved and posted texts become examples for future drafts on that platform.
- [x] **P2-10 Social page**
  - Drafts, ideas, planned and posted items per platform.
- [x] **P2-11 Planned posts**
  - Pick a day and time for a draft; the scheduler reminds you then (real posting comes in phase 3).
- [x] **P2-12 Tests + your acceptance test + push** (accepted 2026-10-15, after the "write about exactly my topic" fix)
  - Automated tests all pass (backend, and 30 end-to-end tests on desktop and phone).
  - **Your acceptance test** (about 20 minutes, a few cents). Start the app with `start.bat`, then:
    1. **Profile:** open Profile and check it's right (it's the only source of facts for every post).
    2. **Ideas:** in the chat, ask "Give me 5 LinkedIn post ideas for this week". Open **Social**: they're under Ideas.
    3. **Five posts:** use **Write it** on ideas (or ask "Write a LinkedIn post about …") until you have 5 drafts you'd really publish. Watch the team's steps; open **Show work** on one.
    4. **Fix and approve:** Edit any draft you'd change, add an image to one (🖼 Add image), plan one for tomorrow (📅 Plan), then **Copy** each, post it if you want, and **Mark as posted**. Posted texts become your style memory.
    5. **A comment:** copy a real LinkedIn post, press 📋 in the chat, paste it, and ask "Should I comment on this? If yes, write a short comment."
    6. **Modes:** switch the mode under the message box to **Plan** and ask for a post: he shows a plan and writes nothing. Switch back to **Auto**.
  - Tell me what felt wrong or slow; we fix it, then push and start Phase 2b.

## Phase 2b: News agents (AI news + Pakistan news)

**Phase done when:** "What's new in AI?" and "What's happening in Pakistan?" give correct, sourced summaries of the last 15 days, in chat and in a call.

Read-only: these agents never post or send anything. News pages are outside content.

- [x] **P2b-01 News sources + reader**
  - `news/sources.toml`: each source's name, feed or page address, and topic (AI or Pakistan). You can edit it.
  - A plain-HTTP reader for RSS, Atom and simple pages (time limits, size limits, no logins, no browser), keeping only the last 15 days and dropping duplicates.
  - Official sources only: the allowed list is the only thing read, and redirects to other sites are refused.
  - *Done when:* the sources file is checked at startup (a broken one gives a clear error), and tests with saved sample feeds pass without the internet.
- [x] **P2b-01b Fact guard (code, not AI)**
  - Every digest item must carry the link of an article actually fetched from an allowed source, with a date inside the 15 days; anything else is dropped. Sources that failed are listed.
  - *Done when:* a test where the AI invents an item, changes a link or adds an old story shows it removed, and a test with a non-official link shows it refused.
- [x] **P2b-02 AI News Agent** (`agents/ai_news_agent.md`)
  - Builds the digest: new models and releases · benchmarks and who's on top, by field (coding, reasoning, agents, voice, image and video, open models) · agents and tools · business moves. Every item has a date and a source link.
  - Answers questions from the digest; web search only for what the digest doesn't cover, and only from official sites first.
  - *Done when:* a digest from sample feeds has the right sections and links, and nothing older than 15 days.
- [x] **P2b-03 Social News Agent** (`agents/social_news_agent.md`)
  - Pakistan only: top stories · trending online (Google Trends Pakistan) · tech, internet and freelancing · economy that affects you. Newest first, neutral, no political opinions.
  - *Done when:* a digest from sample feeds has the right sections and links, and news from other countries is left out.
- [x] **P2b-04 Junior Muneer sends news questions to them**
  - Tools `ai_news` and `pakistan_news` in chat and live calls, chosen from the agents' descriptions. Each step shows in Show work; outside-content rules apply (no memory saving, no instructions followed).
  - *Done when:* "which AI model is best for coding right now?" goes to the AI News Agent and "what's trending in Pakistan?" to the Social News Agent, and a test proves a feed with hidden instructions changes nothing.
- [x] **P2b-05 Daily digest + News page**
  - The scheduler builds both digests each morning (on/off and time in Settings; skipped while paused or over the budget). A News page with AI and Pakistan tabs, a Refresh button, the date of each digest and its cost.
- [x] **P2b-06 Tests + your acceptance test + push** (accepted 2026-10-16)
  - Automated tests all pass (backend, and 36 end-to-end tests on desktop and phone).
  - **Your acceptance test** (about 10 minutes, a few cents). Start the app with `start.bat`, then:
    1. Open **News**: the AI and Pakistan digests should already be there (built at 07:30, or press "Build it now"). Open a few source links: each must go to the real article on the official site.
    2. In the chat ask **"What's new in AI?"** and **"Which AI model is best for coding right now?"** Open **Show work**: it should say "Asking the AI-News-Agent".
    3. Ask **"What's happening in Pakistan?"** and **"What's trending in Pakistan today?"**: answers name their sources (Dawn, Geo…) and stay neutral.
    4. In a **live call**, ask one AI and one Pakistan news question.
    5. Optional: get a free key at artificialanalysis.ai, add it to `backend/.env` as `ARTIFICIAL_ANALYSIS_API_KEY=...`, restart, and press Refresh on the AI tab to see live rankings.
  - Tell me anything wrong or missing; we fix it, then push and start Phase 3.

## Phase 3: Official social APIs (Meta + LinkedIn)

> **Paused (2026-10-16, Muneer's choice):** posting stays copy and paste for now; the API connections come later.
> Ready for then: P3-01 (the safe sender) and the P3-02 Facebook code with `connect.bat meta`.

**Phase done when:** an approved post goes live through the API, and a reply to a real comment is sent.

- [x] **P3-01** API sender base: plain code (no AI), sends the exact stored approved text, Safety Guard check first, "run at most once", "check manually" on unclear results. Fake-API tests
- [ ] **P3-02** Meta developer app (guide for you) → Facebook Page posting
  - **Built:** the Facebook Page sender (text, one image, several images; link to the post), `connect.bat meta`, and Settings → Connections. Waiting for your Meta app to try it for real.
  - **Your steps (about 15 minutes, free):**
    1. **A Facebook Page.** The API can't post to a personal profile. If you don't have a Page yet: facebook.com/pages/create (for example "Muneer Iqbal – AI Engineer").
    2. **A Meta developer account:** developers.facebook.com → Get started, with your Facebook login.
    3. **Create an app:** My Apps → Create app → name it "Junior Muneer" → use case **"Manage everything on your Page"**. If it asks for a business portfolio, you can skip it.
    4. **Permissions:** in the app, open that use case and make sure these are added: `pages_manage_posts`, `pages_read_engagement`, `pages_show_list` (for later: `pages_manage_engagement`, `instagram_basic`, `instagram_content_publish`, `instagram_manage_comments`). Keep the app in **Development** mode: as its admin you can use them on your own Page without Meta's review.
    5. **App ID and secret:** App settings → Basic → copy the App ID and the App secret ("Show"). Also turn on **Require App Secret** (App settings → Advanced); Junior Muneer always sends the secret's proof.
    6. **A token:** developers.facebook.com/tools/explorer → choose your app → "Get User Access Token" → tick the permissions above → Generate Access Token → log in, choose your Page, allow. Copy the token (it only lives an hour; the next step turns it into a lasting Page token).
    7. **Connect:** in the project folder run `connect.bat meta` and paste the App ID, the secret and the token (the secret and token are hidden while you paste), then pick your Page.
    8. **Restart** (`stop.bat`, `start.bat`) → Settings → Connections → Facebook Page shows **Connected** → press **Check**.
    9. **Try it:** ask Junior Muneer "Write a short Facebook post about …" → on the card press **Approve & post** → **View post ↗**.
  - Your secret and tokens stay in `backend/.env` (never in the browser or in Git). You can remove the app's access anytime: Facebook → Settings → Business integrations.
- [ ] **P3-03** Instagram professional posting (pick: Facebook-linked API or Instagram Login; temporary public image host)
- [ ] **P3-04** LinkedIn developer app (guide for you) → posts to your profile, with a 60-day reconnect warning
- [ ] **P3-05** Read comments on Page and Instagram posts through the Meta API → workflow C (replies, always Ask). LinkedIn, X and personal-profile comments come in by paste
- [ ] **P3-06** Scheduler now posts approved API items at their planned time
- [ ] **P3-07** Tests + your acceptance test + push

## Phase 4: Email

> **Waits with the other API work:** it needs a Google Cloud project for Gmail. Freelance (Phase 5) comes first, by copy and paste.

**Phase done when:** you answer a real email from the dashboard.

- [x] **P4-01** Google Cloud project + Gmail access (the Google sign-in from the Google extras; `gmail.readonly` and
  `gmail.compose` added 2026-10-19: use Connect again in Settings → Connections and tick Gmail)
- [x] **P4-02** Email Agent (`agents/email_sorter.md`, `junior/inbox.py`): every 5 minutes new inbox mail is sorted
  (client / freelance / work / study / money / security / personal / newsletter / promotion / social), one-line
  summary, scam check; Gmail's Promotions/Social/Forums tabs sorted without AI. Important ones go to WhatsApp; inside
  WhatsApp's 24-hour rule they wait for your next message. The first check only starts the clock.
- [x] **P4-03** Inbox page (filters, Check now, Read it / Reply / Open in Gmail); Settings → News: watch on/off,
  WhatsApp alerts on/off; important emails in the morning briefing
- [x] **P4-04** `gmail_search`, `gmail_read`, `gmail_draft` (new or reply, in the thread): a Gmail draft plus an
  approval card; the Gmail sender (`senders/gmail.py`) sends exactly the approved text only after Approve (dashboard
  or WhatsApp's Approve button, which now sends too). `gmail.send` Ask, `gmail.reply` locked Ask, Safety Guard
  (placeholders, keys) and the daily limit apply. Fake-API tests.
- [x] **P4-05** Upwork and Fiverr alert emails → tasks for the Freelance Manager *(built with P5-03)*
- [ ] **P4-06** Tests + your acceptance test + push

## Phase 5: Freelance (Upwork + Fiverr, copy and paste)

**Phase done when:** a real proposal, drafted from a real job post you paste, is ready for you to paste into Upwork, and a client message gets a reply draft that keeps Upwork's and Fiverr's rules.

> Built now by paste (no setup). The email parts (P5-01, P5-03) come after Gmail (Phase 4).

- [ ] **P5-01** You set up Upwork saved-search alerts and Fiverr email notifications to your Gmail (guide for you) *(after Phase 4)*
- [x] **P5-02** Upwork and Fiverr playbooks + red lines in the Checker and Safety Guard
- [x] **P5-03** Email parsers for Upwork job alerts and Fiverr order/message emails (raw email shown when parsing is unsure) *(after Phase 4)*
  - **Done 2026-10-20** (`junior/freelance/alerts.py`, `agents/freelance_reader.md`): the email watcher hands Upwork and
    Fiverr emails to code: client messages get scam checks and a WhatsApp alert ("paste the whole chat for a reply");
    job alerts are read, scored and saved (good ones alerted, with "write the proposal for job N"); Fiverr order emails
    become orders with reminders; anything unclear is shown as it is. Live on his 4 real Fiverr messages (13-17 Oct): all
    four are the fake-order scam and are flagged (two wordings found live and added). No Upwork job alerts in his Gmail
    yet: P5-01 first. Freelance paused by Muneer after this (2026-10-20): Phase 10 next.
- [x] **P5-04** Freelance Manager subagent
- [x] **P5-05** Job scoring from alert emails and pasted job posts (skill match, budget, client quality, scam signs) *(pasted posts done; alert emails come with P5-03)*
- [x] **P5-06** Proposal flow: draft → approve → Copy + Open job on Upwork → you paste and Submit → Mark as sent
- [x] **P5-07** Client messages (workflow E): you paste the conversation → reply draft → copy and send yourself
- [x] **P5-08** Fiverr orders: deadlines, revisions, reminders, delivery message drafts
- [~] **P5-09** Clients and contacts store *(skipped: Muneer doesn't need a clients list)*
- [x] **P5-10** Freelance page
- [x] **P5-11** Tests + your acceptance test + push *(accepted 2026-10-16; P5-01 and P5-03 wait for Gmail)*

## Phase 6: Developer Agent (GitHub + terminal)

> **Paused by Muneer (2026-10-17):** "skip github and continue with phase 7". P6-01 is done; the in-app Connect GitHub
> waits for the OAuth App Client ID. P6-02 to P6-06 come later.

**Phase done when:** "What changed in my repo this week?" gets a correct answer, and an approved issue gets created.

- [x] **P6-01** GitHub fine-grained token (guide for you) + the GitHub MCP server in read-only mode
  - **Done 2026-10-17 with your GitHub CLI login** (`connect.bat github` → "Use that login? Y"): the token stays in
    Windows' store and is asked from `gh` when needed; `.env` only says `GITHUB_AUTH=gh`. Live: GitHub's read-only
    MCP server answered as @MSMuneerIqbal and listed your commits; 25 reading tools get through, nothing that writes.
    (A fine-grained token, below, is the other way, and safer: it can be limited to read-only.)
  - **Connect GitHub in the app (for everyone who uses it):** Settings → Connections → GitHub → **Connect GitHub**:
    the app shows a code, you approve on github.com, done. Each person's token is encrypted in the database (key in
    `data/secret.key`), never sent to the browser, and **Disconnect** forgets it. Read-only stays enforced by our code.
    **Your one-time step as the app's owner (2 minutes, free):**
    1. github.com → your picture → **Settings** → **Developer settings** → **OAuth Apps** → **New OAuth App**.
    2. Application name `Junior Muneer`; Homepage URL `http://localhost:3000`; Authorization callback URL
       `http://localhost:3000` (device login doesn't use it, but GitHub asks for one).
    3. **Register application**, then tick **Enable Device Flow** and press **Update application**.
    4. Copy the **Client ID** (not a secret; no client secret is needed) and send it to me, or add
       `GITHUB_CLIENT_ID=...` to `backend/.env` and restart.
  - **Built:** `connect.bat github` (checks the token with GitHub before saving it in `backend/.env`), GitHub in
    Settings → Connections with a Check button, and the read-only GitHub MCP server for the Developer Agent (GitHub's
    `/readonly` endpoint, plus code that only lets through tools that read). Waiting for your token to try it for real.
  - **Your steps (about 5 minutes, free):**
    1. github.com → your picture → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
    2. Name: `Junior Muneer`. Expiration: **90 days** (Settings → Connections shows when it ends). Resource owner: **MSMuneerIqbal**.
    3. Repository access: **All repositories** (or "Only select repositories" if you want to limit it).
    4. Repository permissions, all **Read-only**: **Contents**, **Issues**, **Pull requests** (Metadata is added by itself).
       Creating issues comes in P6-03: then you'll change Issues to "Read and write" on the same token.
    5. **Generate token** and copy it (it starts with `github_pat_`; GitHub shows it once).
    6. In the project folder run `connect.bat github`, paste it (it stays hidden), then restart (stop.bat, start.bat).
    7. Settings → Connections → GitHub → **Check**: it should say "Connected as @MSMuneerIqbal".
- [ ] **P6-02** Developer Agent: repo summaries, issue and PR reading, code review, drafts
- [ ] **P6-03** Dev Executor: GitHub write actions through the permission rules (merge and `main` locked to Ask; deletes denied). Tests included
- [ ] **P6-04** GitHub playbook (commit messages, PR descriptions, branch names)
- [-] **P6-05** Terminal runner: moved to Phase 9 (P9-05), where it works in your allowed folders
- [ ] **P6-06** Tests + your acceptance test + push

## Phase 7: Junior Muneer, full power

**Phase done when:** "What happened today?" gives a full, correct summary.

- [x] **P7-01** Multi-step tasks across several subagents, with progress shown in the chat *(a live checklist, like Claude's to-do list; parts run together)*
- [x] **P7-02** Long tasks run in the background and post their results to the chat *("I'm on it", keep chatting; the result and its cards appear in the same chat)*
- [x] **P7-03** Daily briefing and "what happened today" reports *(facts from the database only; ☀ briefing each morning, Settings → News)*
- [x] **P7-04** Smarter memory: better recall, automatic tidy-up of old memories *(dates, recall beyond 100, weekly tidy-up that archives with Restore)*
- [x] **P7-05** Optional: RSS reader for news and blogs you follow *(News → Your feeds; read every 3 hours, no AI)*
- [x] **P7-06** Tests + your acceptance test + push *(accepted 2026-10-18)*

## Phase 8: WhatsApp + VPS (24/7)

**Phase done when:** it runs for a week without your PC.

- [x] **P8-01** Docker setup for the backend and the dashboard
  - `backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml` (backend + dashboard + Caddy), `Caddyfile`
    (HTTPS by itself, a login in front of everything, `/api` and `/ws` to the backend), `deploy.env.example`,
    `.dockerignore` (keys and data never go into an image). The dashboard's server build uses its own address for the API
    and the chat. Docker isn't on your PC, so the first real build happens on the server (P8-02).
- [ ] **P8-02** VPS setup, HTTPS, dashboard login
  - **Your steps:**
    1. **A server:** a small Ubuntu 24.04 VPS with 2 GB of memory is enough (Hetzner CX22 about €4.50 a month, or
       DigitalOcean / Contabo about $5–6). Pick the region closest to you; note its IP address.
    2. **An address:** a domain or subdomain you own (an "A record" pointing to the server's IP), or a free one from
       duckdns.org. Caddy needs it for HTTPS.
    3. Send me the address and tell me how you'll give me access (we'll set up an SSH key together; never send a password
       in chat). Then I install Docker, copy the app, set the login and start it.
- [ ] **P8-03** Move data and settings; reconnect the API logins (Meta, LinkedIn, Gmail) on the server
- [x] **P8-04** WhatsApp Business API (separate phone number): chat, voice notes and approvals, saved in the same chat history
  - **Built (before the server, by your choice):** chat and voice notes on WhatsApp, answered in a WhatsApp chat in the same
    history (🟢 in the chat list); drafts come with buttons (Posted ✓ or Approve, and Reject); background results are sent
    there too. Only your own number is answered, only messages signed by Meta are accepted, and from outside addresses only
    the webhook answers (the rest of the app stays private even with a tunnel). `connect.bat whatsapp`, Settings → Connections.
  - **Your steps to try it on your PC (about 15 minutes, free; Meta gives a free test number):**
    1. developers.facebook.com → My Apps → your **Junior Muneer** app (or Create app → type **Business**) → **Add product:
       WhatsApp** → Set up.
    2. **WhatsApp → API Setup:** note the **Phone number ID** of the test number. Under **To**, add **your own WhatsApp
       number** and enter the code WhatsApp sends you.
    3. **A token that lasts:** business.facebook.com → Settings → Users → **System users** → Add (Admin) → **Generate
       token** for the Junior Muneer app with `whatsapp_business_messaging` and `whatsapp_business_management`, expiry
       **Never**. (The 24-hour token on the API Setup page also works for a first try.)
    4. In the project folder: `connect.bat whatsapp`, paste the token, the phone number ID and your number. It checks them
       with Meta and prints a **verify token**. Then restart (stop.bat, start.bat).
    5. **A tunnel** (a public https address for your PC): `winget install --id Cloudflare.cloudflared`, then
       `cloudflared tunnel --url http://localhost:8000`. It prints an address like `https://xxxx.trycloudflare.com`.
    6. **WhatsApp → Configuration → Webhook → Edit:** Callback URL `https://xxxx.trycloudflare.com/api/whatsapp/webhook`,
       the verify token from step 4 → **Verify and save**. Under **Webhook fields**, subscribe to **messages**.
    6b. **Publish the app** (Meta delivers real messages only to published apps; it needs a privacy policy link:
       ours is https://gist.github.com/MSMuneerIqbal/6f29706e4df8a63e823a2dbe41001180), and **subscribe the app to the
       WhatsApp account** (`POST /{WABA_ID}/subscribed_apps` with the token; done 2026-10-18 for WABA 2319962942090041).
    7. From your phone, send "Salam" to the test number on WhatsApp. Junior answers there, and the chat shows on the
       dashboard. (A quick tunnel's address changes each time you start it: repeat step 6 then. On the server it's fixed.)
  - **Done 2026-10-18:** a permanent System User token (expiry Never) and a fixed ngrok free domain (`NGROK_AUTHTOKEN` and
    `NGROK_DOMAIN` in backend/.env); `start.bat` starts the tunnel too, `stop.bat` stops it. Voice in = voice out; session
    settings (Settings → WhatsApp).
- [x] **Extra:** change settings by asking in chat or WhatsApp (`junior/settings_chat.py`: `my_settings`, `change_setting`).
  Everyday settings only (models, language, voice, WhatsApp chats, briefing, news, memory tidy-up); the daily limit, pause,
  call minutes, API posts and permissions stay on the Settings page. Needs your own words; blocked when a paste, web result
  or feed is in the turn, and in background work. Each change is in Activity.
- [x] **Extra:** email to yourself (before Phase 4), through Gmail's mail server with a Google App Password
  (`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`; `junior/mailer.py`). Always to your own address only.
  - **`email_me` tool:** "email me the AI news / this proposal / today's plan": anything, when you ask (your own words,
    at most 3 per message). Rule `gmail.to_self` (Auto; Ask or Deny stops it).
  - **Daily top 5 AI news:** the news agents rate each story 1-10; the News page shows the top 5 first (the rest under
    "More news"), and after the morning digest the AI top 5 is emailed (`junior/news/mail.py`, rule `gmail.news_to_self`,
    Settings → News: on/off and "Send it now").
  - **Your step:** turn on 2-Step Verification, make an App Password at https://myaccount.google.com/apppasswords
    (name it "Junior Muneer"), paste it after `GMAIL_APP_PASSWORD=` in backend/.env, restart. **Done 2026-10-18.**
- [x] **Extra: the gate** (`junior/gate.py`): every action a tool takes passes one check (Plan mode, your own words,
  your Ask/Auto/Deny rule, pause, at most 5 per message), is logged in Activity, and what's read is fenced.
  New apps (an API now, an MCP server later) plug into it.
- [x] **Extra: Google Docs, Sheets and Calendar** through Google's own APIs (Google's Workspace MCP servers need a paid
  Workspace account and a preview program; personal Gmail isn't supported there). `junior/google/`.
  - **Connect Google** (Settings → Connections): Google's consent page, PKCE, the login encrypted; asks only for files
    the app creates (`drive.file`), reading Docs and Sheets, calendar events, your email. Disconnect revokes it.
  - **Tools:** `google_doc_create` / `google_doc_read`, `google_sheet_create` (plain-text cells: no formulas from
    the web) / `google_sheet_read`, `calendar_add_event` (your calendar only, nobody invited) / `calendar_events`;
    today's events in the morning briefing. `send_to_me` (Gmail or WhatsApp, a Doc as a Word file) replaces `email_me`.
  - **Drive (added 2026-10-18):** `drive_search` finds your files by name (read-only `drive.readonly`), `send_to_me`
    sends any Drive file; files you send (WhatsApp documents and photos, 📎 in the chat; `junior/files.py`, kept in
    data/files) are saved with `drive_save` (new files only, folders made as needed; your own folders: the app may
    only add to folders it made, so it says so and uses "<name> (Junior Muneer)").
  - **Your steps (about 10 minutes):**
    1. https://console.cloud.google.com → new project "Junior Muneer".
    2. APIs & Services → Library: enable **Google Docs API**, **Google Sheets API**, **Google Calendar API**,
       **Google Drive API**.
    3. Google Auth Platform (OAuth consent screen): app name Junior Muneer, your email; Audience **External**; add your
       Gmail as a test user; then **Publish app** (In production), so the login doesn't expire after 7 days. Google
       will show "unverified app" when you connect: that's your own app, click Advanced → Go to Junior Muneer.
    4. Clients → Create client → **Web application**; Authorized redirect URI
       `http://127.0.0.1:8000/api/google/callback`. Copy the Client ID and Client secret into backend/.env
       (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`), restart, then Settings → Connections → **Connect Google**.
- [x] **Extra: reading files** (`junior/reading.py`): PDF, Word, Excel, CSV, text by code; photos by a vision model
  (`read_file` for files you send, `drive_read` / `drive_folder` for Drive). Drag-and-drop and paste to attach.
- [x] **Extra: Junior mode vs friend mode** (`agent/style.py`): "Junior …" = professional, no emojis (removed in code
  too); anything else = a relaxed friend, emojis fine. Easy English by default (Settings → language).
- [x] **Extra: the Polisher** (`writing/polish.py`, `agents/polisher.md`): emails, Google Docs and messages to you are
  rewritten to read like a careful human wrote them; AI signs found in code; every link, email and number must survive.
- [x] **Extra: dashboard look**: Settings as a full page with a grouped left menu (one section at a time, `#section`
  links), ChatGPT-style sidebar (New chat and features on top, Recents drop-down, you at the bottom), Inter font.
- [x] **Extra: DeepSeek** (2026-10-19): web search through DeepSeek's Search API (`websearch.py`; Settings → Search &
  photos; falls back to OpenAI), DeepSeek V4.1 Flash (= `deepseek-flash`) reads photos, spend by provider in Today.
- [x] **Extra: Gemini Live calls** (2026-10-20, `junior/gemini_live.py`): Settings → Live calls → **Voice engine**:
  OpenAI Realtime (unchanged), **Gemini 3.8 Live** or **Gemini 2.5 Flash Live** (`gemini-2.5-flash-native-audio-preview-12-2025`).
  The browser streams 16 kHz PCM to `/ws/call/gemini`; the backend runs the Gemini Live session (google-genai) with
  Junior's call personality + the Pakistani Urdu/English instruction, Google Search + Junior's tools, saves the chat,
  counts cost (audio and text priced separately) and minutes; his 24 kHz voice plays back, interruptions stop it.
  If a model refuses Google Search, our own web_search is used. Sessions last up to 15 minutes.
  - **Your step:** get a key at https://aistudio.google.com/apikey, paste it after `GEMINI_API_KEY=` in backend/.env,
    restart, then Settings → Live calls → Voice engine → Gemini.
- [x] **Extra: Gemini as the third chat provider** (2026-10-20): Gemini 3.8 Flash and 3.1 Flash-Lite (free tier) and
  Gemini 4 Argon (heavy) in Settings → Models, through Google's OpenAI-compatible endpoint (`[providers.gemini]` in
  models.toml), so every tool works. Gemini web search (Settings → Search & photos): Gemini 2.5 Flash with Google Search
  and URL reading (`websearch.gemini_search`). If DeepSeek or Gemini is rate-limited,
  down or silent before answering, OpenAI answers instead (Show work says so). Spend shows Gemini separately.
  - Live test on his free key (2026-10-20): 3.1 Flash-Lite chat + tools + Gemini search ✅ (~2 s); 2.5 Flash ✅;
    3.8 Flash takes 60-70 s per reply, so OpenAI steps in; 4 Argon is paid only. A free key has no Google Search on
    Gemini 3, so search uses 2.5 Flash, 2.5 Flash Live uses Google Search, and 3.8 Live uses Junior's web_search tool.
- [x] **Extra: Gemini voice messages** (2026-10-20): Settings → Voice → **Voice messages engine** (OpenAI or Gemini;
  `voice_engine`, also changeable from chat). With Gemini, Gemini 2.5 Flash hears your recordings (dashboard mic and
  WhatsApp voice notes; keeps English as English) and `gemini-2.5-flash-preview-tts` reads answers in the Gemini voice,
  turned into MP3 with `lameenc` (`voice.GeminiVoice`). Gemini voice cards in Settings have ▶ samples
  (`/api/voice/gemini-preview/{voice}.wav`). Live test: heard a WebM recording in ~6 s ($0.0002), spoke the answer in ~12 s.
- [ ] **P8-05** Monitoring and automatic restarts
- [ ] **P8-06** Your one-week test + push

## Phase 9: Your computer (local first, then the PC Helper)

> Planned 2026-10-20 (PLAN.md section 14c). Muneer: build and test it locally first, then the PC Helper, then use it
> with the VPS. **Every task is live-checked on his PC** (real files in a throwaway test folder, real commands) as well
> as tested.

**Phase done when:** from the dashboard and from WhatsApp you ask for a file on your PC and get it; an approved file
change, an approved delete (it's in the Recycle Bin) and an approved command all run; a refused one doesn't; and nothing
outside your allowed folders (or on the blocked list) can be read or changed.

- [x] **P9-01** Rules + Settings + the path guard (`junior/computer/paths.py`):
  - **Done 2026-10-20.** Live check on his PC: 14 real paths (project files allowed; `.env`, `data`, `secret.key`, AppData,
    `.claude`, Windows, Program Files, a `..` escape, Pictures and a network path refused; a typed Pictures path allowed,
    its parent not). Found while building: a typed path also unlocked the folders above it; fixed and tested.
  - new action types `computer.read` (Auto), `computer.write` (Ask), `computer.move` (Ask), `computer.delete` (Ask, to
    the Recycle Bin), `computer.run` (Ask, locked); `terminal.run` / `terminal.other` retired
  - Settings → Computer: on/off, allowed folders (first Desktop, Documents, Downloads), add/remove a folder
  - the path guard: real full paths only (`..`, links and shortcuts can't escape), inside an allowed folder or a path
    in your own words, never the blocked list (`.env`, keys, `.ssh`, browser data, Windows, Program Files, Junior's `data`)
  - safety tests for every way out; live check with real paths on his PC
- [x] **P9-02** Reading tools (`pc_list`, `pc_find`, `pc_read` in `junior/computer/tools.py`; tool group `computer_read`): `list_folder`, `find_files`, `read_file` (text, PDF, Word, Excel; size limits; fenced as data).
  Live check: list and read files in a test folder; a blocked file is refused
  - **Done 2026-10-20.** Live: in `Desktop\junior-pc-test` it listed 3 files (the `.env` hidden), found by name and by
    words, read a .txt (line numbers), a .docx and a .csv; `.env`, AppData and C:\Windows refused; a real search found 43 PDFs
    in Downloads. (The names are `pc_*` because `read_file` already reads files you send.)
- [x] **P9-03** Writing (`pc_write`, `pc_make_folder`, `junior/computer/sender.py`): `write_file`, `make_folder` as approval cards (the card shows the new text or the change; editable
  before Approve), carried out by the Computer sender (plain code, at most once); Auto runs at once. Live check
  - **Done 2026-10-20.** Live, through his running backend: a card created `shopping.txt` only after Approve; a change
    showed `+Sugar` on the card and the old file went to his real Recycle Bin; a folder was made; a file with an API key
    was stopped by the Safety Guard; Pictures was refused. Also: the path is checked again just before it runs (a link
    swapped in is caught), a file changed since the card isn't overwritten, at most 20 computer actions per message, and
    files keep their exact text (cards used to trim it).
- [x] **P9-04** Move and delete (`pc_move`, `pc_delete`): `move_file`, `delete_file` (to the Recycle Bin, `send2trash`). Live check: delete, then
  find it in the Recycle Bin and restore it
  - **Done 2026-10-20.** Live: renamed `shopping.txt`, moved it into `Clients\Acme`, deleted `Clients` (the card said
    "1 file, 20 bytes"), found it in the Recycle Bin and restored it with the file inside. Deleting an allowed folder itself
    (Desktop), a secret file, or something outside the folders is refused; a secret can't be moved out of hiding either.
- [x] **P9-05** Terminal (`pc_run`, `junior/computer/terminal.py`): `run_command` (PowerShell, in an allowed folder, 2-minute limit, output capped), always Ask
  (locked), dangerous commands refused in code, the result on the card and in the chat. Live check
  - **Done 2026-10-20.** Live, approved through his backend: `git status` + `git log` in the project, `python --version;
    node --version`, a `Format-Table` listing, Urdu output; `shutdown` and `type backend\.env` refused before any card.
    Found live: `Format-Table` was taken for formatting a disk; fixed and tested. The command runs without keys in its
    environment; an edited card is checked again before it runs. **Honest limit:** word checks can't catch every trick
    (a wildcard like `.e?v` could reach a secret), so commands stay locked to Ask: your Approve on the exact command is
    the real lock.
- [x] **P9-06** The Computer Agent (`agents/computer.md`, all the tools) and Junior's handoff to it, plus Junior's quick
  read-only tools. Live check: "what's in my Downloads?", "make notes.txt on my Desktop with ..."
  - **Done 2026-10-20.** Live with the real AI (Gemini 3.1 Flash-Lite for Junior): "what's in my Desktop\junior-pc-test?"
    (Junior looked himself, the secret hidden), "make todo.txt there with two lines" (Computer Agent → card → Approve →
    file), "run git log --oneline -3 in the project" (card → Approve → output). Found live: Junior made up
    `C:\Users\Muneer\...` instead of `Desktop\...` (the guard refused it); now paths are passed exactly as you wrote them
    and the Computer Agent is told your real user folder. Also: a waiting card is never called "created". Fake-AI
    trigger `pc list ...` / `pc write NAME: TEXT` for the e2e test.
- [x] **P9-07** WhatsApp: computer approvals with Approve/Reject buttons, results sent back, "send me that file" from
  your PC. Live check on WhatsApp
  - **Done 2026-10-20.** PC cards on WhatsApp say what they do ("Your PC: Create ...", the change, or "run this
    command in ..."), with Approve/Reject; Approve runs it and "Done on your PC: ..." comes back (command output too); a
    card approved on the dashboard also reports back on WhatsApp; `send_to_me` takes `pc_file` (25 MB, same guard; `.env`
    refused). Live: a real PC card and `plan.txt` from `Desktop\junior-pc-test` reached his WhatsApp; his tap on Approve
    is the last step (also in P9-08).
- [x] **P9-08** Your acceptance test (local), then push
  - **Accepted 2026-10-20** by Muneer (his Approve on the WhatsApp PC card created the file); pushed. The test folder
    `Desktop\junior-pc-test` went to the Recycle Bin.
- [ ] **P9-09** PC Helper (after the VPS is ready): a small program on your PC that connects out to the server, gets
  only approved jobs, runs them with the same guard, sends results; "your PC is offline" when it isn't running
- [ ] **P9-10** Acceptance test with the VPS + push

## Phase 10: Documents Agent, skills and task status

> Planned 2026-10-20 (PLAN.md section 14d). Muneer: "write this and don't start yet". Each task is live-checked.

**Phase done when:** a long research + document job (e.g. "make my China scholarship roadmap doc") starts in the
background while you keep chatting, "status?" says which step it's on and roughly how long is left, and the result
with its links arrives in the chat you asked from, WhatsApp included.

- [x] **P10-01** WhatsApp chat replies always reach the phone (also when the message came from the dashboard)
  - **Done 2026-10-20.** Live: a message typed on the dashboard in his WhatsApp chat was answered there and on his phone
    (his question on top). Other chats never go to WhatsApp.
- [x] **P10-02** Skills: `skills/*.md` (name, description, instructions), checked at startup, a `use_skill` tool that
  loads one, "make a skill for ..." from chat. Tests: a broken skill stops startup with a clear error
  - **Done 2026-10-20** (`junior/skills.py`, `skills/`). Live: "make a skill called repo_status ..." saved a good skill
    file; in a new chat "repo status for ...junior-muneer" loaded it and the Computer Agent made the two git command
    cards. Found live: the skill was loaded 4 times in one answer; now once per request.
- [x] **P10-02a** Skills library + Settings management (requested 2026-10-23): ten reviewed starter skills,
  Settings → Skills (search, add, edit, delete), validated persistent edits, agent scope checks and live task matching.
  **Done 2026-10-24.** Backend suite and focused desktop/phone E2E passed; real-model throwaway-data check
  matched and used skills for two ordinary requests ($0.042215 total). Next.js and matching ESLint config updated
  to 16.4.3 after audit found critical advisories in 16.4.0. Extends P10-02; does not complete P10-03 or P10-06.
- [x] **P10-03** The Documents & Research Agent (`agents/documents_agent.md`): research + Docs, Sheets, Markdown; Junior
  hands long jobs to it as background tasks by himself
  - **Done 2026-10-24.** `junior/documents/`: bounded research via the selected search API, actual citation catalog,
    structured writing and an independent content checker; exports DOCX/XLSX/Markdown/PPTX. Google Docs/Sheets
    requests queue approval cards and use a guarded sender. Downloads return to the original chat; WhatsApp
    attachment delivery is covered with the fake service. No model-generated programs or arbitrary execution.
- [x] **P10-04** Task status: progress (step, done of planned, started), a time estimate from similar past tasks, a
  `task_status` tool ("status?"), a "Running now" list on the dashboard
  - **Done 2026-10-24.** Persistent progress, elapsed time and median estimates from similar completed tasks;
    cancellation, pause/Plan checks, restart interruption, per-task cost/time/retry limits in Settings. Provider
    calls have bounded output and conservative cost preflight; the daily cap also applies. External actions are
    never retried by the task. Final backend suite passed; full browser run: 92 passed, 14 skipped; final feature
    browser run: all 4 passed (desktop/phone, including saved task limits). TypeScript and ESLint passed.
- [x] **P10-04a** Local PowerPoint: researched, editable PPTX returned as a download and WhatsApp document. Requested
  2026-10-24 together with P10-03/04; no generated script or manual Python execution.
  - **Done 2026-10-24.** Real-model isolated check: ordinary NLP request automatically delegated and produced
    6 editable slides in ~94 seconds, $0.0593174 for the task ($0.0850729 including the chat turn), no retries on
    the successful check. Opened/exported with installed PowerPoint and inspected all 6 slides. Earlier live
    checks exposed and fixed reviewer/export-stage confusion and overstrict citation checks on unused fields.
    Backend restarted after a database backup; health and Documents Agent registration confirmed on port 8000.
  - **Follow-up live test 2026-10-24:** sent an NLP request through the running app in the WhatsApp chat.
    It generated 8 editable slides with source notes; Meta accepted the actual PowerPoint document message.
    ~86 seconds including sending; $0.061059484 including the chat reply. Phone delivery/read receipts were not checked.
- [x] **P10-04b** Class notes + folders (requested 2026-10-24): turn supplied text/images/PPTX/DOCX/PDF/TXT/Markdown
  into checked notes, auto-save with class date/title/course, reuse or create the named Notes folder, preserve source
  uploads, and find/read/edit/download/archive/restore from a Notes page. Local Markdown storage; existing task limits.
  - **Done 2026-10-24.** Separate Notes Agent + editable `class_notes` skill in Settings. Folder matching is
    case-insensitive; IDs prevent repeated titles from overwriting notes. PPTX text/tables/charts/speaker notes,
    embedded images and scanned-PDF reading; explicit batch limits and bounded vision calls. Source text is data,
    never profile memory or authorization. Full backend suite passed; browser: 94 passed/14 skipped, Notes on desktop
    and phone visually inspected; final Notes-only browser checks: 2 passed after applying Markdown formatting.
    TypeScript/ESLint passed. Real-model throwaway-data test saved NLP slides + a
    whiteboard photo to an existing folder in 66 seconds, $0.0530214 including chat; sources and negation preserved.
    Two successful real-model checks cost $0.0911926 total. No live WhatsApp note message was sent in these checks.
    Database backed up before the new migration; backend restarted and health, Notes/folder APIs, skill and agent
    registration checked on port 8000. Focused reading/provider and notes safety checks also passed after tightening
    model-price-aware vision bounds and shared retry handling.
- [x] **P10-04c** Exact document placement + ZIP delivery (requested 2026-10-24): copy real document bytes from
  chat/generated files, PC, Google Drive or saved notes into a specified PC/Drive folder; preserve source and create
  missing folders. ZIP local/Drive folders recursively and send the archive's private download link to the owner's
  WhatsApp through approvals. No redirected destinations, silent omissions or terminal scripts. Settings skill + tests.
  - **Done 2026-10-24.** `junior/transfers/`, place_document/zip_folder and `skills/file_transfer.md`. Copy from chat,
    generated files, PC, Google Drive or Notes; exact PC/Drive destinations and reviewable immutable snapshots.
    Optional Google consent enables user-created Drive folders; normal connection scopes stay unchanged. A real
    application/zip upload was rejected by Meta, so ZIP delivery uses a private My Drive file link, never a renamed
    attachment or public sharing grant. Compound Drive/WhatsApp rules are checked before work and execution, and
    again between upload and sending. Interrupted/uncertain sends are not replayed; deliberate retries reuse the upload.
  - **Checks:** final full backend suite passed; unreadable-subfolder check also passed. Full browser run: 95 passed,
    14 skipped, one voice-test failure from a stale mobile button position. Fixed the test to wait for a stable locator;
    final desktop/phone transfer + voice run: all 6 passed. TypeScript/ESLint passed. Earlier backend failures were an
    outdated tool-scope assertion and a scheduler test using a changing clock; corrected and passed in the final full run.
  - **Real check (throwaway app data, synthetic PDF only):** natural prompts copied matching bytes into a new PC
    folder and Google Drive folder; local and Drive ZIPs reopened with matching PDF bytes; Meta accepted the actual
    private ZIP-link WhatsApp message. Two model turns: 35.7s/$0.0628076 and 19.5s/$0.0315434 ($0.094351 total AI cost;
    approval/API verification time additional). Phone delivery/read receipts and real broader Drive consent were not
    checked. Existing-folder consent, permissions, stale paths, collisions, nested folders, pagination, exports,
    partial failure/retry and Pause between stages are covered with controlled services. Backend backed up/restarted;
    health, archive permission and runtime skill registration confirmed. P10-05 remains next planned work.
- [x] **P10-04d** Fresh sessions + save-only file gallery + Drive sharing (requested 2026-10-25): /clear and cls
  reset WhatsApp/dashboard sessions without a model call; save/upload without content analysis; folder/file gallery
  for original uploads and notes, with previews/downloads; public-view/public-edit Drive links through approvals.
    - Old history/summary is deleted and a distinct session created; pending background work/unsent approvals are
      cancelled. Saved files/notes/profile memory and cost accounting survive. Exact commands only; pasted/quoted
      commands cannot clear a session. A foreground reply must finish before its session is cleared.
    - Original uploads and generated artifacts have folder/archive metadata; internal transfer snapshots are hidden.
      Notes shows folders and file cards (TXT/MD/Word/PPTX/PDF/images), selected-file previews, upload/download,
      rename/move/archive and Drive controls. Raw text saves preserve exact text. Save-only tools refuse AI reading.
    - Public sharing uses the separate google.drive.share Ask rule; cards state reader/writer, compound actions
      honor all permissions. Successful creation IDs survive unclear sharing for a deliberate retry without copies.
      Muneer's live new-save default is reader; new installs default private. Existing private files are unchanged;
      share them explicitly. ZIP WhatsApp links keep their private access. Google policy may refuse public sharing.
    - Checked 2026-10-25: clean full backend **990 passed**; full browser **100 passed, 14 configured skips**;
      final folder-navigation/gallery/notes browser checks **6 passed** on desktop/phone; TypeScript and ESLint passed.
      Two old test setups updated for persisted approval records and the additional setting. Gallery screenshots reviewed.
      Real isolated model requests saved/uploaded a synthetic MD without reading: 7.1s + 11.0s, **$0.0622289** total.
      Actual Drive download matched original bytes; anyone-reader then anyone-writer permissions confirmed. Isolated
      /clear cost $0. No real WhatsApp chat was cleared. Live DB backed up/migrated; backend restarted, settings,
      file/folder endpoints, health and dashboard checked. P10-05 remains the next planned feature; no push/acceptance.
- [x] **P10-04e** Manual Notes folder menus + previous view (requested 2026-10-26): three-dot Rename/Delete,
  Save changes, confirmation with contents retained in Unfiled; preserve gallery filters/folder/scroll on Back,
  browser Back/Forward and reload.
    - Folder card/open-folder menus support keyboard navigation/Escape and native rename/delete dialogs. Confirmed
      deletion removes the folder and rehomes all active/archived notes/files in Unfiled; nonempty Unfiled uses
      Unfiled (2). Original bytes and external PC/Drive files are retained. Duplicate names/invalid paths/stale
      revisions are refused. Markdown mirrors follow changes; no recursive deletion. No AI/API-provider cost.
    - Gallery folder/search/date/archive/selection/pagination use URL state; Back restores the prior view and scroll,
      browser Back/Forward restores filters, reload preserves filters, and direct links fall back to the item's folder.
    - Checked 2026-10-26: full backend **995 passed**; TypeScript/ESLint and whitespace checks passed. Full browser
      **101 passed/14 skipped**, with one existing approval test timing out during a cold fake-AI draft. Its wait now
      allows 30s and the test 60s; final **10 desktop/phone checks passed** for approvals, folders, notes and gallery.
      Screenshots reviewed. Cases include rename/update, cancel/confirm delete, exact original bytes, archived
      content, stale changes, mirror failures, Back/Forward, reload, filters, scroll and keyboard menu access.
      Live DB backed up; backend restarted; health, folder revisions and dashboard checked. No real folder was deleted
      during testing; controlled data only. No push or phase acceptance claimed.
- [ ] **P10-05** Slides (Google Slides API, one more Google permission) and PDF export
- [ ] **P10-06** First skills: CV review, scholarship roadmap, research report, pitch deck, proposal
- [ ] **P10-07** Your acceptance test + push
