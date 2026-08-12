"""Optional remote monitoring hooks.

The generated system can run without a dashboard/log collector. These helpers
therefore default to no-op behavior and only forward events after an explicit
monitoring client is configured.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

_logger = logging.getLogger(__name__)
_monitoring_enabled = False


def init_monitoring(*, server_url: str, source: str | None = None) -> None:
    global _monitoring_enabled
    _monitoring_enabled = bool(server_url)
    if _monitoring_enabled:
        _logger.info("monitoring configured", extra={"source": source or ""})


def start_heartbeat(interval_seconds: int | float = 30) -> None:
    if _monitoring_enabled:
        _logger.info("monitoring heartbeat enabled", extra={"interval": interval_seconds})


def stop_heartbeat() -> None:
    if _monitoring_enabled:
        _logger.info("monitoring heartbeat stopped")


def report_user_action(
    *,
    action: str,
    state: str = "success",
    describe: str = "",
    level: str = "INFO",
    **metadata: Any,
) -> None:
    if not _monitoring_enabled:
        return
    log_level = getattr(logging, str(level or "INFO").upper(), logging.INFO)
    _logger.log(
        log_level,
        "user action",
        extra={"action": action, "state": state, "describe": describe, **metadata},
    )


def make_structlog_processor(min_level: str = "WARNING") -> Callable[..., Any]:
    def _processor(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        return event_dict

    return _processor
