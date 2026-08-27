"""Flow run & trace chain models — dynamic CSV dataflow traceability.

Mirrors the canonical contract in
`assembly/baselines/default-db-schema.baseline.json` (tables: flow_runs,
flow_key_aliases, trace_chains, trace_chain_steps). Owned by import-pipeline-kit.

Identity is flow_run_id / trace_uuid; hashes are for comparison/versioning only
(see dynamic_csv_dataflow_trace_design.txt §5 — do not use hash as a foreign key).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class FlowRun(Base):
    """One traceable business process run (e.g. one lot). Created from the anchor step."""

    __tablename__ = "flow_runs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "flow_key", "flow_key_type", name="uq_flow_runs_tenant_key"
        ),
        Index("ix_flow_runs_tenant_date", "tenant_id", "process_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    # The import_job that created this flow_run (design's upload_batch_id).
    upload_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_jobs.id"), nullable=True, index=True
    )
    flow_key: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="Primary key value from the anchor step"
    )
    flow_key_type: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Column name that provided flow_key"
    )
    process_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="Display/filter only, not used for matching"
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="partial",
        nullable=False,
        comment="partial | completed | waiting_for_mapping",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    aliases: Mapped[list["FlowKeyAlias"]] = relationship(
        back_populates="flow_run", cascade="all, delete-orphan"
    )
    trace_chain: Mapped["TraceChain"] = relationship(
        back_populates="flow_run", cascade="all, delete-orphan", uselist=False
    )


class FlowKeyAlias(Base):
    """All known key values for a flow_run across steps. Solves cross-table key mismatch."""

    __tablename__ = "flow_key_aliases"
    __table_args__ = (
        UniqueConstraint(
            "key_type", "key_value", name="uq_flow_key_aliases_type_value"
        ),
        Index("ix_flow_key_aliases_lookup", "key_type", "key_value"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    flow_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("flow_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key_type: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Column name (e.g. 原料卡號)"
    )
    key_value: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="The actual key value in that step"
    )
    confirmed_by: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="auto | user_id"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    flow_run: Mapped["FlowRun"] = relationship(back_populates="aliases")


class TraceChain(Base):
    """Identity and aggregate status of one traceable data chain."""

    __tablename__ = "trace_chains"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    flow_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("flow_runs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    trace_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        default=uuid.uuid4,
        nullable=False,
        comment="External-facing stable identifier",
    )
    chain_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA256 of completed step_hashes sorted by step_order",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="partial",
        nullable=False,
        comment="partial | completed | waiting_for_mapping",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    flow_run: Mapped["FlowRun"] = relationship(back_populates="trace_chain")
    steps: Mapped[list["TraceChainStep"]] = relationship(
        back_populates="trace_chain", cascade="all, delete-orphan"
    )


class TraceChainStep(Base):
    """One row per step per trace chain. Dynamic — new step type needs no schema change."""

    __tablename__ = "trace_chain_steps"
    __table_args__ = (
        UniqueConstraint(
            "trace_chain_id", "step_name", name="uq_trace_chain_steps_chain_step"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trace_chain_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trace_chains.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="e.g. daihui_entry, daihui_material"
    )
    step_order: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Sort order; used when computing chain_hash"
    )
    step_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="SHA256 of row_hashes; NULL if not uploaded"
    )
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_files.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
        comment="pending | completed | failed",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    trace_chain: Mapped["TraceChain"] = relationship(back_populates="steps")
