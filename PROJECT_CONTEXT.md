# Junior Muneer: project context

Last reviewed: **2026-10-27**, after cost/workflow acceptance (P11-08).

## Active continuation (2026-10-27)

2026-10-28: user reported browser debugging error and WhatsApp failure. Port 9222 had no listener; ordinary isolated
browser works without it. UI now labels the optional debugging connection and shows ready/no-page state. Focused
browser/WhatsApp backend and six desktop/phone UI checks passed. WhatsApp token metadata check succeeded; no ngrok
process or local 4040 listener. Auto approval review blocked starting tunnel due to policy; asked owner to open
start.bat. End-to-end incoming/outgoing remains unverified. App restarted at fd6c3ef; supervised backend healthy,
dashboard HTTP 200.

2026-10-28 browser follow-up: logs showed four pending approvals mislabeled refused, one outside scope and one
browser-off request; a real isolated session opened a page. Added opt-in `browser_sites=["*"]` for all public
websites, preserving private-network/proxy guards and locked approvals; Settings exposes the toggle. Pending
actions now log as pending. Focused browser/settings tests, real Chromium fixture in both scopes, TypeScript,
ESLint and six desktop/phone browser tests passed. Owner app restarted with uncommitted code, health/dashboard
working; existing exact-site setting retained. Full backend 1,244 passed; full UI 130 passed/14 skips before final
guidance changes. Do not claim Google Slides live verification.
Later user retry: approved cards 87/88 opened successfully; live snapshot showed website's tenant-not-configured
page (missing/inactive organization subdomain). Junior wrongly promised automatic reading after approval; navigation
does not resume the agent. The user's signed-in personal browser is isolated. Added truthful action-result and agent
guidance to ask for and take a snapshot on the next message. Final focused browser/agent tests and six UI tests passed;
real-model synthetic page read used snapshot, 10.8s/$0.0397723. Commit 4aba5c0 restarted: backend health at that
revision, supervised=true, dashboard HTTP 200. User asked for working URL. All-public scope is now on in owner settings.

Muneer asked to do the remaining work after Phase 11. P10-05 Google Slides/local PDF and P10-06 specialist skills
are complete. Questions about resuming paused integrations/new WhatsApp and VPS/domain
details were asked asynchronously; no answer recorded yet. Keep new WhatsApp deferred pending clarification.
Live local status shows GitHub configured/connected, Facebook unconnected, Instagram/LinkedIn not implemented,
Google saved connection with all current scopes (token freshness not checked in this follow-up). Docker CLI absent;
SSH exists, but no VPS/domain supplied. Do not claim account setup, publication, deployment or user acceptance.
P10-05 focused tests/static checks and real PDF layout checks passed. One real-model researched NLP PDF check
passed in 80.9 seconds, estimated $0.0925705, exactly five pages, throwaway chat/data with outgoing services off.
Full backend checkpoint: 1,238 passed. Final rebuilt UI: 28 passed/2 existing skips after fake slide-count and
old test isolation/timing fixes. Final documents recheck 33 passed; committed 3e47ba3. P10-06 skills and a Windows
supervisor transient file-lock retry committed 6105fe9. Full UI 128 passed/14 skips, Skills UI 4 passed; full backend
1,240 passed/one timing failure that passed isolated rerun. Real-model new-skill matching remains unverified.
Real code helper on synthetic repo proposed a correct fix behind TEST approval, 8.4s/$0.004656, no execution/apply.
Supervised restart verified: backend health reports 6105fe9, supervised=true, dashboard HTTP 200. Phase acceptance
and push remain pending.

## Purpose and owner

Muneer Iqbal is building his personal AI assistant, currently called **Junior Muneer**, to handle work he does
every day. On 2026-10-22 he asked to preserve project context for continued development toward a successful product.
The immediate scope remains his own assistant; public distribution, multiple users and monetization are undecided.

On 2026-10-26 he authorized a plan followed by tested steps for controlled PC/browser actions, reusable learning,
updates and code proposals. PLAN 14h / TASK Phase 11 record the scope; new WhatsApp integrations are deferred.
P11-01 managed local jobs, P11-02 desktop controls, P11-03 isolated browser and P11-04 browser connection are complete;
P11-05 learning/skills commands, P11-06 controlled updates, P11-07 code proposals and P11-08 cost/workflow
acceptance are complete. Commit `5f344c5` is running through the Windows supervisor: backend reports that revision,
dashboard returns HTTP 200 and /api/updates reports supervised=true (2026-10-27 07:40 PKT). Only verified legacy
backend/dashboard processes were stopped; the WhatsApp tunnel was preserved. Do not automatically start paused
phases or setup-dependent tasks; new WhatsApp work remains deferred.
Existing API providers remain. Browser control is opt-in under Settings → Computer, with exact website origins,
temporary profiles, locked-Ask actions and an authenticated proxy that pins public IPs. See junior/browser and TASK
for limits/checks. It does not open personal cookies, run page-supplied instructions or automatically open downloads.
P11-06 lives in junior/maintenance: source.py (bounded Git/export/atomic records), updates.py (review cards/API/
zero-cost reports/switch write guard), supervisor.py (owned processes, immutable releases, pinned installs/checks,
SQLite backup/rollback) and child.py (stdin ownership gate). start.bat launches the Windows supervisor; stop.bat
signals it before legacy stop handling. config honors JUNIOR_ENV_FILE so active releases use the original .env;
DATA_DIR and editable skills retain original locations. Never replace/stash the owner's dirty checkout. The
current handover files block live apply intentionally. Native synthetic release check is scripts/check_update_native.py;
final run passed after explicit SQLite handle closing. No real update was applied. Full backend/UI and final
checks are in TASK; one previous synthetic temporary fixture remains after automatic removal was blocked.
P11-07: maintenance/code.py stores bounded proposals/source manifests and controls TEST/APPLY/ROLLBACK senders;
code_tools.py delegates to agents/code_agent.md through existing provider/budget. Source tools are fenced/read-only;
all native execution needs a TEST approval with full-account warning, then a separate APPLY card after checks.
Source/target hashes, revision, policy/credential path guards and exact-byte backups protect reviews/local edits.
Advanced CodeSettings manages diffs/status/review cards. Tests use isolated Git source; opt-in scripts/check_code_model.py
verified one real-model proposal without executing/applying it. Full/final checks are in TASK. Deployed releases
stay immutable; sync the original development checkout locally before code proposals when its revision differs.
P11-08 extends documents/limits.py's bounded provider to typed chat and helpers, sharing cost/call caps across
delegation and fallback. Builder applies global response output limits; live calls retain existing minute/day
controls. Budget settings, /api/usage/limits and LimitSummary expose caps. Source proposal records include draft
cost/time; code preparation reserves a turn before awaiting export. Local commands/reset remain zero-model and
Usage survives /clear. Configured prices are estimates; in-flight/provider billing can differ. All final full
checks passed (1,223 backend, 124 UI/14 skips) plus one bounded real reply; no new providers/speech enabled.
Final feature commits: P11-05 `8d05820`, P11-06 `0484ac4`, P11-07 `6e6e3c6`, P11-08 `5f344c5`. They were not pushed.
Working tree still has the preexisting CLAUDE.md edit and untracked .agents/, AGENTS.md and this context file;
these were preserved unstaged and intentionally prevent applying an upstream update. Final native launch logs:
data/updates/launcher-20261027-074014.{out,err}.log plus backend.log/dashboard.log. No runtime update was applied.
One synthetic installer fixture remains in the temp directory after automated approval blocked recursive removal;
it contains no owner data. A combined restart command was also blocked; separate verified-process checks and
scoped stops succeeded, followed by the verified supervised start. No permission bypass or broad process kill.
P11-04 adds explicit owner connection to compatible local Chrome/Edge debugging ports, in a newly created proxied
context only. It validates endpoint/launch flags and preserves the peer/default pages. README has setup; authentication
uses existing service APIs or ordinary manual browsing, with no personal-cookie import. Session generations bind cards
across reconnects. hosts.py now checks browser Origin as well as Host, including unsafe cross-site requests/WebSockets.
P11-05: skill_learning.py queues learned workflows for locked-Ask approval; Settings remains explicit owner editing.
chat/commands.py handles skill/memory commands before models/history and returns zero-cost saved replies. skills.py
bundles up to six 8k-character resources with instructions; read_skill_resource is agent-bound, fenced and never
executes scripts. skill_history.py archives prior bundles with SHA-256 verification (20 previous + current), and
Settings previews/restores versions/deleted skills. Credential patterns are rejected from instruction/resource/
memory writes; request validation omits raw input. Existing source/memory/path/permission rules still apply.

The experience combines a friend and a working assistant. Text, voice messages and live calls support English,
Urdu script and Roman Urdu. A message starting with "Junior" selects the professional style; ordinary conversation
uses the friend style. Junior is the single voice the user talks to; specialists report back to him.

Daily work already represented in the code includes writing social posts, freelance proposals and replies,
handling email, researching news, working with Google files/calendar, remembering user-provided facts, and
reading or changing files on the user's PC. The dashboard and WhatsApp are the main ways to use it.

## Reading order and sources of truth

- [AGENTS.md](AGENTS.md): development instructions, safety rules and latest handover status.
- [TASK.md](TASK.md): individual tasks, completion marks, setup dependencies and acceptance records.
- [PLAN.md](PLAN.md): design and decisions; includes planned features and older decisions superseded by later entries.
- [README.md](README.md): user-facing capabilities, setup and everyday use.
- Implementation and tests: verify current behavior here before extending a feature or promising a capability.

When sources disagree, report the specific discrepancy and check the relevant code and latest user decision.
An implemented feature is not necessarily connected, live-tested today, or accepted by Muneer.

## Current handover

- Latest: news uses a strict 72-hour publication window at collection, guard, cached display and sending. Every
  rebuild runs Google discovery through Gemini and fetches source evidence; no old-digest carry-forward, hourly
  cache. `news_deliveries` (fa2c4e6a8b0d) reserves source URL/title keys before SMTP and retains sent/uncertain states
  across restarts. Old emailed digest identities are seeded at upgrade. Nothing fresh/unseen means no email.
  Muneer approved ainews.com as an additional publisher. Its main reader/feed paths return Cloudflare 403; its public
  Google News RSS route is accessible. Publisher identity/age are checked and only exact verified wrapper links are
  kept. Google News is not a general allowed search domain. RSS had zero eligible indexed stories at live check.
  `DeleteEntry.tsx` and library/notes DELETE routes add confirmed individual deletion to Recycle Bin. External copies
  and a deleted note's sources remain; busy/stale/uncertain sends are held and unsent dependent cards rejected.
  Full backend 1,007 passed, 72 source follow-ups passed; full browser 103 passed/14 skipped plus a corrected timing
  failure, final 14 passed/2 skipped. TypeScript/ESLint passed. No real files deleted in checks. Backup/migration and
  restart done. Isolated Google freshness check + live 17-source/3-story AI refresh cost $0.005061 combined.
  **Google OAuth currently expired for Drive/inbox** (observed in live logs); user needs Settings → Connections to
  reconnect. Gemini Google Search is a separate working connection. See TASK.md for detailed checks.
  Committed as `99ba1bf`; not pushed. The changed synthetic OpenAI RSS fixture is explicitly tracked despite the
  broad data/ ignore. Other preexisting news fixture files remain locally ignored; review that ignore rule before
  claiming fresh-clone test reproducibility. Existing CLAUDE.md/.agents/AGENTS.md/context changes stay unstaged.
- Phases 0, 1, 2, 2b and 7 are recorded as accepted. Freelance by paste was accepted; further freelance work is paused.
- Gmail implementation includes P4-05/P5-03 email alert parsing. P4-06 acceptance remains unchecked.
  P5-01 still needs Muneer's Upwork/Fiverr notification setup. P5-09 is described as skipped despite its `[~]` marker.
- Social API work (Phase 3) and the Developer Agent (Phase 6 after GitHub connection) are paused by Muneer.
  A permission entry or sender scaffold does not mean the entire integration is finished.
- WhatsApp is recorded as working locally. Docker/Caddy files exist, but VPS setup, migration, monitoring and
  the week-long acceptance test remain open. Deployment has not been verified in this review.
- Local computer work P9-01 through P9-08 is recorded as accepted. P9-09 PC Helper depends on the VPS;
  the current backend operates on the machine where it runs.
- Phase 10: P10-01 WhatsApp/dashboard reply delivery, P10-02 runtime skills and P10-02a Skills Settings are done.
  Settings → Skills manages the starter library; agent scope limits which skills can be loaded. P10-03/04 and
  P10-04a are now built: Documents/Research specialist, local PowerPoint export, progress, cancellation and limits.
  P10-04b adds a separate Notes Agent, Settings skill `class_notes`, dated notes and named folders in the sidebar Notes
  page. Existing folders are reused case-insensitively; new ones are created on save. Supplied class material is the
  source of facts, and notes never automatically become personal profile memory.
  P10-04c adds real binary document placement into exact PC/Google Drive folders and recursive folder ZIPs, with
  the file_transfer skill. Meta rejected a real ZIP upload, so WhatsApp receives the ZIP through a private Google
  Drive link after approval; direct ZIP attachments are not supported by this connection. Live synthetic copy/ZIP
  verification passed ($0.094351 for two model turns). Final full backend passed; full browser 95 passed/14 skipped
  with one voice-test issue fixed, followed by 6 passing transfer/voice checks. Backend restarted; see TASK.md.
  P10-04d adds local `/clear`/`cls` commands (delete conversation/summary, distinct new ID, zero model cost), an original
  file gallery alongside class notes, local previews on selection, and explicit save-only reading guards. Library
  originals survive chat resets and can be found across sessions. Files store library folder/archive metadata on
  ReceivedFile; cloud-only generated Docs/Sheets are indexed too. Internal approval snapshots remain hidden.
  `google.drive.share` is a separate Ask action; future Google saves pin private/reader/writer access on the card.
  The live owner's new-save default is public viewing, while new installs default private. Public editing can be
  requested or selected, existing links can be shared separately, and ZIP delivery remains private. Google permissions
  and byte preservation were checked on synthetic data; no real user chat was cleared. See TASK.md for verification.
  Final checks: 990 backend tests passed; full browser 100 passed/14 skipped, followed by 6 passing gallery/notes
  checks; TypeScript/ESLint passed. Backend backed up/migrated/restarted and live default set to reader. Feature
  commit: `a80745a`; not pushed. Preexisting CLAUDE.md, .agents/, AGENTS.md and this handover remain unstaged.
  **Next planned: P10-05 Google Slides API/PDF**, remaining P10-06 skills, then Muneer's acceptance (P10-07).

- P10-04e adds Notes-folder Rename/Delete APIs in `notes/store.py`, `FolderActions.tsx` three-dot menus on folder
  cards and the open-folder breadcrumb, with Save changes and a confirmation dialog. Deleting a folder retains all
  active/archived contents in Unfiled (or Unfiled (2) when deleting Unfiled); original files/Google/PC copies survive.
  Revisions include folder metadata and contents; stale changes are refused. Folder changes rewrite Markdown mirrors
  before removing old exact mirror paths. No schema migration or recursive deletion is needed.
  Gallery state lives in URL parameters and integrates with native history, explicit Back and per-view scroll.
  Reload preserves filters; direct content links fall back to their library folder. Keep Next's internal __NA marker
  out of native history-call arguments, or it skips updating useSearchParams. Browser checks are recorded in TASK.md.
  Final checks: 995 backend passed; TypeScript/ESLint passed; full browser 101 passed/14 skipped with one cold-start
  approval timeout, resolved by a realistic test wait and 10 passing final desktop/phone regression checks. Live DB
  backed up/backend restarted; health, revision metadata and dashboard checked. No real folder deletion or paid AI test.
  Committed as `d85af42`; not pushed. Existing CLAUDE.md and untracked .agents/, AGENTS.md and this context file
  remain unstaged, as before this task.

Local PPTX, DOCX, XLSX, Markdown and PDF work without a Google connection. Researched Google Slides uses
google/slides.py and the reviewed workspace sender, with a local PPTX fallback. PDF uses an offline owned worker
in documents/pdf.py and pdf_worker.py. Existing Google PDF export remains supported. Real Google Slides creation
has not been tested on the owner's account; its API must be enabled. See P10-05 for checks and limits.

## Runtime and data

- Backend: Python 3.13+, FastAPI, OpenAI Agents SDK, SQLAlchemy and Alembic, SQLite.
- Dashboard: Next.js 16 App Router, React, TypeScript, SWR and Tailwind 4.
- `backend/junior/config.py` loads environment settings; `settings_store.py` holds app preferences in the database.
- `data/junior.db` contains application state; other files and backups live under `data/`. A relative `DATA_DIR`
  resolves from the repository root. Tests must use separate data, never Muneer's live database.
- `agents/models.toml` and `backend/junior/models.py` define configured models, tiers and cost accounting.
  OpenAI, DeepSeek and Gemini paths exist. Configured model names/prices are not a guarantee of current availability.
- Secrets belong in local environment configuration, never these notes or Git. Do not read or print `backend/.env`
  to build context. See configuration code and example files for variable names.

## How a request moves through the app

1. The dashboard uses `frontend/src/lib/api.ts` and `useChatSocket.ts` to reach REST APIs and `/ws/chat`.
   WhatsApp enters through `backend/junior/whatsapp.py`; live calls use `calls.py` or `gemini_live.py`.
2. `chat/service.py` saves messages and sources, builds history, runs a turn, streams progress and saves the answer.
   `chat/history.py` handles history/summaries; `agent/context.py` carries provenance, usage, approvals and events.
3. `registry.py` loads agent definitions. `agent/builder.py` supplies instructions, model and tools;
   `agent/runner.py` runs the SDK turn and reports streamed text, tool steps and cost.
4. `agent/tools.py` registers tool groups and connects to domain tools. `agent/helpers.py` runs specialists with
   the same turn context and budget. Writing uses Writer, Checker and Humanizer; other prose uses the Polisher.
5. Actions use the applicable permission/gate checks. Queued actions become approval cards; approved API or PC
   work goes through `senders/dispatch.py` and its sender. Copy-and-paste work is posted by Muneer himself.
6. `background.py`, the chat service and `scheduler.py` support long work and scheduled jobs. Background tasks
   keep progress, elapsed time, costs, files, limits and running/done/failed/cancelled states. Time estimates use
   similar finished tasks; no history means unknown. The Documents pipeline runs separately from Junior's chat.

Startup in `backend/junior/main.py` initializes/migrates the database, validates model/agent/playbook/skill/news
configuration, registers senders/routes, recovers interrupted work and starts background services. Invalid
instruction files deliberately fail startup. Interrupted background tasks are marked failed, not automatically resumed.

## Where to make changes

- Personality and specialist instructions: `agents/*.md`; definitions are loaded by `backend/junior/registry.py`.
- Runtime skills: `skills/*.md`, `backend/junior/skills.py`, and the skill tools in `agent/tools.py`.
  Agents see descriptions and load instructions when needed; loaded skills are tracked per turn.
- Researched deliverables: `junior/documents/` (writer/checker schemas, real search citation collection, task-model
  limits and deterministic exports), `agents/documents_agent.md`, `agents/documents_checker.md`. The model supplies
  structured content; it never writes or runs a script to create a deck. `ask_documents_agent` queues the work.
  Generated artifacts use ReceivedFile with source `generated`, inside `data/files`, and `/api/files/{id}/download`.
  WhatsApp background delivery attaches those files only to their originating WhatsApp chat. Google research files
  use `senders/google_workspace.py` and normal approval guards. Task fields: migration `f4b6c8d0e2a5`.
- Writing/social: `backend/junior/writing/`, `ideas.py`, `images.py`, `playbooks/` and the social agent definitions.
- Class notes: `backend/junior/notes/` (source extraction/vision, checked draft, storage/API and Junior tools),
  `agents/notes_agent.md`, `skills/class_notes.md`, `frontend/src/app/notes/page.tsx`. SQLite stores canonical notes;
  atomic Markdown mirrors live in `data/notes/<folder-id>-<name>/<class-date> <note-id>-<title>.md` and originals stay
  in `data/files`. Migration `f6c8d0e2a4b7` adds NotesFolder/ClassNote. Folder names refer to this app library;
  arbitrary PC paths remain permission-checked Computer actions. Notes use the existing background pipeline with
  progress and bounded cost/time/retries, up to eight source files/eight visual readings/80,000 extracted characters
  and 120 PDF pages per batch. Editing uses revision checks; archive is reversible. PowerPoint text/tables/charts/
  speaker notes are also readable through the general file reader; scanned PDF and embedded visual reading belongs
  to the Notes source pipeline (pypdfium2 + existing vision provider).
- Email and freelance: `inbox.py`, `google/gmail.py`, `senders/gmail.py`, `freelance/`.
  `mailer.py` is the separate SMTP route for messages to the owner.
- Google and attachments: `google/`, `files.py`, `reading.py`; GitHub connection: `github/`.
- News, feeds and daily work: `news/`, `feeds.py`, `reports.py`, `memory_tidy.py`, `scheduler.py`.
- Computer actions: `computer/paths.py`, `tools.py`, `sender.py`, `terminal.py` and `agents/computer_agent.md`.
- Managed PC jobs (P11-01): `computer/jobs.py` owns status/history and per-app supervision;
  `computer/owned_process.py` assigns each Windows PowerShell process to an unnamed kill-on-close Job Object
  before releasing its stdin handshake. Commands/descendants stay owned even on backend crash. This is lifetime
  management, not a shell sandbox. `ComputerJob` (migration fc4e6a8b0d2f) stores bounded output and the approval ID;
  saved PIDs are never replayed or killed during recovery. `pc_run_background`, `pc_job_status`, `pc_stop_job`
  belong to the Computer Agent; start uses locked computer.run, stop proposals use locked computer.job.stop.
  The owner can cancel directly in Settings → Computer even while paused/off/in Plan. Max three jobs, default
  600s/max 3600s, last 16,000 output characters, no automatic retry. UI polling is ordinary HTTP, not model calls.
  `frontend/src/components/ComputerJobs.tsx` and `/api/computer/jobs` provide status/output/stop. Production
  browser-control tools remain P11-03. WhatsApp integration work is deferred.
- Desktop controls (P11-02): `computer/desktop.py` (permission/scoping, expiring single-use snapshots, approval
  execution/API/tools), `desktop_native.py` (UIA + guarded SendInput + window-only PrintWindow), `desktop_fake.py`
  (fake-AI adapter). Desktop is off by default; supported process selection is explicit in Settings → Computer.
  `DesktopSettings.tsx` manages opt-in/apps/previews. Only reviewed app/control identities are focused; a dashboard
  approval can restore that target but the adapter stops if focus/control identity changes during input. It never
  automates terminal/browser/auth/security UI or file dialogs. Snapshots are data, marked before vision; max four
  per model turn. Max 1,000 characters/action, 80 controls, eight-second worker budget, 100 captures, one-day preview
  expiry/pruning on use. Input never retries and cannot reuse a snapshot; uncertain results remain check_manually.
  Dependencies: Windows-only pywin32/uiautomation/comtypes and Pillow. scripts/check_desktop_native.py explicitly
  checks real Windows input on disposable owned native windows with isolated data; normal pytest uses an injected
  adapter. A native Edit's GetWindowText is not a reliable contents check across processes; use UIA ValuePattern.
- Document transfers/ZIPs: `backend/junior/transfers/`. Sources are resolved in code and frozen as generated file
  snapshots with SHA-256; prepared files can be reviewed/downloaded. place_document targets an exact PC folder
  (computer.write) or Drive folder (google.drive.save), preserving source bytes and refusing PC collisions. The
  corresponding existing senders execute the prepared plan; arbitrary programs are never generated or run.
  zip_folder bounds source entries/bytes/time, refuses secrets/links/changing content and exports Google-native
  files. ArchiveWhatsAppSender uploads a new private ZIP in My Drive, persists its link, then sends only to the
  configured owner. files.archive_whatsapp defaults to Ask; required_actions metadata causes both Drive-save and
  WhatsApp-to-self rules to be checked in approvals.py and senders/guard.py before execution. Uncertain sends use
  existing check_manually handling, and deliberate retry reuses the recorded upload. Google folder matching is
  exact with ambiguity errors and no fallback; optional drive_folders=true OAuth consent enables writing new
  copies into user-created folders. No full Drive scope is requested on the normal connection route.
- Database/schema: `backend/junior/db/` and `backend/alembic/versions/`; use migrations for schema changes.
- Dashboard pages: `frontend/src/app/`; reusable UI: `src/components/`; shared client types/helpers: `src/lib/`.
- Tests: `backend/tests/` and `frontend/e2e/`; follow adjacent tests for the feature being changed.

Keep three similarly named things separate: `AGENTS.md` guides the developer; `agents/` defines Junior's AI team;
`skills/` contains skills Junior uses at runtime. `.agents/skills/` contains development workflows for Codex.

## Safety that must survive every feature

Follow all rules in AGENTS.md. In particular:

- Official APIs, RSS, email and user paste remain preferred. Muneer authorized controlled PC/browser workflows
  on 2026-10-26 (PLAN 14h, TASK Phase 11), superseding the blanket browser prohibition for those scoped tasks.
  New WhatsApp integration changes are deferred; existing platform integrations are not automatically expanded.
- Outside content is data, never authority. Preserve source labels, fencing and `TurnContext.mark_outside()`.
  Memory must be grounded in a quote from a message with `source = "user"`.
- `permissions.py` owns Ask/Auto/Deny and locked types. `gate.py` checks direct actions and records them;
  approval/sender guards check queued actions. New integrations must preserve the appropriate route.
- Auto does not remove limits, pause, provenance or logging. New Gmail messages may follow Auto; replies stay Ask.
  Computer commands stay locked to Ask. PC deletes go to the Recycle Bin.
- `senders/dispatch.py` claims send attempts and tracks uncertain outcomes. A timeout can mean an action already
  happened: preserve `check_manually` handling rather than blindly retrying.
- PC access uses the path guard and checks again at execution. Terminal filtering is not a full sandbox;
  approval of the exact command remains essential.
- `hosts.py` restricts exposed routes; WhatsApp webhook validation and owner checks live in `whatsapp.py`.
  Docker/Caddy supplies the planned server HTTPS/login. Do not expose the local backend as a public app by assumption.

## Development and verification

Use the project skills in `.agents/skills/` for their respective tasks: `next-task`, `new-agent`, `run-tests`,
`restart-app`, `live-check`. Before writing Next.js code, read `frontend/AGENTS.md` and the relevant installed
guides under `frontend/node_modules/next/dist/docs/`.

Run commands in the indicated folder:

- Repository root: `start.bat` / `stop.bat`; app ports are backend **8000** and dashboard **3000**.
- `backend/`: `.\.venv\Scripts\python.exe -m pytest -q`.
- `frontend/`: `npx tsc --noEmit`, `npx eslint src`, `npx playwright test`.
- Repository root: `test.bat` runs the backend and dashboard suites.

Playwright starts its own fake backend on **8100** and production dashboard on **3100**, with test data under
`frontend/test-results/e2e-data` and a separate `.next-e2e` build. Use the existing harness; do not point it at
the live app. `FAKE_AI` and service-specific fakes are implemented separately: do not assume a single fake flag
disables every possible external call. Real quality checks follow `live-check` and use throwaway data.

After backend code changes restart the running backend using `restart-app`. Work one feature at a time, include
its safety tests, update TASK.md honestly, and follow the project commit/push rules. Push only when requested or
at phase acceptance. A documentation review is not a new feature acceptance or a claim that tests passed.

## Latest session and next pickup

2026-10-24: completed P10-04c at Muneer's request. Exact document placement, bounded recursive ZIPs and approved
private-link WhatsApp delivery are built and tested. Real synthetic PC/Drive copies matched the original PDF bytes;
both ZIP sources reopened correctly, and Meta accepted the ZIP-link message. Real Google broader consent and phone
delivery/read receipts remain unverified. Temporary app data and PC fixtures were removed; the labeled synthetic
Google Drive test file/folder and ZIP remain available through the sent link. Live chats, memory and approvals were
not used by that verification. Existing broader-scope setup is an optional user consent in Settings → Connections.
No new Google permissions are requested by the default connection, and no public sharing permission is created.
The last backend restart includes the transfer tools and unreadable-subfolder failure handling. Tests and actual
costs are recorded in TASK.md; do not claim an unperformed phase acceptance or push.

2026-10-24: implemented P10-03/04/P10-04a at Muneer's request. Researched PowerPoint generation returns the file,
  replacing the previous behavior of writing a Python script on his PC. Default task limits: $0.50, 600 seconds,
  one shared service/content retry; at most 12 model calls and four searches. Limits are editable in Settings.
  Final backend suite passed, full browser run had 92 passed/14 skipped, and final feature browser run had 4 passed.
  TypeScript/ESLint passed. An initial timing-sensitive backend test passed on its focused rerun and the final full run.
  Real NLP check: 6 slides, ~94 seconds, $0.0850729 including chat; all six slides rendered/inspected in PowerPoint.
  Earlier live failures led to fixes in checker/export-stage instructions and format-specific citation validation.
  Backend restarted after a live-database backup; health and Documents Agent registration verified, dashboard on 3000.
  Live WhatsApp/Google writes were not part of verification; their delivery/approval paths were checked with fakes.
  Follow-up at Muneer's explicit request: the running app made an 8-slide NLP deck and Meta accepted the actual
  PowerPoint document message to his WhatsApp (~86 seconds, $0.061059484 including chat). The downloaded file
  reopened with all 8 slides and source notes. Phone delivery/read receipts were not checked; Google writes remain
  verified with fakes only.

At the next feature session, check the working tree and Muneer's latest request, then reread its TASK entry.
P10-05 and P10-06 are complete; P10-07 is the owner's acceptance test. Do not resume paused
phases or invent VPS/account details. Keep this guide focused on enduring decisions and useful entry points;
keep detailed task history in TASK.md.

The system-action work authorized 2026-10-26 (PLAN section 14h / TASK Phase 11) is complete through P11-08.
Follow-up on 2026-10-27 confirmed backend health at commit 5f344c5, dashboard HTTP 200 and supervised=true.
Do not restart completed P11 tasks because historical entries say "next". New WhatsApp integrations remain deferred.
Paused and setup-dependent phases are not automatically resumed by a generic continuation request.
