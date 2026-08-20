from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_capabilities import DB_CAPABILITIES
from app.core.kit_contracts import capability_index, load_kit_contracts


async def call_capability(
    capability: str,
    *,
    db: AsyncSession,
    tenant_id: Any | None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    index = capability_index()
    entry = index.get(capability)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Unknown kit capability: {capability}")

    if capability in DB_CAPABILITIES:
        safe_payload = {k: v for k, v in payload.items() if k not in ("db", "tenant_id")}
        data = await DB_CAPABILITIES[capability](db=db, tenant_id=tenant_id, **safe_payload)
        return {"capability": capability, "kind": "db", "data": data}

    if entry.get("kind") == "api":
        return {
            "capability": capability,
            "kind": "api",
            "kit": entry.get("kit"),
            "method": entry.get("method"),
            "path": entry.get("path"),
            "message": "Use method/path for direct API calls or add a broker adapter for this capability.",
        }

    raise HTTPException(status_code=501, detail=f"No runtime adapter for capability: {capability}")


def list_contracts() -> dict[str, Any]:
    return {
        "contracts": load_kit_contracts(),
        "capabilities": sorted(capability_index().values(), key=lambda item: item["capability"]),
    }
