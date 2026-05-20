"""
Database configuration and session management.

Provides async SQLAlchemy setup with PostgreSQL, connection pooling,
and dependency injection for FastAPI routes.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

# SQLite 測試相容：專案模型大量使用 PostgreSQL JSONB。
# 在 SQLite（測試用）時將 JSONB 編譯成 JSON，避免 create_all 失敗。
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

# Database engine and session factory (initialized during startup)
engine = None
async_session_factory = None


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


async def init_db() -> None:
    """
    Initialize database engine and session factory.

    This should be called during application startup.
    Only supports PostgreSQL database.
    """
    global engine, async_session_factory

    settings = get_settings()

    # Validate that we're using PostgreSQL or SQLite
    if not settings.database_url.startswith(
        "postgresql"
    ) and not settings.database_url.startswith("sqlite"):
        raise ValueError(
            f"只支援PostgreSQL或SQLite資料庫。當前配置: {settings.database_url[:20]}..."
        )

    # Create async engine with connection pooling
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

    engine_args = {
        "url": settings.database_url,
        "echo": settings.database_echo,
        "pool_pre_ping": True,
    }

    if settings.database_url.startswith("postgresql"):
        engine_args.update(
            {
                "pool_size": settings.database_pool_size,
                "pool_recycle": settings.database_pool_recycle,
            }
        )
    else:
        # SQLite specific
        engine_args["connect_args"] = connect_args

    engine = create_async_engine(**engine_args)

    # Create session factory
    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get database session.

    Provides async database session with automatic cleanup.
    Use this as a FastAPI dependency.

    Yields:
        AsyncSession: Database session

    Example:
        ```python
        @app.get("/users/")
        async def get_users(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(User))
            return result.scalars().all()
        ```
    """
    if async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() during startup.")

    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database session.

    Use this for database operations outside of FastAPI routes.

    Yields:
        AsyncSession: Database session

    Example:
        ```python
        async with get_db_context() as db:
            user = await db.get(User, user_id)
        ```
    """
    if async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() during startup.")

    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db() -> None:
    """
    Close database engine.

    This should be called during application shutdown.
    """
    global engine
    if engine:
        await engine.dispose()
        engine = None
