"""Best-effort audit event writer.

Called from multiple write-path routes/services (app/api/routes_upload.py,
app/api/routes_import_v2.py, app/api/routes_auth.py, app/services/import_v2.py) to
record a durable AuditEvent row. Never raises: audit write failures must not fail
the caller's request.
"""

from __future__ import annotations

from typing import Any


async def write_audit_event_best_effort(
    *,
    tenant_id: Any = None,
    actor_api_key_id: Any = None,
    actor_label_snapshot: str | None = None,
    request_id: str | None = None,
    method: str | None = None,
    path: str | None = None,
    status_code: int | None = None,
    action: str | None = None,
    metadata: dict[str, Any] | None = None,
    client_host: str | None = None,
    user_agent: str | None = None,
    **_: Any,
) -> None:
    try:
        from app.core.database import async_session_factory
        from app.models.core.audit_event import AuditEvent

        if async_session_factory is None:
            return

        async with async_session_factory() as db:
            db.add(
                AuditEvent(
                    tenant_id=tenant_id,
                    actor_api_key_id=actor_api_key_id,
                    actor_label_snapshot=actor_label_snapshot,
                    request_id=request_id,
                    method=method or "INTERNAL",
                    path=path or "",
                    status_code=status_code or 0,
                    action=action or "unknown",
                    metadata_json=metadata,
                    client_host=client_host,
                    user_agent=user_agent,
                )
            )
            await db.commit()
    except Exception:
        # Best-effort: audit write failures must never fail the caller's request.
        return
