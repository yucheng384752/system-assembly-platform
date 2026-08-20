from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.kit_broker import call_capability, list_contracts

router = APIRouter()


class CapabilityCall(BaseModel):
    payload: dict[str, Any] | None = None


@router.get("/contracts")
async def get_contracts() -> dict[str, Any]:
    return list_contracts()


@router.post("/call/{capability:path}")
async def post_capability(
    capability: str,
    body: CapabilityCall,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    tenant_id = getattr(request.state, "tenant_id", None) or getattr(request.state, "auth_tenant_id", None)
    return await call_capability(capability, db=db, tenant_id=tenant_id, payload=body.payload)
