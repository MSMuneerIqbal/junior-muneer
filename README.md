# Junior Muneer

Your personal AI assistant and friend. He chats in English and Urdu, remembers what you tell him, and works
for you: social posts, Upwork and Fiverr proposals, your Gmail, Google Docs, Sheets, Calendar and Drive, files and
the terminal on your PC, the news, voice messages and live calls, on the dashboard and on WhatsApp.

- **Two modes.** Start a message with **"Junior …"** and he works like a professional junior (focused, no emojis).
  Anything else, and he's your friend: relaxed, jokes, emojis welcome.
- **You decide what goes out.** Every outgoing action follows Ask / Auto / Deny rules; emails and replies to other
  people wait for your Approve. Data comes through APIs, feeds, email or your paste. Controlled desktop/browser
  actions are being added in [Phase 11](PLAN.md#14h-system-actions-browser-and-learning-authorized-2026-10-26).
- **Human writing.** Emails, docs and messages go through the **Polisher** (easy English, no AI signs, facts
  checked in code); social posts and proposals through the writing team.

The design is in [PLAN.md](PLAN.md); progress and set-up steps per feature are in [TASK.md](TASK.md).

**PC jobs:** ask Junior to run a PowerShell command in the background in an allowed folder. Approve its card,
then open **Settings → Computer → PC jobs** to see the status, view output or press Stop. The default limit is
10 minutes (up to one hour when requested), with at most three jobs at once. Output checks here use no AI tokens.
Jobs stop on Pause, Computer off, Plan mode or backend shutdown; stopping keeps any partial changes.

**Desktop apps:** in **Settings → Computer → Desktop controls**, opt in and select supported apps. Open an app,
then ask Junior to inspect its window or type into an observed editor. A window preview and the exact action wait
for approval; typed text can be edited on the card. Desktop controls require an unlocked Windows PC. File creation
and saving still use the existing file/document tools.

**Browser:** in **Settings → Computer → Browser controls**, opt in and list exact website origins (for example
`https://example.com`; subdomains need separate entries). Ask Junior to open a page, then approve its navigation
card. The Computer Agent can read page snapshots and propose clicks, form text or a download. Every action waits
for approval; text can be edited on its card. A fresh snapshot is needed after each input. Settings shows the
connection, a page preview and Disconnect. Sessions use a temporary profile and close after 15 minutes, Pause,
Plan mode, Computer off or backend shutdown. Personal cookies are not loaded. Passwords, payments, private
networks, streaming media and websocket channels are blocked. Downloads up to 20 MB go to the Downloads gallery
without being opened. Required resource origins must also be listed; some websites will need manual use.

Install the matching browser once after Python dependencies: from `backend/`, run
`.venv\Scripts\python -m playwright install chromium` (Linux: `python -m playwright install --with-deps chromium`).
The Docker image includes it. Browser DOM snapshots and Settings polling use no model calls.

### Browser connection setup

For a compatible running Chrome/Edge instance, open **Settings → Computer → Browser controls → Connect a running
Chrome or Edge browser**. This is an explicit local debugging connection. Junior opens its own temporary context,
with the same website scopes and approvals. Its Disconnect closes that context and leaves the browser running.
Existing page contents and cookies are not imported. Debugging sessions expire after 15 minutes and old approval
cards cannot act after a reconnect. New WhatsApp, remote PC Helper and cloud-browser setup are separate work.

Start a dedicated debugging profile yourself in PowerShell (adjust the executable path for your installed Chrome
or Edge). These flags are checked on connection; incompatible/debugging-disabled browsers are refused:

```powershell
$juniorBrowserExe = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
& $juniorBrowserExe --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --user-data-dir="$env:LOCALAPPDATA\JuniorMuneerBrowser" --enable-automation --disable-quic --force-webrtc-ip-handling-policy=disable_non_proxied_udp --disable-features=WebTransport,WebUSB,WebBluetooth,Serial,DirectSockets --disable-background-networking --disable-extensions
```

Keep the debugging port local. Enable browser controls, save allowed website origins, then connect port **9222**
in Settings. Ask Junior to open the desired page and approve its navigation. Use connected service APIs or an
ordinary manual browser for signed-in account tasks: managed input excludes authentication/password/payment
fields, and personal-profile cookies are not reused. A disconnected debugging peer requires a fresh explicit
connection. Unattended authentication is not supported.

## What he can do

| Area | What |
|---|---|
| **Chat** | Streaming chat, memory (only from your own words), web search, file reading, Show work on every answer |
| **Voice** | Voice messages (🎙), spoken answers, and **📞 live calls** with **OpenAI Realtime** or **Google Gemini Live**; on a call he can do everything chat can (files, email, Docs, your PC) |
| **WhatsApp** | Text, voice notes (answered by voice), photos and documents; cards with Approve buttons (drafts, PC actions); important-email alerts; anything you type on the dashboard in your WhatsApp chat is answered on your phone too |
| **Social** | Writing team (Writer, Checker, Humanizer), Social Media Manager, ideas, planned posts, images on drafts |
| **Freelance** | Upwork job scoring and scam signs, proposals with screening answers, client replies, Fiverr orders and reminders; Upwork/Fiverr notification emails read by themselves (job alerts scored, orders tracked, client messages checked for scams) |
| **Gmail** | Inbox watcher (sorts new mail, important ones to WhatsApp), read and search, drafts sent after Approve (or Auto for new emails) |
| **Google** | Docs and Sheets (create, read), Calendar (add, list, in the briefing), Drive (find, read, send to you, save files you send) |
| **News** | AI and Pakistan news published within the last three days; Google discovery plus official feeds, verified dates/links, up to five previously undelivered AI stories by daily email |
| **Every day** | Morning briefing, "what happened today?", background tasks, your own RSS feeds, weekly memory tidy-up |
| **Send to you** | "Email me / WhatsApp me this": text, Drive files, files from your PC, docs as Word or PDF |
| **Your PC** | The **Computer Agent**: find, read, create, change, move and delete files (deletes go to the Recycle Bin) and run terminal commands, only in your allowed folders; changes and commands are cards you approve |
| **Skills** | Step-by-step instruction files in `skills/` for kinds of work ("make a skill for ..." from chat); agents load the one that fits |
| **Researched PowerPoint** | Give Junior a topic: he researches the internet and returns an editable `.pptx` with citations and speaker notes, as a download and a real WhatsApp document |
| **Documents & Research Agent** | Researched Word, Markdown and Excel files in the background; Google Docs/Sheets requests create approval cards; progress, cost, time limits and Stop are visible |
| **Class notes** | Turn class text, photos, slides or documents into saved notes with title, class date and course. Name a Notes folder: Junior reuses it or creates it. Search, read, edit, download, archive and restore on **Notes** |
| **File placement and ZIPs** | Copy an actual document to a PC drive/folder or Google Drive folder. ZIP local/Drive folders with subfolders; download the ZIP or approve sending its private Drive download link to your WhatsApp. Manage `file_transfer` in Settings → Skills |

For example: “Put this PDF in `D:\Classes\NLP`” or “Zip `D:\Classes\NLP` and send it to my WhatsApp.”
Source files are kept and existing documents are never overwritten. Missing destination folders are created as part
of the permitted action. If Google cannot access a folder you created, use **Settings → Connections → Allow existing
Drive folders** to grant optional broader Drive access; Junior does not redirect a save to a different folder.
The official WhatsApp API rejects ZIP uploads (verified with the connected account), so archives reach WhatsApp as
private Google Drive download links. Both Google and WhatsApp must be connected. No public sharing permission is added.
Folder archives support up to 500 entries, 100 MB of source material, a 20 MB ZIP and two minutes of preparation.

Send **`/clear`** or **`cls`** as the whole message on WhatsApp or the dashboard to delete that chat's history
and summary and start a fresh session. This command costs no AI tokens. Pending work and unsent approvals for
the old session are cancelled; your saved files, notes, profile and personal memories remain available.

**Notes** is also a file gallery: create/open folders, upload originals, search, rename, move, download or archive
TXT, Markdown, Word, PowerPoint, PDF and image files. Image thumbnails and selected-file previews are available.
Use a folder's **⋯** menu (on its card or beside its name) to rename it or delete it. Rename uses **Save changes**.
Deleting a folder asks for confirmation and keeps its files and notes, including archived items, in **Unfiled**.
The **Back** button and browser Back/Forward restore the previous folder, filters and scroll position; folder/search/
date/archive filters also survive a reload. These controls manage folders inside Junior's Notes library.
Individual files and saved notes also have **⋯ → Delete**, plus a Delete button in the open item. Confirming removes
the selected item from Junior and puts its managed local copy in the Recycle Bin. Other PC/Google Drive copies and
original sources of a deleted note remain available. Running tasks or uncertain sends must finish/be resolved first.
“Just save/upload this to …” preserves the original without AI reading, rewriting or summarizing it. Ask explicitly
to read or make notes when you want analysis. Raw text can also be saved as a TXT or MD file.

**Settings → Connections → Google → Default Drive link access** controls new document/note saves: private,
anyone with the link can view, or anyone with the link can edit. Public sharing has its own approval rule and the
card states the access. Muneer's requested default is public viewing; editing can be selected per file or requested
in chat. Existing private files stay private until you share them. Open a file in Notes and choose **Save to Drive**
or **Update Drive sharing**, or ask Junior to share its Drive link. ZIP delivery keeps its private-link behavior.

## Models and costs (Settings)

News rebuilds search Google through the configured Gemini key and read approved sources, including **AI News
(ainews.com)** through its publisher-filtered Google News RSS feed (its direct reader is currently blocked). Every publication must be
within the last 72 hours, including when an old saved digest is displayed or sent. The hourly chat cache saves repeated
search costs; Refresh forces a new build. Daily emails skip already delivered stories across restarts, and skip sending
when there is nothing new. Uncertain email delivery is held for checking, rather than automatically retried. Missing
or unavailable Google Search is shown in the digest's source problems; recent official feeds still work.

| What | Choices |
|---|---|
| Chat model | OpenAI GPT-6 family, **DeepSeek** (V4.1 Flash, V4 Pro) or **Google Gemini** (3.8 Flash, 3.1 Flash-Lite: free tier; 4 Argon: heavy). If DeepSeek or Gemini is busy or rate-limited, OpenAI answers |
| Web search | OpenAI (hosted search), **DeepSeek Search API** (~$0.0008 a search) or **Gemini** (Google Search + reading links, free tier) |
| Reading photos | OpenAI's small vision model or **DeepSeek V4.1 Flash** |
| Live calls | **OpenAI Realtime** (Natural ~$0.05/min, Economy ~$0.02/min), **Gemini 3.8 Live** or **Gemini 2.5 Flash Live** (~$0.02/min, free tier) |
| Voice messages | **OpenAI** or **Gemini** (Settings → Voice: the engine, plus the hearing and speaking model). Gemini's voice has 10 replies a day on a free key; then OpenAI speaks |

The **Today** panel shows today's spend by type, by provider (OpenAI, DeepSeek, Gemini) and web search by engine, against
your daily cap. Every call to an AI is in **Activity**.

## Start it

Double-click **`start.bat`**. The first run sets everything up (a few minutes), then it opens the dashboard at
http://localhost:3000. It also starts the WhatsApp tunnel if one is set up. **`stop.bat`** stops everything.

Keys go in `backend\.env` (created on the first run; see `backend\.env.example`). You paste them yourself:

| Key | For |
|---|---|
| `OPENAI_API_KEY` | Chat, voice, OpenAI calls and search (needed) |
| `DEEPSEEK_API_KEY` | DeepSeek models, search and photos (optional) |
| `GEMINI_API_KEY` | Gemini chat models, Gemini web search and Gemini Live calls (optional; aistudio.google.com/apikey) |
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | Emails to yourself (daily news, "email me") |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google Docs, Sheets, Calendar, Drive and Gmail (then Connect Google in Settings) |
| `WHATSAPP_*`, `META_APP_SECRET`, `NGROK_*` | WhatsApp (steps in TASK.md, P8-04) |

To try the dashboard without keys, set `FAKE_AI=true`: answers are fake and nothing is spent.

## Set it up on a new PC

1. Install **Python 3.13** (python.org, tick "Add to PATH") and **Node.js 22** (nodejs.org).
2. Get the code: `git clone https://github.com/MSMuneerIqbal/junior-muneer.git`
3. To bring your chats, memory and settings: copy the `data\` folder from the old PC
   (or a backup from `data\backups\`, renamed to `data\junior.db`).
4. Double-click `start.bat`, then paste your keys into `backend\.env` as above.

Run it on **one PC at a time**. A Docker set-up for a server (Caddy with HTTPS and a login) is in
`docker-compose.yml` and `deploy.env.example`.

## Everyday things

| What | How |
|---|---|
| Settings | Your name at the bottom of the sidebar → **Settings** (a full page with its own menu) |
| Work mode vs friend | Start with "Junior" for work; anything else is a chat with a friend |
| Talk instead of typing | Hold 🎙 next to Send (or tap to start, tap again to send) |
| Real-time voice conversation | **Live call** at the top of the chat; choose the engine in Settings → Live calls |
| Text from another site | 📋 **Paste box** (choose where it's from and what it is, then say what to do) |
| Attach a file | 📎, drag it onto the chat, or paste a screenshot |
| Change a setting by asking | "Junior, switch web search to DeepSeek", "reply in Urdu from now on" |
| Emails to other people | "Junior, email sara@x.com that…" (a file from your PC too): your Send-email rule decides: Ask = a card, **Approve** sends it; Auto = sent at once |
| Files and commands on your PC | "Junior, what's in my Downloads?", "run git status in ...": changes and commands are cards; **Settings → Computer** for your allowed folders |
| Make a skill | "Junior, make a skill for my weekly client report" or `/learn name \| when to use it \| workflow steps`; review and approve its card to save |
| Manage skills | **Settings → Skills**: add/edit/delete skills, script/reference/template text resources, preview saved versions and restore deleted skills; changes apply to the next message |
| Local commands | `/skills [search]`, `/reload-skills`, `/memory [search]` and `/clear` / `cls` work without model calls; credential text is excluded from skills and memory |
| Make a presentation | "Make 10 slides about NLP for beginners." Junior researches, checks and attaches the finished PowerPoint; 1–24 slides including cover/sources |
| Check a long task | Ask "status?" in its chat, or see its current step in the chat and **Running now & recent work** in the Today panel |
| Control background cost | **Settings → Background tasks**: allowance per task (default $0.50), time limit (600 seconds) and shared retry/revision limit (one). The daily cap still applies |
| Save a lecture | Attach your material and say: "Make class notes titled Introduction to NLP, date 2026-10-24, in folder NLP." The existing folder is reused; missing folders are created automatically |
| Revise from saved notes | "Find my NLP class notes" then "Explain tokenization from those notes." Or open **Notes** and filter by folder/date |
| Notes input limits | Up to 8 source files, 80,000 extracted characters and 8 visual readings per task. PDF: up to 120 pages; split larger batches. Supports PPTX, DOCX, PDF, images, TXT and MD; old PPT/DOC need conversion |
| See or edit what he remembers | **Memory** |
| See everything he did, with costs | **Activity** |
| Stop all background work and actions | **Pause everything** in the Today panel |
| Change his personality | Edit `agents\junior_muneer.md` |
| Backups | Automatic, daily, last 14 kept in `data\backups\` |
| Restore a backup | `stop.bat`, then in `backend\`: `.venv\Scripts\python -m junior.backup restore ..\data\backups\junior-YYYY-MM-DD.db` |
| Run all tests (no keys needed, nothing spent) | Double-click `test.bat` |

## Folders

| Folder | What's in it |
|---|---|
| `backend/` | Python: FastAPI, OpenAI Agents SDK, Google GenAI SDK, database (SQLite + Alembic), tests |
| `frontend/` | Next.js dashboard |
| `agents/` | One file per agent (personality, instructions, model, tools) + `models.toml` (models and prices) |
| `playbooks/` | One expert file per platform |
| `news/` | The official news sources |
| `skills/` | Skills: instructions for kinds of work, loaded when needed |
| `data/` | Database, backups, files you send (never in Git) |

## Voice notes

- The microphone works on this PC (`localhost`). From your phone it needs HTTPS, which comes with the server.
- Live calls have a daily minutes limit (Settings). Gemini Live sessions last up to 15 minutes each.
- The browser never gets an API key: OpenAI calls are set up by the backend, and Gemini calls stream through it.

## Privacy

Chats go to the AI you chose (OpenAI, DeepSeek or Gemini), live calls to OpenAI or Google, searches to OpenAI, DeepSeek
or Google. Everything else stays in `data\` on your PC. API keys live only in `backend\.env`, which is never committed.
On your PC, Junior can only reach your allowed folders; keys, passwords, `.env` files, `.ssh`, AppData and system
folders are always blocked, and terminal commands run without your keys.
## Reviewed local updates

Use `/update --check` in chat, or Settings → Advanced → **Check for updates**. Junior fetches only the
configured Git upstream and shows the exact revisions and changed-file summary. `/update --apply` prepares
an approval card; it does not install immediately. Reviews expire after 15 minutes. No model calls are used.

The Windows launcher in `start.bat` now supervises both servers. Stop existing servers normally before using
this launcher; it never adopts unrelated processes. Approved updates require a clean original Git checkout
(including untracked files). Junior will not stash, discard or commit local edits. This development checkout
currently has local handover files, so updating it will be refused until you decide how to save those files.

An update exports the pinned tracked source into `data/updates/releases/<revision>`, creates a separate venv,
installs `backend/requirements.lock` without dependency re-resolution and runs `pip check`, migrations against
a database copy, backend tests, locked dashboard installation, type/lint checks and a production build. Installs
and tests execute reviewed upstream code with your account's authority. They are isolated source copies, not a
security sandbox. The overall limit is 60 minutes, with no automatic retries; Pause/Plan/Stop cancels checks.

Before activation, the supervisor stops only its owned process trees, saves a SQLite backup and atomically
switches the active-release pointer. Requests are held during the switch. Failed health checks restore the old
database and release. Interrupted switches recover on the next supervised start; interrupted preparations do
not automatically rerun. Calls and jobs do not survive restart. Junior remains paused after success or rollback;
review Settings → Advanced and interrupted tasks before resuming. A result is also saved in the originating chat.
Original `.env`, uploads, notes and editable skills stay in their original locations. Keep the original checkout
and its environment; the launcher and rollback source use them. Three staged releases are retained; further
updates require local review/archiving, rather than silently deleting rollback copies. Windows-only local updater;
VPS/Docker deployment continues through the normal deployment process. No new WhatsApp integration is added.
