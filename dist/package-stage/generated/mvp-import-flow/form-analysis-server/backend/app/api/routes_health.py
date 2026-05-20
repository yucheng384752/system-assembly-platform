"""
Health check endpoints.

Provides comprehensive health monitoring for the application including:
- Basic health status
- Database connectivity
- Service dependencies
- System resources (optional)
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db

router = APIRouter()


@router.get("", summary="Basic Health Check")
@router.get("/", summary="Basic Health Check")
async def health_check() -> dict[str, Any]:
    """
    Basic health check endpoint.

    Returns:
        dict: Basic service status and metadata
    """
    return {
        "status": "healthy",
        "service": "form-analysis-api",
        "version": "1.0.0",
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "environment": get_settings().environment,
    }


@router.get("/detailed", summary="Detailed Health Check")
async def detailed_health_check(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """
    Detailed health check with database connectivity test.

    Args:
        db: Database session dependency

    Returns:
        dict: Comprehensive health status including database

    Raises:
        HTTPException: If critical services are unavailable
    """
    settings = get_settings()
    health_data = {
        "status": "healthy",
        "service": "form-analysis-api",
        "version": "1.0.0",
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "environment": settings.environment,
        "checks": {},
    }

    # Database connectivity check
    try:
        result = await db.execute(text("SELECT 1 as health_check"))
        row = result.fetchone()
        if row and row[0] == 1:
            health_data["checks"]["database"] = {
                "status": "healthy",
                "message": "Database connection successful",
            }
        else:
            raise Exception("Invalid health check response")

    except Exception as e:
        health_data["checks"]["database"] = {
            "status": "unhealthy",
            "message": f"Database connection failed: {str(e)}",
        }
        health_data["status"] = "degraded"

    # Configuration check
    try:
        # Verify critical configuration is present
        if not settings.database_url:
            raise ValueError("DATABASE_URL not configured")
        if not settings.secret_key:
            raise ValueError("SECRET_KEY not configured")

        health_data["checks"]["configuration"] = {
            "status": "healthy",
            "message": "Configuration loaded successfully",
        }
    except Exception as e:
        health_data["checks"]["configuration"] = {
            "status": "unhealthy",
            "message": f"Configuration error: {str(e)}",
        }
        health_data["status"] = "unhealthy"

    # Return appropriate HTTP status
    if health_data["status"] == "unhealthy":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=health_data
        )
    elif health_data["status"] == "degraded":
        raise HTTPException(
            status_code=status.HTTP_200_OK,  # Still return 200 for degraded
            detail=health_data,
        )

    return health_data


@router.get("/ready", summary="Readiness Check")
async def readiness_check(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """
    Kubernetes-style readiness probe.

    Tests if the service is ready to accept traffic.

    Args:
        db: Database session dependency

    Returns:
        dict: Simple ready/not ready status

    Raises:
        HTTPException: If service is not ready
    """
    try:
        # Quick database connectivity test
        await db.execute(text("SELECT 1"))

        return {"status": "ready", "message": "Service is ready to accept traffic"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "message": f"Service not ready: {str(e)}"},
        )


@router.get("/live", summary="Liveness Check")
async def liveness_check() -> dict[str, str]:
    """
    Kubernetes-style liveness probe.

    Tests if the service is alive (basic functionality).
    This should be lightweight and not depend on external services.

    Returns:
        dict: Simple alive status
    """
    return {"status": "alive", "message": "Service is running"}
