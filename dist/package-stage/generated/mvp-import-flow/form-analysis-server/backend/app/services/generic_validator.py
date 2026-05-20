"""Generic validator — config-driven replacement for hardcoded validation rules."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.station import Station
from app.models.validation_rule import ValidationRule


class GenericValidator:
    """Validates record data against rules stored in the validation_rules table."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def validate(
        self,
        tenant_id: UUID,
        station_code: str,
        data: dict[str, Any],
    ) -> list[dict[str, str]]:
        """Validate *data* against all active rules for *station_code*.

        Returns a list of ``{"field", "code", "message"}`` dicts (empty = valid).
        """
        station = (
            await self.session.execute(
                select(Station).where(
                    Station.tenant_id == tenant_id,
                    Station.code == station_code,
                )
            )
        ).scalar_one_or_none()

        station_id = station.id if station else None

        stmt = select(ValidationRule).where(
            ValidationRule.tenant_id == tenant_id,
            ValidationRule.is_active == True,
        )
        if station_id is not None:
            stmt = stmt.where(
                or_(
                    ValidationRule.station_id == station_id,
                    ValidationRule.station_id.is_(None),
                )
            )
        else:
            stmt = stmt.where(ValidationRule.station_id.is_(None))

        rules = list((await self.session.execute(stmt)).scalars().all())
        return _apply_rules(rules, data)


def _apply_rules(
    rules: list[ValidationRule], data: dict[str, Any]
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []

    for rule in rules:
        value = data.get(rule.field_name)
        cfg = rule.rule_config or {}

        if rule.rule_type == "required" and value is None:
            errors.append(
                {
                    "field": rule.field_name,
                    "code": "REQUIRED",
                    "message": f"{rule.field_name} is required",
                }
            )

        elif rule.rule_type == "enum" and value is not None:
            allowed = cfg.get("values", [])
            if value not in allowed:
                errors.append(
                    {
                        "field": rule.field_name,
                        "code": "INVALID_ENUM",
                        "message": f"{rule.field_name} must be one of {allowed}",
                    }
                )

        elif rule.rule_type == "range" and value is not None:
            try:
                v = float(value)
                lo, hi = cfg.get("min"), cfg.get("max")
                if lo is not None and v < lo:
                    errors.append(
                        {
                            "field": rule.field_name,
                            "code": "OUT_OF_RANGE",
                            "message": f"{rule.field_name} below min {lo}",
                        }
                    )
                if hi is not None and v > hi:
                    errors.append(
                        {
                            "field": rule.field_name,
                            "code": "OUT_OF_RANGE",
                            "message": f"{rule.field_name} above max {hi}",
                        }
                    )
            except (ValueError, TypeError):
                pass

        elif rule.rule_type == "regex" and value is not None:
            pattern = cfg.get("pattern", "")
            if pattern and not re.match(pattern, str(value)):
                errors.append(
                    {
                        "field": rule.field_name,
                        "code": "INVALID_FORMAT",
                        "message": f"{rule.field_name} does not match pattern {pattern}",
                    }
                )

    return errors
