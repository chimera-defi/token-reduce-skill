"""Best-effort central telemetry; no subprocesses or import-time I/O."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

_MODEL_CACHE: dict[str, str] = {}


def central_path() -> Path | None:
    try:
        value = os.environ.get("TOKEN_REDUCE_CENTRAL_EVENTS")
        if value is not None:
            if value.strip().lower() in {"off", "0", ""}:
                return None
            return Path(value).expanduser()
        return Path.home() / ".local" / "share" / "token-reduce" / "events.jsonl"
    except Exception:
        return None


def append_line(obj: dict) -> None:
    """Append one JSON line with one O_APPEND write, or silently give up."""
    fd = None
    try:
        path = central_path()
        if path is None:
            return
        line = (json.dumps(obj, sort_keys=True) + "\n").encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        os.write(fd, line)
    except Exception:
        pass
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass


def session_hash(data: dict) -> str:
    try:
        value = data.get("session_id") or data.get("transcript_path")
        if value:
            return hashlib.sha1(str(value).encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    except Exception:
        pass
    return "none"


def detect_model(data: dict) -> str:
    try:
        model = os.environ.get("CLAUDE_SESSION_MODEL") or os.environ.get("ANTHROPIC_MODEL")
        if model:
            return model
        model = data.get("model")
        if isinstance(model, str):
            return model
        session = session_hash(data)
        if session != "none" and session in _MODEL_CACHE:
            return _MODEL_CACHE[session]
        model = "unknown"
        try:
            with open(data["transcript_path"], "rb") as handle:
                handle.seek(0, os.SEEK_END)
                handle.seek(max(0, handle.tell() - 64 * 1024))
                tail = handle.read(64 * 1024)
            for line in reversed(tail.splitlines()):
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        continue
                    message = row.get("message")
                    candidate = message.get("model") if isinstance(message, dict) else None
                    if not isinstance(candidate, str):
                        candidate = row.get("model")
                    if isinstance(candidate, str):
                        model = candidate
                        break
                except Exception:
                    continue
        except Exception:
            pass
        if session != "none":
            _MODEL_CACHE[session] = model
        return model
    except Exception:
        return "unknown"


def detect_lane(data: dict) -> str:
    try:
        if "TOKEN_REDUCE_LANE" in os.environ:
            return os.environ["TOKEN_REDUCE_LANE"]
        return "subagent" if data.get("agent_id") or data.get("agent_type") else "main"
    except Exception:
        return "main"


def log_call(data: dict, *, advised: bool = False, rule: str | None = None,
             extra: dict | None = None, event: str = "hook_call") -> None:
    try:
        path = central_path()
        if path is None:
            return
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "tool": data.get("tool_name"),
            "model": detect_model(data),
            "lane": detect_lane(data),
            "session": session_hash(data),
            "advised": bool(advised),
            "rule": str(rule) if rule is not None else None,
            "project": Path(data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or "").name,
            "hook_event": data.get("hook_event_name"),
            "client": os.environ.get("CLAUDE_CODE_ENTRYPOINT", ""),
            "source": "hook",
        }
        if extra:
            payload.update(extra)
        append_line(payload)
        # Names only: neither session identifiers nor tool-input values escape.
        # Exclusive creation also prevents concurrent first sightings clobbering it.
        hook_event = re.sub(r"[^A-Za-z0-9_.-]", "_", str(data.get("hook_event_name") or "unknown"))[:100]
        tool = re.sub(r"[^A-Za-z0-9_.-]", "_", str(data.get("tool_name") or "unknown"))[:100]
        keys_path = path.parent / f"payload-keys-{hook_event}-{tool}.json"
        if not keys_path.exists():
            with keys_path.open("x", encoding="utf-8") as handle:
                json.dump(sorted(data), handle)
                handle.write("\n")
    except Exception:
        pass
