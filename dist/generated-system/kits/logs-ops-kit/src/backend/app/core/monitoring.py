"""
logs-ops-kit monitoring — local persistence plus optional remote heartbeat.

Overrides the platform-core-kit no-op. Every report_user_action call and
every structlog WARNING+ event is persisted to system_logs without blocking
async route handlers. Uses a daemon background thread + queue so callers
never wait on I/O. Remote heartbeat is disabled unless init_monitoring receives
a non-empty server URL; user actions and structlog events are never forwarded.
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
_monitor_client: Any = None
_heartbeat_thread: threading.Thread | None = None
_heartbeat_stop = threading.Event()
_heartbeat_lock = threading.Lock()

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
    tenant_id       TEXT        NULL,
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
    tenant_id       TEXT        NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

# Best-effort migration for tables created before tenant_id existed. SQLite/PG both accept
# bare ADD COLUMN; neither reliably supports "IF NOT EXISTS" for it (PG needs 9.6+, SQLite never
# does), so the caller must swallow the "column already exists" error on a second run.
_ALTER_ADD_TENANT_ID = "ALTER TABLE system_logs ADD COLUMN tenant_id TEXT"

_INSERT_SQL = """
INSERT INTO system_logs (id, timestamp, log_type, level, action, state, describe, metadata_json, tenant_id)
VALUES (:id, :timestamp, :log_type, :level, :action, :state, :describe, :metadata_json, :tenant_id)
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
        try:
            # Separate connection/transaction: a pre-existing table (created before tenant_id
            # existed) makes this fail with "column already exists" — that failure must not
            # abort the CREATE TABLE transaction above, which already committed successfully.
            with engine.connect() as conn:
                conn.execute(text(_ALTER_ADD_TENANT_ID))
                conn.commit()
        except Exception:
            pass
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
    """Initialize local persistence and the opt-in heartbeat client."""
    global _monitor_client
    _ensure_initialized()
    if server_url:
        from app.core.log_client import LogCollectClient

        _monitor_client = LogCollectClient(server_url, source or "form-analysis-server")
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
            "tenant_id": None,  # platform-level lifecycle event, not attributable to a tenant
        })


def start_heartbeat(interval_seconds: int | float = 30) -> None:
    """Start remote heartbeat delivery when a monitor client is configured."""
    global _heartbeat_thread
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
        "tenant_id": None,
    })
    if _monitor_client is None:
        return

    interval = max(float(interval_seconds), 1.0)
    with _heartbeat_lock:
        if _heartbeat_thread and _heartbeat_thread.is_alive():
            return
        _heartbeat_stop.clear()

        def _heartbeat_loop() -> None:
            while not _heartbeat_stop.is_set():
                _monitor_client.send_heartbeat()
                _heartbeat_stop.wait(interval)

        _heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            daemon=True,
            name="remote-heartbeat",
        )
        _heartbeat_thread.start()


def stop_heartbeat() -> None:
    """Stop remote heartbeat delivery and the local shutdown writer."""
    global _heartbeat_thread, _running
    _heartbeat_stop.set()
    if _heartbeat_thread and _heartbeat_thread.is_alive():
        _heartbeat_thread.join(timeout=5.0)
    _heartbeat_thread = None
    _enqueue({
        "id": str(uuid.uuid4()),
        "timestamp": _now_iso(),
        "log_type": "system",
        "level": "INFO",
        "action": "heartbeat_stop",
        "state": "success",
        "describe": "heartbeat stopped at shutdown",
        "metadata_json": "{}",
        "tenant_id": None,
    })
    _running = False


def report_user_action(
    *,
    action: str,
    state: str = "success",
    describe: str = "",
    level: str = "INFO",
    **metadata: Any,
) -> None:
    # tenant_id is not a formal parameter so this keeps the exact signature of the
    # platform-core-kit no-op it overrides — callers that want the row attributed to a
    # tenant pass tenant_id=tenant.id like any other metadata kwarg; it is pulled out of
    # metadata_json into its own column here instead of staying buried in JSON.
    tenant_id = metadata.pop("tenant_id", None)
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
        "tenant_id": str(tenant_id) if tenant_id is not None else None,
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
            # Most log lines have no request/tenant context (startup, background workers).
            # Pick up tenant_id only if something upstream already bound it into the event
            # dict (e.g. a future structlog contextvars binding in request middleware);
            # otherwise the row is platform-level and stays unattributed rather than guessed.
            tenant_id = event_dict.get("tenant_id")
            _enqueue({
                "id": str(uuid.uuid4()),
                "timestamp": _now_iso(),
                "log_type": log_type,
                "level": level_name,
                "action": "structlog_event",
                "state": "error" if has_exc else "warning",
                "describe": event,
                "tenant_id": str(tenant_id) if tenant_id is not None else None,
                "metadata_json": json.dumps(
                    {k: str(v) for k, v in event_dict.items()
                     if k not in ("event", "exc_info", "exception", "_record", "tenant_id")},
                    default=str,
                ),
            })
        return event_dict

    return _processor
