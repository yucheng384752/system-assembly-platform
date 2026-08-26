"""Heartbeat-only client for the optional remote monitor service."""
from __future__ import annotations

import logging
import socket
from datetime import datetime, timezone

import httpx

_logger = logging.getLogger(__name__)


class LogCollectClient:
    def __init__(self, server_url: str, source: str) -> None:
        self.server_url = server_url
        self.source = source

    def send_heartbeat(self, state: str = "alive") -> bool:
        payload = {
            "source": self.source,
            "host": socket.gethostname(),
            "state": state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            response = httpx.post(self.server_url, json=payload, timeout=5.0)
            response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            _logger.warning("remote heartbeat failed: %s", exc)
            return False
