"""
Custom middleware for request processing.

Provides request ID generation, logging, timing, and error handling.
"""

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for request logging and timing.

    Adds request ID, logs requests/responses, and tracks processing time.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """
        Process request with logging and timing.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/route handler

        Returns:
            Response: HTTP response with additional headers
        """
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Best-effort actor/tenant context (may be populated later in the request lifecycle)
        tenant_id = getattr(getattr(request, "state", None), "tenant_id", None)
        tenant_code = getattr(getattr(request, "state", None), "tenant_code", None)
        auth_tenant_id = getattr(
            getattr(request, "state", None), "auth_tenant_id", None
        )
        auth_api_key_id = getattr(
            getattr(request, "state", None), "auth_api_key_id", None
        )
        auth_api_key_label = getattr(
            getattr(request, "state", None), "auth_api_key_label", None
        )

        # Start timing
        start_time = time.time()

        # Log incoming request
        logger.info(
            "Request started",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            query_params=str(request.query_params),
            client_host=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            tenant_id=str(tenant_id) if tenant_id else None,
            tenant_code=tenant_code,
            auth_tenant_id=str(auth_tenant_id) if auth_tenant_id else None,
            actor_api_key_id=str(auth_api_key_id) if auth_api_key_id else None,
            actor_api_key_label=auth_api_key_label,
        )

        try:
            # Process request
            response = await call_next(request)

            # Calculate processing time
            process_time = time.time() - start_time

            # Add custom headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(process_time)

            # Log response
            tenant_id = getattr(getattr(request, "state", None), "tenant_id", None)
            tenant_code = getattr(getattr(request, "state", None), "tenant_code", None)
            auth_tenant_id = getattr(
                getattr(request, "state", None), "auth_tenant_id", None
            )
            auth_api_key_id = getattr(
                getattr(request, "state", None), "auth_api_key_id", None
            )
            auth_api_key_label = getattr(
                getattr(request, "state", None), "auth_api_key_label", None
            )

            logger.info(
                "Request completed",
                request_id=request_id,
                status_code=response.status_code,
                process_time=process_time,
                tenant_id=str(tenant_id) if tenant_id else None,
                tenant_code=tenant_code,
                auth_tenant_id=str(auth_tenant_id) if auth_tenant_id else None,
                actor_api_key_id=str(auth_api_key_id) if auth_api_key_id else None,
                actor_api_key_label=auth_api_key_label,
            )

            return response

        except Exception as exc:
            # Calculate processing time for errors
            process_time = time.time() - start_time

            # Log error
            tenant_id = getattr(getattr(request, "state", None), "tenant_id", None)
            tenant_code = getattr(getattr(request, "state", None), "tenant_code", None)
            auth_tenant_id = getattr(
                getattr(request, "state", None), "auth_tenant_id", None
            )
            auth_api_key_id = getattr(
                getattr(request, "state", None), "auth_api_key_id", None
            )
            auth_api_key_label = getattr(
                getattr(request, "state", None), "auth_api_key_label", None
            )

            logger.error(
                "Request failed",
                request_id=request_id,
                error=str(exc),
                process_time=process_time,
                exc_info=True,
                tenant_id=str(tenant_id) if tenant_id else None,
                tenant_code=tenant_code,
                auth_tenant_id=str(auth_tenant_id) if auth_tenant_id else None,
                actor_api_key_id=str(auth_api_key_id) if auth_api_key_id else None,
                actor_api_key_label=auth_api_key_label,
            )

            raise


async def add_process_time_header(request: Request, call_next: Callable) -> Response:
    """
    Simple middleware function to add processing time header.

    Args:
        request: HTTP request
        call_next: Next handler in chain

    Returns:
        Response: Response with X-Process-Time header
    """
    # Keep this middleware idempotent: other middleware may already set the header.
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers.setdefault("X-Process-Time", str(process_time))
    return response
