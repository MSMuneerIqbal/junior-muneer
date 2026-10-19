# Junior Muneer

Your personal AI assistant and friend. He chats in English and Urdu, remembers what you tell him, and works
for you: social posts, Upwork and Fiverr proposals, your Gmail, Google Docs, Sheets, Calendar and Drive, the news,
voice messages and live calls, on the dashboard and on WhatsApp.

- **Two modes.** Start a message with **"Junior …"** and he works like a professional junior (focused, no emojis).
  Anything else, and he's your friend: relaxed, jokes, emojis welcome.
- **You decide what goes out.** Every outgoing action follows Ask / Auto / Deny rules; emails and replies to other
  people wait for your Approve. No browser bots: data comes from official APIs, email or your paste.
- **Human writing.** Emails, docs and messages go through the **Polisher** (easy English, no AI signs, facts
  checked in code); social posts and proposals through the writing team.

The design is in [PLAN.md](PLAN.md); progress and set-up steps per feature are in [TASK.md](TASK.md).

## What he can do

| Area | What |
|---|---|
| **Chat** | Streaming chat, memory (only from your own words), web search, file reading, Show work on every answer |
| **Voice** | Voice messages (🎙), spoken answers, and **📞 live calls** with **OpenAI Realtime** or **Google Gemini Live** |
| **WhatsApp** | Text, voice notes (answered by voice), photos and documents; draft cards with Approve buttons; important-email alerts |
| **Social** | Writing team (Writer, Checker, Humanizer), Social Media Manager, ideas, planned posts, images on drafts |
| **Freelance** | Upwork job scoring and scam signs, proposals with screening answers, client replies, Fiverr orders and reminders |
| **Gmail** | Inbox watcher (sorts new mail, important ones to WhatsApp), read and search, drafts sent after Approve (or Auto for new emails) |
| **Google** | Docs and Sheets (create, read), Calendar (add, list, in the briefing), Drive (find, read, send to you, save files you send) |
| **News** | AI and Pakistan news from official sources only (fact guard in code), top 5 first, top 5 AI news by email each morning |
| **Every day** | Morning briefing, "what happened today?", background tasks, your own RSS feeds, weekly memory tidy-up |
| **Send to you** | "Email me / WhatsApp me this": text, Drive files, docs as Word or PDF |

## Models and costs (Settings)

| What | Choices |
|---|---|
| Chat model | OpenAI GPT-6 family, **DeepSeek V4.1 Flash** (fast, cheap, sees images) or DeepSeek V4 Pro |
| Web search | OpenAI (hosted search) or **DeepSeek Search API** (~$0.0008 a search) |
| Reading photos | OpenAI's small vision model or **DeepSeek V4.1 Flash** |
| Live calls | **OpenAI Realtime** (Natural ~$0.05/min, Economy ~$0.02/min), **Gemini 3.8 Live** or **Gemini 2.5 Flash Live** (~$0.02/min, free tier) |
| Voice messages | OpenAI transcribe and text-to-speech |

The **Today** panel shows today's spend by type, by provider (OpenAI, DeepSeek) and web search by engine, against
your daily cap. Every call to an AI is in **Activity**.

## Start it

Double-click **`start.bat`**. The first run sets everything up (a few minutes), then it opens the dashboard at
http://localhost:3000. It also starts the WhatsApp tunnel if one is set up. **`stop.bat`** stops everything.

Keys go in `backend\.env` (created on the first run; see `backend\.env.example`). You paste them yourself:

| Key | For |
|---|---|
| `OPENAI_API_KEY` | Chat, voice, OpenAI calls and search (needed) |
| `DEEPSEEK_API_KEY` | DeepSeek models, search and photos (optional) |
| `GEMINI_API_KEY` | Gemini Live calls (optional; aistudio.google.com/apikey) |
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
| Emails to other people | "Junior, email sara@x.com that…": a draft and a card; **Approve** sends it |
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
| `data/` | Database, backups, files you send (never in Git) |

## Voice notes

- The microphone works on this PC (`localhost`). From your phone it needs HTTPS, which comes with the server.
- Live calls have a daily minutes limit (Settings). Gemini Live sessions last up to 15 minutes each.
- The browser never gets an API key: OpenAI calls are set up by the backend, and Gemini calls stream through it.

## Privacy

Chats go to the AI you chose (OpenAI or DeepSeek), live calls to OpenAI or Google, searches to OpenAI or DeepSeek.
Everything else stays in `data\` on your PC. API keys live only in `backend\.env`, which is never committed.
