"""
logs-ops-kit monitoring — always-on local persistence.

Overrides the platform-core-kit no-op. Every report_user_action call and
every structlog WARNING+ event is persisted to system_logs without blocking
async route handlers. Uses a daemon background thread + queue so callers
never wait on I/O.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------
_log_queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=2000)
_worker_thread: threading.Thread | None = None
_running = False
_initialized = False
_init_lock = threading.Lock()

# ---------------------------------------------------------------------------
# DDL — database-agnostic (SQLite uses TEXT timestamps; PG uses TIMESTAMPTZ)
# ---------------------------------------------------------------------------
_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS system_logs (
    id              TEXT        PRIMARY KEY,
    timestamp       TEXT        NOT NULL,
    log_type        TEXT        NOT NULL,
    level           TEXT        NOT NULL,
    action          TEXT        NOT NULL,
    state           TEXT        NOT NULL,
    describe        TEXT        NOT NULL DEFAULT '',
    metadata_json   TEXT        NOT NULL DEFAULT '{}',
    created_at      TEXT        NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
)
"""

_DDL_PG = """
CREATE TABLE IF NOT EXISTS system_logs (
    id              TEXT        PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL,
    log_type        TEXT        NOT NULL,
    level           TEXT        NOT NULL,
    action          TEXT        NOT NULL,
    state           TEXT        NOT NULL,
    describe        TEXT        NOT NULL DEFAULT '',
    metadata_json   TEXT        NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

_INSERT_SQL = """
INSERT INTO system_logs (id, timestamp, log_type, level, action, state, describe, metadata_json)
VALUES (:id, :timestamp, :log_type, :level, :action, :state, :describe, :metadata_json)
"""


# ---------------------------------------------------------------------------
# Background writer
# ---------------------------------------------------------------------------

def _to_sync_url(async_url: str) -> str:
    return async_url.replace("+asyncpg", "").replace("+aiosqlite", "")


def _worker_loop(session_factory: Any) -> None:
    global _running
    while True:
        try:
            entry = _log_queue.get(timeout=1.0)
        except queue.Empty:
            if not _running:
                break
            continue
        if entry is None:
            break
        try:
            from sqlalchemy import text
            with session_factory() as session:
                session.execute(text(_INSERT_SQL), entry)
                session.commit()
        except Exception as exc:  # noqa: BLE001
            _logger.debug("system_logs write failed: %s", exc)


def _do_init(db_url: str) -> None:
    global _worker_thread, _running
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    sync_url = _to_sync_url(db_url)
    is_pg = sync_url.startswith("postgresql")
    ddl = _DDL_PG if is_pg else _DDL_SQLITE

    try:
        engine = create_engine(sync_url, echo=False, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text(ddl))
            conn.commit()
        factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        _running = True
        _worker_thread = threading.Thread(
            target=_worker_loop,
            args=(factory,),
            daemon=True,
            name="monitoring-writer",
        )
        _worker_thread.start()
        _logger.info("monitoring: system_logs writer started (db=%s)", sync_url.split("@")[-1])
    except Exception as exc:
        _logger.error("monitoring: init failed — logs will not be persisted: %s", exc)


def _ensure_initialized() -> None:
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        _initialized = True
        try:
            from app.core.config import get_settings
            db_url = get_settings().database_url
        except Exception as exc:
            _logger.warning("monitoring: could not read settings, logs will not be persisted: %s", exc)
            return
        _do_init(db_url)


def _enqueue(entry: dict[str, Any]) -> None:
    try:
        _log_queue.put_nowait(entry)
    except queue.Full:
        _logger.debug("monitoring: log queue full, entry dropped")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Public API — identical interface to platform-core-kit no-op
# ---------------------------------------------------------------------------

def init_monitoring(*, server_url: str = "", source: str | None = None) -> None:
    """Called from app/main.py on startup. Forces immediate DB init."""
    _ensure_initialized()
    if source:
        _enqueue({
            "id": str(uuid.uuid4()),
            "timestamp": _now_iso(),
            "log_type": "system",
            "level": "INFO",
            "action": "monitoring_init",
            "state": "success",
            "describe": f"source={source}",
            "metadata_json": json.dumps({"source": source, "server_url": server_url}),
        })


def start_heartbeat(interval_seconds: int | float = 30) -> None:
    _ensure_initialized()
    _enqueue({
        "id": str(uuid.uuid4()),
        "timestamp": _now_iso(),
        "log_type": "system",
        "level": "INFO",
        "action": "heartbeat_start",
        "state": "success",
        "describe": f"interval={interval_seconds}s",
        "metadata_json": json.dumps({"interval_seconds": interval_seconds}),
    })


def stop_heartbeat() -> None:
    _enqueue({
        "id": str(uuid.uuid4()),
        "timestamp": _now_iso(),
        "log_type": "system",
        "level": "INFO",
        "action": "heartbeat_stop",
        "state": "success",
        "describe": "heartbeat stopped at shutdown",
        "metadata_json": "{}",
    })
    global _running
    _running = False


def report_user_action(
    *,
    action: str,
    state: str = "success",
    describe: str = "",
    level: str = "INFO",
    **metadata: Any,
) -> None:
    _ensure_initialized()
    log_level_int = getattr(logging, str(level or "INFO").upper(), logging.INFO)
    _logger.log(
        log_level_int,
        "user_action action=%s state=%s",
        action,
        state,
        extra={"action": action, "state": state, "describe": describe, **metadata},
    )
    _enqueue({
        "id": str(uuid.uuid4()),
        "timestamp": _now_iso(),
        "log_type": "user_action",
        "level": str(level or "INFO").upper(),
        "action": action,
        "state": state,
        "describe": describe,
        "metadata_json": json.dumps(metadata, default=str),
    })


def make_structlog_processor(min_level: str = "WARNING") -> Callable[..., Any]:
    """
    Structlog processor that persists WARNING+ events to system_logs.
    Returned processor is called by app/core/logging.py during setup.
    """
    _min = getattr(logging, str(min_level or "WARNING").upper(), logging.WARNING)

    def _processor(
        logger: Any, method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        level_name = str(method_name or "").upper()
        level_int = getattr(logging, level_name, logging.DEBUG)
        if level_int >= _min:
            event = str(event_dict.get("event", ""))
            has_exc = bool(event_dict.get("exc_info") or event_dict.get("exception"))
            _ensure_initialized()
            log_type = "system_error" if level_int >= logging.ERROR else "system_warning"
            _enqueue({
                "id": str(uuid.uuid4()),
                "timestamp": _now_iso(),
                "log_type": log_type,
                "level": level_name,
                "action": "structlog_event",
                "state": "error" if has_exc else "warning",
                "describe": event,
                "metadata_json": json.dumps(
                    {k: str(v) for k, v in event_dict.items()
                     if k not in ("event", "exc_info", "exception", "_record")},
                    default=str,
                ),
            })
        return event_dict

    return _processor
