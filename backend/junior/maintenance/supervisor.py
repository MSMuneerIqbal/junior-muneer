"""Local Windows release supervisor. Launched by start.bat, never adopts a stored PID.

Original checkout and .env are preserved. Releases have separate environments/node_modules;
an atomic pointer selects them. No background retries, no automatic upstream execution.
"""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from contextlib import closing
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from junior.computer.owned_process import OwnedTree
from junior.maintenance.source import MaintenanceError, clean, export, git, home, read_json, revision, write_json

TOTAL_SECONDS = 3600
MAX_LOG = 8 * 1024 * 1024
CHILD = Path(__file__).with_name("child.py")
BASE_PYTHON = getattr(sys, "_base_executable", sys.executable)


def npm_command(*args):
    npm = shutil.which("npm.cmd")
    node = shutil.which("node.exe")
    cli = Path(npm).parent / "node_modules" / "npm" / "bin" / "npm-cli.js" if npm else None
    if not node or not cli or not cli.is_file():
        raise MaintenanceError("A standard Node.js installation with npm is required for supervised updates.")
    return [node, str(cli), *args]


class Child:
    def __init__(self, command, cwd, env, log):
        self.tree = OwnedTree()
        self.log = Path(log)
        self.file = self.log.open("ab")
        self.process = None
        try:
            self.process = subprocess.Popen([BASE_PYTHON, str(CHILD), *map(str, command)], cwd=cwd, env=env,
                                            stdin=subprocess.PIPE, stdout=self.file, stderr=subprocess.STDOUT,
                                            creationflags=subprocess.CREATE_NO_WINDOW)
            self.tree.assign(self.process.pid)
            self.process.stdin.write(b"junior-go\n")
            self.process.stdin.flush()
            self.process.stdin.close()
        except BaseException:
            self.stop()
            raise

    def stop(self):
        self.tree.close()
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()  # this live child handle only, including failed assignment/handshake
            self.process.wait(timeout=15)
        self.file.close()


def backup_db(source, target):
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)


def restore_db(source, target):
    # Caller owns/stopped both servers. SQLite backup also replaces migrated schemas safely.
    backup_db(source, target)


def pause_db(db):
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("INSERT INTO settings (key,value,updated_at) VALUES ('paused','true',CURRENT_TIMESTAMP) ON CONFLICT(key) DO UPDATE SET value='true',updated_at=CURRENT_TIMESTAMP")


class Supervisor:
    def __init__(self, root, data, *, backend_port=8000, frontend_port=3000):
        self.root, self.data = Path(root).resolve(), Path(data).resolve()
        self.folder = self.data / "updates"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.session = uuid.uuid4().hex
        self.servers = []
        self.deadline = None
        self.activating = False
        self.pointer = self.folder / "active.json"
        self.opener = build_opener(ProxyHandler({}))
        self.backend_port, self.frontend_port = backend_port, frontend_port

    def heartbeat(self):
        write_json(self.folder / "supervisor.json", {"session": self.session, "heartbeat": time.time()})

    def progress(self, state, step, **extra):
        prior = read_json(self.folder / "progress.json", {})
        write_json(self.folder / "progress.json", {**prior, **extra, "state": state, "step": step, "updated_at": time.time()})

    def allowed(self):
        self.heartbeat()
        if self.deadline and time.monotonic() > self.deadline:
            raise MaintenanceError("The 60-minute update limit was reached.")
        if (self.folder / "stop").exists():
            raise MaintenanceError("The owner stopped the supervisor.")
        if self.deadline and not self.activating:
            with closing(sqlite3.connect(self.data / "junior.db")) as conn:
                settings = dict(conn.execute("SELECT key,value FROM settings WHERE key IN ('paused','permission_mode')"))
            if json.loads(settings.get("paused", "false")) or json.loads(settings.get("permission_mode", '"rules"')) == "plan":
                raise MaintenanceError("Pause/Plan cancelled the update checks.")

    def run(self, command, cwd, env, label, seconds=900):
        self.progress("preparing", label)
        log = self.folder / "checks.log"
        log.write_text("", encoding="utf-8")  # capped private local diagnostic; never returned to the model
        child = Child(command, cwd, env, log)
        deadline = time.monotonic() + seconds
        try:
            while child.process.poll() is None:
                self.allowed()
                if time.monotonic() > deadline or log.stat().st_size > MAX_LOG:
                    raise MaintenanceError("A check exceeded its time/output limit.")
                time.sleep(.2)
            if child.process.returncode:
                raise MaintenanceError(f"{label} failed. See the private updates/checks.log file locally.")
        finally:
            child.stop()

    def active(self):
        record = read_json(self.pointer)
        if not record:
            return self.root, git(self.root, "rev-parse", "HEAD")
        sha = revision(record["revision"])
        path = self.folder / "releases" / sha
        if path.is_symlink() or path.is_junction() or not path.is_dir():
            raise MaintenanceError("The active release is missing or linked. Check the update record locally.")
        return path, sha

    def environment(self, source, sha):
        return {**os.environ, "DATA_DIR": str(self.data), "JUNIOR_HOME": str(self.root), "JUNIOR_REVISION": sha,
                "PORT": str(self.frontend_port),
                "JUNIOR_ENV_FILE": str(self.root / "backend" / ".env"),
                "JUNIOR_SKILLS_DIR": str(self.root / "skills"), "JUNIOR_SUPERVISED": self.session}

    def start_servers(self):
        source, sha = self.active()
        env = self.environment(source, sha)
        python = source / "backend" / ".venv" / "Scripts" / "python.exe"
        frontend = source / "frontend"
        self.servers.append(Child([python, "-m", "uvicorn", "junior.main:app", "--host", "127.0.0.1", "--port", str(self.backend_port)],
                                  source / "backend", env, self.folder / "backend.log"))
        self.servers.append(Child(npm_command("run", "start" if source != self.root else "dev"),
                                  frontend, env, self.folder / "dashboard.log"))

    def stop_servers(self):
        for child in reversed(self.servers):
            child.stop()
        self.servers.clear()

    def health(self, expected):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            self.allowed()
            try:
                with self.opener.open(f"http://127.0.0.1:{self.backend_port}/health", timeout=2) as response:
                    body = json.loads(response.read(2048))
                with self.opener.open(f"http://127.0.0.1:{self.frontend_port}", timeout=2) as response:
                    okay = response.status == 200
                if body.get("status") == "ok" and body.get("revision") == expected and okay:
                    return
            except (OSError, ValueError):
                pass
            if any(child.process.poll() is not None for child in self.servers):
                break
            time.sleep(.5)
        raise MaintenanceError("The selected release did not pass its backend/dashboard health checks.")

    def prepare(self, request):
        clean(self.root)
        if git(self.root, "rev-parse", "HEAD") != request["root_head"]:
            raise MaintenanceError("Local source changed since the review.")
        _, base = self.active()
        if base != request["base"]:
            raise MaintenanceError("The running revision changed since the review.")
        target = revision(request["target"])
        git(self.root, "merge-base", "--is-ancestor", base, target)
        if shutil.disk_usage(self.folder).free < 8 * 1024**3:
            raise MaintenanceError("At least 8 GB free disk space is needed for a tested release and rollback.")
        releases = self.folder / "releases"
        if releases.exists() and len(list(releases.iterdir())) >= 3:
            raise MaintenanceError("Three staged releases are retained. Review/archive old releases locally before another update.")
        candidate = releases / target
        self.progress("preparing", "Exporting the exact reviewed source")
        export(self.root, target, candidate)
        lock = candidate / "backend" / "requirements.lock"
        if not lock.exists() or not all(re.fullmatch(r"[\w.-]+==[\w.+!-]+(?:;[^\r\n]+)?", line.strip())
                                        for line in lock.read_text().splitlines() if line.strip() and not line.startswith("#")):
            raise MaintenanceError("The release needs a complete version-pinned requirements.lock.")
        if not (candidate / "frontend" / "package-lock.json").exists():
            raise MaintenanceError("The release needs package-lock.json.")
        safe_env = {key: value for key, value in os.environ.items() if key.upper() in
                    {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "COMSPEC", "PATHEXT"}}
        env = {**safe_env, "PIP_CONFIG_FILE": os.devnull, "NPM_CONFIG_USERCONFIG": os.devnull,
               "DATA_DIR": str(candidate / "rehearsal"), "JUNIOR_ENV_FILE": str(candidate / "missing.env"),
               "FAKE_AI": "true", "SCHEDULER_ENABLED": "false", "OPENAI_API_KEY": "", "DEEPSEEK_API_KEY": "",
               "GEMINI_API_KEY": "", "JUNIOR_SKILLS_DIR": str(candidate / "skills")}
        for key in ("JUNIOR_HOME", "JUNIOR_REVISION", "JUNIOR_SUPERVISED", "PYTHONPATH", "PYTHONHOME", "NODE_OPTIONS"):
            env.pop(key, None)
        backend = candidate / "backend"
        python = backend / ".venv" / "Scripts" / "python.exe"
        self.run([BASE_PYTHON, "-m", "venv", backend / ".venv"], backend, env, "Creating a separate Python environment")
        self.run([python, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--no-deps", "-r", lock],
                 backend, env, "Installing pinned Python dependencies")
        self.run([python, "-m", "pip", "check"], backend, env, "Checking dependency consistency")
        rehearsal = candidate / "rehearsal"
        rehearsal.mkdir()
        backup_db(self.data / "junior.db", rehearsal / "junior.db")
        self.run([python, "-c", "from junior.db import init_db; init_db()"], backend, env, "Rehearsing database migrations", 120)
        self.run([python, "-m", "pytest", "-q"], backend, env, "Running backend safety and regression tests", 1200)
        for args, label in [(["ci", "--ignore-scripts", "--no-audit", "--no-fund"], "Installing dashboard lockfile"),
                            (["run", "typecheck"], "Checking dashboard types"), (["run", "lint"], "Checking dashboard lint"),
                            (["run", "build"], "Building dashboard")]:
            self.run(npm_command(*args), candidate / "frontend", env, label)
        clean(self.root)  # concurrent local changes block activation too
        if git(self.root, "rev-parse", "HEAD") != request["root_head"]:
            raise MaintenanceError("The local revision changed during checks.")
        return candidate

    def recover(self):
        state = read_json(self.folder / "progress.json", {})
        if state.get("state") in {"switching", "rolling_back"}:
            self.rollback(state)
        elif state.get("state") in {"queued", "preparing"}:
            self.progress("interrupted", "Update preparation was interrupted. No automatic retry; current release retained.")
        # Old session requests cannot run after a supervisor restart.
        request = self.folder / "request.json"
        if request.exists():
            request.replace(self.folder / "interrupted-request.json")

    def rollback(self, state):
        self.stop_servers()
        self.progress("rolling_back", "Restoring the previous database and release")
        backup = self.folder / f"before-{revision(state['target'])}.db"
        if not backup.exists():
            raise MaintenanceError("Rollback backup is missing. Servers remain stopped; recover locally.")
        restore_db(backup, self.data / "junior.db")
        pause_db(self.data / "junior.db")
        write_json(self.pointer, state.get("previous"))
        self.progress("rolled_back", "Previous release/database restored; Junior remains paused. Review interrupted work before resuming.")

    def update(self, request):
        self.deadline = time.monotonic() + TOTAL_SECONDS
        self.progress("preparing", "Starting approved checks", target=request["target"], previous=read_json(self.pointer),
                      conversation_id=request.get("conversation_id"), approval_id=request["approval_id"])
        switching = False
        try:
            self.prepare(request)
            self.allowed()
            # The app rechecks permissions immediately before handing off. Pause/Plan during preparation cancels activation.
            with closing(sqlite3.connect(self.data / "junior.db")) as conn:
                settings = dict(conn.execute("SELECT key,value FROM settings WHERE key IN ('paused','permission_mode')"))
            if json.loads(settings.get("paused", "false")) or json.loads(settings.get("permission_mode", '"rules"')) == "plan":
                raise MaintenanceError("Pause/Plan is enabled. Activation was cancelled; no release was changed.")
            self.stop_servers()
            backup_db(self.data / "junior.db", self.folder / f"before-{request['target']}.db")
            self.activating = True
            self.progress("switching", "Rollback backup saved; switching the selected release")
            switching = True
            pause_db(self.data / "junior.db")
            write_json(self.pointer, {"revision": request["target"]})
            self.start_servers()  # startup runs real migrations; paused throughout health checks
            self.health(request["target"])
            self.progress("done", "Update healthy. Junior remains paused; review interrupted work, then resume.")
        except Exception as error:
            if switching:
                self.rollback(read_json(self.folder / "progress.json"))
                self.deadline = None
                if not (self.folder / "stop").exists():
                    self.start_servers()
                    self.health(request["base"])
            else:
                self.progress("failed", str(error) if isinstance(error, MaintenanceError) else "Update check failed; current release preserved.")
                if not self.servers and not (self.folder / "stop").exists():
                    self.start_servers()
        finally:
            self.deadline = None
            self.activating = False

    def loop(self):
        self.recover()
        self.heartbeat()
        self.start_servers()
        try:
            while not (self.folder / "stop").exists():
                self.heartbeat()
                request = read_json(self.folder / "request.json")
                if request:
                    if request.get("session") == self.session and time.time() - request.get("queued_at", 0) >= 5:
                        (self.folder / "request.json").replace(self.folder / "last-request.json")
                        self.update(request)
                    elif request.get("session") != self.session:
                        (self.folder / "request.json").replace(self.folder / "interrupted-request.json")
                if any(child.process.poll() is not None for child in self.servers):
                    self.progress("interrupted", "A server exited. No automatic retry. Check local server logs and start Junior again.")
                    break
                time.sleep(.5)
        finally:
            self.stop_servers()
            write_json(self.folder / "supervisor.json", {})


if __name__ == "__main__":
    if os.name != "nt":
        raise SystemExit("Local supervised updates currently require Windows. Deploy servers through your normal deployment process.")
    root = home()
    from junior.config import get_settings
    data = get_settings().data_path.resolve()
    supervisor = Supervisor(root, data)
    import msvcrt
    launcher_lock = (supervisor.folder / "launcher.lock").open("a+b")
    launcher_lock.write(b"0")
    launcher_lock.flush()
    launcher_lock.seek(0)
    try:
        msvcrt.locking(launcher_lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        raise SystemExit("Junior's supervisor is already running.") from None
    # Refuse a second launcher before taking ownership; never stop unrelated listeners.
    import socket
    locks = []
    try:
        for port in (8000, 3000):
            sock = socket.socket()
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(("127.0.0.1", port))
            locks.append(sock)
    except OSError:
        raise SystemExit("A backend/dashboard is already running. Stop it normally before starting the supervisor.") from None
    finally:
        for sock in locks:
            sock.close()
    (supervisor.folder / "stop").unlink(missing_ok=True)
    supervisor.loop()
