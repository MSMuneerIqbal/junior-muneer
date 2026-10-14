"""Daily database backups: data/backups/junior-YYYY-MM-DD.db, the last 14 kept.

Backups keep running while paused: they protect your data and do no AI work.

    GET  /api/backups      list backups
    POST /api/backups      make one now

From the terminal (stop the backend before restoring):
    python -m junior.backup now
    python -m junior.backup list
    python -m junior.backup restore data/backups/junior-2026-10-14.db
"""

import logging
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter

from junior.audit import audit
from junior.config import get_settings
from junior.db.engine import close_all_connections
from junior.settings_store import get_setting
from junior.timeutil import zone

log = logging.getLogger(__name__)
router = APIRouter()

KEEP = 14
PREFIX = "junior-"


def backup_dir() -> Path:
    path = get_settings().data_path / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_date() -> str:
    return datetime.now(UTC).astimezone(zone(get_setting("timezone"))).date().isoformat()


def list_backups() -> list[Path]:
    """Newest first."""
    return sorted(backup_dir().glob(f"{PREFIX}*.db"), reverse=True)


def make_backup(label: str | None = None) -> Path:
    """Copy the database safely (SQLite's backup API works while the app is running)."""
    target = backup_dir() / f"{PREFIX}{label or local_date()}.db"
    tmp = target.with_suffix(".tmp")
    source = sqlite3.connect(get_settings().db_path)
    try:
        dest = sqlite3.connect(tmp)
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()
    tmp.replace(target)
    pruned = prune()
    audit("system", "backup", detail={"file": target.name, "pruned": pruned})
    log.info("Backup written: %s", target)
    return target


def prune(keep: int = KEEP) -> list[str]:
    old = list_backups()[keep:]
    for path in old:
        path.unlink()
    return [p.name for p in old]


def backup_if_due() -> Path | None:
    """Make today's backup if it doesn't exist yet. Called by the scheduler."""
    if (backup_dir() / f"{PREFIX}{local_date()}.db").exists():
        return None
    return make_backup()


def restore(backup: Path) -> None:
    """Replace the database with a backup. Stop the backend first."""
    if not backup.exists():
        raise FileNotFoundError(backup)
    close_all_connections()
    db = get_settings().db_path
    if db.exists():
        safety = db.with_name(f"junior-before-restore-{datetime.now():%Y%m%d-%H%M%S}.db")
        shutil.copy2(db, safety)
        log.info("Current database saved as %s", safety)
    for extra in (db.with_name(db.name + "-wal"), db.with_name(db.name + "-shm")):
        extra.unlink(missing_ok=True)
    shutil.copy2(backup, db)
    log.info("Restored %s", backup)


@router.get("/api/backups")
def api_list() -> list[dict]:
    return [
        {"file": p.name, "size_bytes": p.stat().st_size} for p in list_backups()
    ]


@router.post("/api/backups", status_code=201)
def api_backup_now() -> dict:
    path = make_backup()
    return {"file": path.name, "size_bytes": path.stat().st_size}


if __name__ == "__main__":
    from junior.db import init_db
    from junior.logging_setup import setup_logging

    setup_logging()
    command = sys.argv[1] if len(sys.argv) > 1 else "list"
    if command == "restore" and len(sys.argv) == 3:
        restore(Path(sys.argv[2]))
    elif command == "now":
        init_db()
        print(make_backup())
    elif command == "list":
        for path in list_backups():
            print(path.name)
    else:
        sys.exit(__doc__)
