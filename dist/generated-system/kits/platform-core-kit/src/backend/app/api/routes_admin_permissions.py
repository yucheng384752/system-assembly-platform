"""
platform-core-kit: deployed-instance endpoint permission admin API.

Routes:
  GET /api/admin/endpoint-permissions   current path-prefix -> required-role overrides
  PUT /api/admin/endpoint-permissions   replace the override map

Access control: system-admin only (request.state.is_admin, set via ADMIN_API_KEYS /
X-Admin-API-Key). Lets a customer deployment restrict endpoints beyond the kit
defaults without a code change/redeploy — see core/permission_config.py and
core/endpoint_permission_middleware.py for how the config is read and enforced.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request, status

from app.core.permission_config import config_path, get_permission_map

router = APIRouter(tags=["Admin"])


def _require_system_admin(request: Request) -> None:
    is_admin = bool(getattr(getattr(request, "state", None), "is_admin", False))
    if not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="system-admin only")


@router.get("/api/admin/endpoint-permissions")
async def get_endpoint_permissions(request: Request) -> dict[str, Any]:
    _require_system_admin(request)
    return {"path": str(config_path()), "permissions": get_permission_map()}


@router.put("/api/admin/endpoint-permissions")
async def put_endpoint_permissions(
    request: Request, body: dict[str, str] = Body(...)
) -> dict[str, Any]:
    """body: {"<path-prefix>": "<role>"}. "<role>" is "system-admin" or a
    TenantUser.role value (e.g. "manager"). Empty body clears all overrides."""
    _require_system_admin(request)
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    for prefix, role in body.items():
        if not isinstance(prefix, str) or not prefix.startswith("/"):
            raise HTTPException(
                status_code=400,
                detail=f"invalid path prefix (must start with '/'): {prefix!r}",
            )
        if not isinstance(role, str) or not role.strip():
            raise HTTPException(status_code=400, detail=f"invalid role for {prefix!r}: {role!r}")

    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(path), "permissions": get_permission_map()}
