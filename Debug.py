from __future__ import annotations

import time
import os
import json
import atexit
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

# Simple opt-in console logging; controlled via env for noisier runs.
_debug_stdout_flag = "DEBUG_TO_STDOUT"

_current_state: dict | None = None
_debug_env_flag = "USE_DEBUG_SETTINGS"
_debug_force_key = "DEBUG_FORCE_MODEL"

# Internal guard so we only print flag summary once per process.
_flags_announced = False
LOG_ROOT = Path(__file__).with_name("Logs")
CRASH_ROOT = Path(__file__).with_name("Crashlog")
LOG_ROOT.mkdir(exist_ok=True)
CRASH_ROOT.mkdir(exist_ok=True)
ACTIVE_DIR = LOG_ROOT / "run_active"
_shutdown_reason = "Shutdown"


def _timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def _bootstrap_run_dir() -> Path:
    """
    Ensure we have a writable run directory:
    - If Logs/ doesn't exist, create it.
    - If Logs/run_active exists, reuse it (continuing the same run).
    - Otherwise, create Logs/run_active.
    """
    LOG_ROOT.mkdir(exist_ok=True)
    if ACTIVE_DIR.exists():
        # If there is no end marker, previous run likely crashed; archive it.
        if not (ACTIVE_DIR / "session_end.txt").exists():
            crash_target = CRASH_ROOT / f"crash_{_timestamp()}"
            try:
                ACTIVE_DIR.rename(crash_target)
            except Exception:
                pass
            try:
                print(f"[DEBUG:LOG] Previous run missing session_end.txt; moved to {crash_target}")
            except Exception:
                pass
        else:
            # Clean but unarchived folder: promote to "latest".
            latest_target = LOG_ROOT / "latest"
            if latest_target.exists():
                archived = LOG_ROOT / f"previous_{_timestamp()}"
                try:
                    latest_target.rename(archived)
                except Exception:
                    pass
            try:
                ACTIVE_DIR.rename(latest_target)
            except Exception:
                pass
    ACTIVE_DIR.mkdir(exist_ok=True)
    return ACTIVE_DIR


_run_dir = _bootstrap_run_dir()
_log_path = _run_dir / "Debug_log.json"


def _to_stdout() -> bool:
    return os.environ.get(_debug_stdout_flag, "1") != "0"


def _console(tag: str, message: str):
    if _to_stdout():
        try:
            colors = {
                "DATA": "\033[32m",   # green
                "FLAGS": "\033[32m",  # green
                "LOG": "\033[33m",    # yellow
                "ERROR": "\033[31m",  # red
                "TIME": "\033[36m",   # cyan
                "FETCH": "\033[35m",  # magenta
                "PROMPT": "\033[34m", # blue
                "EVIDENCE": "\033[34m", # blue
            }
            color = colors.get(tag, "")
            reset = "\033[0m" if color else ""
            print(f"{color}[DEBUG:{tag}] {message}{reset}")
        except BrokenPipeError:
            # Avoid crashing when stdout is a closed pipe (e.g., tee stopped).
            try:
                os.environ[_debug_stdout_flag] = "0"
            except Exception:
                pass


def _maybe_state():
    try:
        return get_state()
    except RuntimeError:
        return None


def _ensure_debug_keys(state: dict):
    state.setdefault("dbg_log", [])
    state.setdefault("dbg_timings", [])
    state.setdefault("dbg_errors", [])
    state.setdefault("dbg_fetches", [])
    state.setdefault("dbg_evidence", "")
    state.setdefault("dbg_prompt", "")
    state.setdefault("dbg_data", {})


def _session_id():
    state = _maybe_state()
    return state.get("session_id") if state else None


def _log_flag(flag: str):
    """
    Persist a debug flag event to Debug_log.json with session id and timestamp.
    """
    try:
        sid = _session_id()
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "Debugflag": flag,
        }
        if sid:
            entry["Session id"] = sid
        existing = []
        if _log_path.exists():
            try:
                existing = json.loads(_log_path.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []
        existing.append(entry)
        _log_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # Never let logging break runtime behavior.
        pass


def attach_state(state: dict):
    """Point debug helpers at the active session state."""
    global _current_state
    _current_state = state


def get_state() -> dict:
    if _current_state is None:
        raise RuntimeError("Debug state is not attached")
    return _current_state


def init_debug(state: dict):
    attach_state(state)
    state.setdefault("dbg_log", [])
    state.setdefault("dbg_timings", [])
    state.setdefault("dbg_errors", [])
    state.setdefault("dbg_fetches", [])
    state.setdefault("dbg_evidence", "")
    state.setdefault("dbg_prompt", "")
    state.setdefault("dbg_data", {})
    log_active_flags()


def dbg(message: str):
    state = _maybe_state()
    if state is not None:
        _ensure_debug_keys(state)
        state["dbg_log"].append({"timestamp": _timestamp(), "log": message})
    _console("LOG", message)
    _log_flag(f"dbg: {message}")


def set_debug(key: str, value):
    state = _maybe_state()
    if state is not None:
        _ensure_debug_keys(state)
        state["dbg_data"][key] = value
    _console("DATA", f"{key} -> {value}")
    _log_flag(f"set_debug {key}")


def add_error(message: str):
    state = _maybe_state()
    if state is not None:
        _ensure_debug_keys(state)
        state["dbg_errors"].append(f"{_timestamp()};{message}")
    _console("ERROR", message)
    _log_flag(f"error: {message}")


def add_timing(label: str, seconds: float):
    state = _maybe_state()
    if state is not None:
        _ensure_debug_keys(state)
        state["dbg_timings"].append(
            {"timestamp": _timestamp(), "label": label, "seconds": seconds}
        )
    _console("TIME", f"{label} = {seconds:.3f}s")
    _log_flag(f"timing {label}={seconds:.3f}s")


def add_fetch(url: str, error: str | None):
    state = _maybe_state()
    if state is not None:
        _ensure_debug_keys(state)
        state["dbg_fetches"].append(
            {"timestamp": _timestamp(), "url": url, "error": error}
        )
    status = "ok" if not error else f"error: {error}"
    _console("FETCH", f"{url} ({status})")
    _log_flag(f"fetch {url} {status}")


def set_evidence(text: str):
    state = _maybe_state()
    if state is not None:
        _ensure_debug_keys(state)
        state["dbg_evidence"] = f"{_timestamp()};{text}"
    _console("EVIDENCE", f"len={len(text)}")
    _log_flag("evidence set")


def set_prompt(text: str):
    state = _maybe_state()
    if state is not None:
        _ensure_debug_keys(state)
        state["dbg_prompt"] = f"{_timestamp()};{text}"
    _console("PROMPT", f"chars={len(text)}")
    _log_flag("prompt set")


@contextmanager
def status(label: str):
    """Lightweight status context that records duration."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        add_timing(label, elapsed)


def enable_debug_settings(force_model: str | None = None):
    """
    Opt-in to reading DebugSettings.py at runtime.
    Optionally set a temporary forced model ("local", "cloud", or a model tag).
    """
    os.environ[_debug_env_flag] = "1"
    if force_model:
        os.environ[_debug_force_key] = force_model


def disable_debug_settings():
    """Stop reading DebugSettings.py overrides."""
    os.environ.pop(_debug_env_flag, None)
    os.environ.pop(_debug_force_key, None)


def debug_settings_enabled() -> bool:
    return os.environ.get(_debug_env_flag) == "1"


def get_forced_model_env() -> str | None:
    return os.environ.get(_debug_force_key)


def active_flags() -> dict:
    """Return a snapshot of debug-related environment toggles."""
    return {
        "use_debug_settings": debug_settings_enabled(),
        "forced_model_env": get_forced_model_env(),
        "debug_to_stdout": _to_stdout(),
    }


def log_active_flags():
    """Print the debug flag status once per process."""
    global _flags_announced
    if _flags_announced:
        return
    _flags_announced = True
    flags = active_flags()
    _console(
        "FLAGS",
        ", ".join(f"{k}={v}" for k, v in flags.items()),
    )
    _log_flag("flags: " + ", ".join(f"{k}={v}" for k, v in flags.items()))


def _on_exit():
    try:
        end_ts = _timestamp()
        (ACTIVE_DIR / "session_end.txt").write_text(
            f"Session ended at {datetime.utcnow().isoformat()}Z\n"
            f"Reason: {_shutdown_reason}\n",
            encoding="utf-8",
        )
        reason_slug = _shutdown_reason.lower().replace(" ", "_")
        latest_target = LOG_ROOT / f"latest_{reason_slug}"
        if latest_target.exists():
            archived = LOG_ROOT / f"previous_{end_ts}"
            try:
                latest_target.rename(archived)
            except Exception:
                pass
        try:
            ACTIVE_DIR.rename(latest_target)
        except Exception:
            pass
    except Exception:
        pass


def set_shutdown_reason(reason: str):
    """Set the label written at shutdown; e.g., 'Shutdown', 'Restarted'."""
    global _shutdown_reason
    _shutdown_reason = reason or "Shutdown"


atexit.register(_on_exit)
