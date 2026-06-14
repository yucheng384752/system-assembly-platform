"""Cross-dialect JSON/JSONB helper.

PostgreSQL  → JSONB  (native binary JSON, supports GIN indexing)
SQLite/other → JSON  (stored as TEXT, SQLAlchemy handles serialisation)

Usage in models:
    from app.core.db_types import JsonBColumn
    data: Mapped[dict] = mapped_column(JsonBColumn(), nullable=False, server_default="{}")
"""
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB as _JSONB


def JsonBColumn():
    return JSON().with_variant(_JSONB(), "postgresql")
