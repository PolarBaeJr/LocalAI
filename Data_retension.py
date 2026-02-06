"""
Session data retention utilities.
- Archived deletions are moved into Deleted_Data/<session_id>_<ts>.json
- Files older than RETENTION_DAYS are purged automatically.
- A debug guard allows explicit single-file removal when DEBUG_SINGLE_DELETE=1.
"""

from __future__ import annotations

import os
import time
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from Debug import dbg, add_error

RETENTION_DAYS = 30
UPLOAD_RETENTION_DAYS = 1
ARCHIVE_DIR = Path(__file__).with_name("Deleted_Data")
ARCHIVE_DIR.mkdir(exist_ok=True)
UPLOADS_DIR = Path(__file__).with_name("uploads")
UPLOAD_ARCHIVE_DIR = ARCHIVE_DIR / "uploads"
UPLOAD_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _timestamp_for_filename() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def archive_session_file(path: Path, session_id: str) -> Optional[Path]:
    """
    Move the session file to the archive folder with a timestamped name.
    Returns the new path or None if nothing was moved.
    """
    if not path.exists():
        dbg(f"Archive skip: no file for session {session_id}")
        return None

    target = ARCHIVE_DIR / f"{session_id}_{_timestamp_for_filename()}{path.suffix}"
    try:
        path.replace(target)
        dbg(f"Session {session_id} archived to {target.name}")
        return target
    except Exception as exc:  # noqa: BLE001
        add_error(f"Archive failed for {session_id}: {exc}")
        return None


def archive_session_uploads(session_id: str) -> Optional[Path]:
    """
    Move uploads for a session into Deleted_Data/uploads/<session_id>_<ts>/.
    Returns target dir or None if nothing was moved.
    """
    if not UPLOADS_DIR.exists():
        return None
    src = UPLOADS_DIR / session_id
    if not src.exists():
        return None
    target = UPLOAD_ARCHIVE_DIR / f"{session_id}_{_timestamp_for_filename()}"
    try:
        target.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            shutil.move(str(item), str(target / item.name))
        try:
            src.rmdir()
        except Exception:
            pass
        dbg(f"Session {session_id} uploads archived to {target.name}")
        return target
    except Exception as exc:  # noqa: BLE001
        add_error(f"Upload archive failed for {session_id}: {exc}")
        return None


def purge_expired(now: Optional[datetime] = None, retention_days: int = RETENTION_DAYS) -> int:
    """
    Delete archived files older than retention_days.
    Returns count of files removed.
    """
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=retention_days)
    removed = 0
    for file in ARCHIVE_DIR.glob("*.json"):
        try:
            mtime = datetime.utcfromtimestamp(file.stat().st_mtime)
            if mtime < cutoff:
                file.unlink()
                removed += 1
        except Exception:
            continue
    if removed:
        dbg(f"Purge removed {removed} archived session(s)")
    removed += purge_expired_uploads(now=now, retention_days=UPLOAD_RETENTION_DAYS)
    return removed


def purge_expired_uploads(
    now: Optional[datetime] = None, retention_days: int = UPLOAD_RETENTION_DAYS
) -> int:
    """
    Move uploaded files older than retention_days to Deleted_Data/uploads/.
    Returns count of files moved.
    """
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=retention_days)
    moved = 0
    if not UPLOADS_DIR.exists():
        return 0
    for session_dir in UPLOADS_DIR.iterdir():
        if not session_dir.is_dir():
            continue
        target_dir = UPLOAD_ARCHIVE_DIR / f"{session_dir.name}_{_timestamp_for_filename()}"
        target_dir.mkdir(parents=True, exist_ok=True)
        for file in session_dir.iterdir():
            try:
                mtime = datetime.utcfromtimestamp(file.stat().st_mtime)
                if mtime < cutoff:
                    shutil.move(str(file), str(target_dir / file.name))
                    moved += 1
            except Exception:
                continue
        # Remove empty session dirs.
        try:
            if not any(session_dir.iterdir()):
                session_dir.rmdir()
        except Exception:
            pass
    if moved:
        dbg(f"Purge moved {moved} uploaded file(s) to Deleted_Data/uploads")
    return moved


def delete_single_archived(session_id: str) -> bool:
    """
    Debug helper: delete the newest archived file for a session.
    Requires DEBUG_SINGLE_DELETE=1 to be set.
    """
    if os.environ.get("DEBUG_SINGLE_DELETE") != "1":
        add_error("DEBUG_SINGLE_DELETE not enabled; refusing single delete")
        return False

    matches = sorted(
        ARCHIVE_DIR.glob(f"{session_id}_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        dbg(f"No archived files to delete for {session_id}")
        return False
    try:
        matches[0].unlink()
        dbg(f"Archived session {session_id} deleted (single-file debug)")
        return True
    except Exception as exc:  # noqa: BLE001
        add_error(f"Single delete failed for {session_id}: {exc}")
        return False
