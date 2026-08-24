"""Deployed-instance endpoint permission enforcement.

Registered generically via backend_middleware_registry.py (see
tools/generate-backend-middleware-registry.ps1), which platform-core-kit's manifest
(backend.middlewareRegistrations) declares. Kit-contributed middlewares are added to
the app after main.py's own api_key_auth_middleware/audit_events_middleware, so they
run as the innermost layer — request.state.is_admin / actor_role are already resolved
by the time this runs. See backend_middleware_registry.py's register_backend_middlewares
for the ordering note.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.permission_config import get_required_role


async def endpoint_permission_middleware(request: Request, call_next):
    required_role = get_required_role(request.url.path)
    if required_role:
        state = getattr(request, "state", None)
        is_admin = bool(getattr(state, "is_admin", False))
        actor_role = getattr(state, "actor_role", None)
        allowed = is_admin or (required_role != "system-admin" and actor_role == required_role)
        if not allowed:
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)
