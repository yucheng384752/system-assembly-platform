"""Deployed-instance endpoint permission overrides.

Lets a system-admin at a customer deployment restrict specific API paths to a role
without a code change: edit backend/app/config/endpoint_permissions.json (or point
ENDPOINT_PERMISSIONS_FILE at another path) and the next request picks it up — no
restart required. Missing/malformed file = no extra restrictions (same behavior as
before this feature existed).

Config shape: {"<path-prefix>": "<role>"}. "<role>" is either "system-admin"
(request.state.is_admin, set via ADMIN_API_KEYS) or a TenantUser.role value
(e.g. "manager"). The longest matching prefix wins.

Enforced by endpoint_permission_middleware.py. Read/write via
GET/PUT /api/admin/endpoint-permissions (routes_admin_permissions.py, system-admin only).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_DEFAULT_PATH = Path(__file__).resolve().parents[1] / "config" / "endpoint_permissions.json"

_cache: dict[str, str] = {}
_cache_mtime: float | None = None
_cache_path: Path | None = None


def config_path() -> Path:
    override = os.environ.get("ENDPOINT_PERMISSIONS_FILE")
    return Path(override) if override else _DEFAULT_PATH


def _load(path: Path) -> dict[str, str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f" Warning: failed to read endpoint permissions config ({path}): {exc}")
        return {}
    if not isinstance(raw, dict):
        print(f" Warning: endpoint permissions config ({path}) is not a JSON object, ignoring")
        return {}
    return {str(k): str(v) for k, v in raw.items() if k and v}


def get_permission_map() -> dict[str, str]:
    """Current path-prefix -> required-role map, reloaded whenever the file's mtime changes."""
    global _cache, _cache_mtime, _cache_path
    path = config_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    if path != _cache_path or mtime != _cache_mtime:
        _cache = _load(path)
        _cache_mtime = mtime
        _cache_path = path
    return _cache


def get_required_role(request_path: str) -> str | None:
    """Longest-prefix-matching required role for request_path, or None if unrestricted."""
    best_prefix = ""
    best_role: str | None = None
    for prefix, role in get_permission_map().items():
        if request_path.startswith(prefix) and len(prefix) > len(best_prefix):
            best_prefix = prefix
            best_role = role
    return best_role
