"""Best-effort audit event writer.

Generated packages may reference audit hooks even when persistent audit models are
not selected. Keep those hooks non-blocking in that configuration.
"""

from typing import Any


async def write_audit_event_best_effort(**_: Any) -> None:
    return None
