import json
from pathlib import Path
from typing import Dict, Optional
import uuid

from fastapi import HTTPException

from Config import apply_defaults

# In-memory cache; persists to disk under sessions/*.json
STATE: Dict[str, dict] = {}
SESSIONS_DIR = Path(__file__).with_name("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)


def _sanitize_session_id(session_id: str) -> str:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
    return safe or "default"


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{_sanitize_session_id(session_id)}.json"


def load_session(session_id: str) -> dict:
    """Load a session from disk if present; otherwise return a fresh state."""
    path = _session_path(session_id)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:  # noqa: BLE001
            pass
    return {}


def save_session(session_id: str, state: dict) -> None:
    """Persist session state to disk (atomic write)."""
    path = _session_path(session_id)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to save session {session_id}: {exc}")


def get_state(session_id: str) -> dict:
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    if session_id not in STATE:
        STATE[session_id] = load_session(session_id)
    state = STATE[session_id]
    apply_defaults(state)
    save_session(session_id, state)
    return state


def list_session_ids() -> list[str]:
    disk_sessions = {p.stem for p in SESSIONS_DIR.glob("*.json")}
    memory_sessions = set(STATE.keys())
    return sorted(disk_sessions | memory_sessions)


def delete_session(session_id: str) -> str:
    sid = _sanitize_session_id(session_id)
    STATE.pop(sid, None)
    path = _session_path(sid)
    if path.exists():
        path.unlink()
    return sid


def create_session(session_id: Optional[str] = None) -> str:
    """Create a new session (empty) and persist it."""
    sid = _sanitize_session_id(session_id or uuid.uuid4().hex)
    if sid not in STATE:
        STATE[sid] = {}
    apply_defaults(STATE[sid])
    save_session(sid, STATE[sid])
    return sid
