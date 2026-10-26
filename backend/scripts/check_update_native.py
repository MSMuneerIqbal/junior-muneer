r"""Opt-in real installer/migration/server-switch check on disposable Git/SQLite and random local ports.

No model or external account calls. Downloads only the small fixture's pinned test/server dependencies.
Run: .venv\Scripts\python scripts\check_update_native.py
"""

import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from junior.maintenance.supervisor import Supervisor, BASE_PYTHON
from junior.maintenance.source import read_json


def main():
    with tempfile.TemporaryDirectory(prefix="junior-update-check-") as temp:
        root = Path(temp) / "checkout"
        root.mkdir()
        def write(path, text):
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        def git(*args):
            return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL).decode().strip()
        write(".gitignore", ".venv/\n__pycache__/\n.pytest_cache/\n")
        write("backend/junior/__init__.py", "")
        write("backend/junior/db.py", "import sqlite3,os\nfrom pathlib import Path\ndef init_db():\n p=Path(os.environ['DATA_DIR']); p.mkdir(exist_ok=True,parents=True)\n with sqlite3.connect(p/'junior.db') as db: db.execute('CREATE TABLE IF NOT EXISTS migrated(value TEXT)')\n")
        write("backend/junior/main.py", "import os,json\nfrom junior.db import init_db\ninit_db()\nasync def app(scope,receive,send):\n if scope['type']=='lifespan':\n  while True:\n   event=await receive()\n   await send({'type':event['type']+'.complete'})\n   if event['type']=='lifespan.shutdown': return\n else:\n  await send({'type':'http.response.start','status':200,'headers':[(b'content-type',b'application/json')]})\n  await send({'type':'http.response.body','body':json.dumps({'status':'ok','revision':os.environ['JUNIOR_REVISION']}).encode()})\n")
        write("backend/pyproject.toml", '[tool.pytest.ini_options]\npythonpath=["."]\n')
        write("backend/tests/test_fixture.py", "def test_fixture():\n import os\n from junior.db import init_db\n init_db()\n assert os.environ['FAKE_AI']=='true'\n assert os.environ.get('OPENAI_API_KEY')==''\n")
        wanted = {"uvicorn", "click", "h11", "colorama", "pytest", "iniconfig", "packaging", "pluggy", "pygments"}
        original_lock = (Path(__file__).resolve().parents[1] / "requirements.lock").read_text()
        lines = [line for line in original_lock.splitlines() if line.split("==")[0].casefold() in wanted]
        write("backend/requirements.lock", "\n".join(lines) + "\n")
        scripts = {name: "node check.cjs" for name in ("typecheck", "lint", "build")}
        scripts.update(start="node server.cjs", dev="node server.cjs")
        write("frontend/package.json", json.dumps({"name": "junior-update-fixture", "version": "1.0.0", "scripts": scripts}))
        write("frontend/package-lock.json", json.dumps({"name": "junior-update-fixture", "version": "1.0.0", "lockfileVersion": 3,
              "packages": {"": {"name": "junior-update-fixture", "version": "1.0.0"}}}))
        write("frontend/check.cjs", "if (!process.env.FAKE_AI) process.exit(2);\n")
        write("frontend/server.cjs", "require('http').createServer((req,res)=>res.end('fixture')).listen(Number(process.env.PORT),'127.0.0.1');\n")
        git("init", "-q")
        git("config", "user.name", "Synthetic check")
        git("config", "user.email", "fixture@example.test")
        git("add", ".")
        git("commit", "-qm", "base")
        base = git("rev-parse", "HEAD")
        write("README.md", "Synthetic release change.\n")
        git("add", ".")
        git("commit", "-qm", "reviewed target")
        target = git("rev-parse", "HEAD")
        git("checkout", "--detach", base)
        data = Path(temp) / "data"
        data.mkdir()
        with closing(sqlite3.connect(data / "junior.db")) as db, db:
            db.execute("CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT,updated_at TEXT)")
            db.execute("CREATE TABLE marker(value TEXT)")
            db.execute("INSERT INTO marker VALUES ('preserve')")
        ports = []
        for _ in range(2):
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                ports.append(sock.getsockname()[1])
        supervisor = Supervisor(root, data, backend_port=ports[0], frontend_port=ports[1])
        request = {"base": base, "root_head": base, "target": target, "approval_id": 1}
        try:
            supervisor.update(request)
            state = read_json(supervisor.folder / "progress.json")
            if state["state"] != "done":
                # Fixture logs contain no credentials. Show only this opt-in diagnostic on failure.
                print((supervisor.folder / "checks.log").read_text(errors="replace")[-4000:])
                raise AssertionError(state)
            with closing(sqlite3.connect(data / "junior.db")) as db:
                assert db.execute("SELECT value FROM marker").fetchone()[0] == "preserve"
                assert db.execute("SELECT name FROM sqlite_master WHERE name='migrated'").fetchone()
            assert git("rev-parse", "HEAD") == base and not git("status", "--porcelain")
            assert read_json(supervisor.pointer)["revision"] == target
            print(json.dumps({"result": "passed", "dependency_install": True, "migration": True,
                              "owned_server_handover": True, "original_checkout_preserved": True, "model_cost_usd": 0}))
        finally:
            supervisor.stop_servers()


if __name__ == "__main__":
    main()
