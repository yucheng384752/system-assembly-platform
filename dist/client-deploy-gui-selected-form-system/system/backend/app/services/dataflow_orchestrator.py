"""Dataflow orchestrator — flow_run resolution + trace_chain maintenance.

Implements dynamic_csv_dataflow_trace_design.txt §11 (runtime), adapted to this
project: steps are identified by form_code / step_name, data lives in the target
tables committed by ImportService. Call `record_step` once per committed step.

Flow step definitions mirror assembly/baselines/daihui-form-schema.baseline.json
(dataFlowDefinition). They are embedded here because the deployed backend does not
ship the assembly baselines.
# ponytail: inline step map mirrors the baseline; move to a flow_definitions table
#           or a shipped config JSON when more than the Daihui flow exists.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.flow_trace import FlowKeyAlias, FlowRun, TraceChain, TraceChainStep
from app.services.dataflow_hash import compute_chain_hash, compute_step_hash

WAITING_FOR_MAPPING = "waiting_for_mapping"


@dataclass(frozen=True)
class FlowStepDef:
    step_name: str
    step_order: int
    business_key: str | None  # column name providing the flow key; None = no key column
    is_anchor: bool
    key_match_strategy: str  # anchor | exact | alias
    required: bool


# Daihui 5-step chain (mirrors daihui-form-schema.baseline.json dataFlowDefinition).
_DAIHUI_STEPS = [
    FlowStepDef("daihui_entry", 1, "批號", True, "anchor", True),
    FlowStepDef("daihui_inspection", 2, "批號", False, "exact", False),
    FlowStepDef("daihui_material", 3, "原料卡號", False, "alias", False),
    FlowStepDef("daihui_production", 4, "生產批號", False, "alias", False),
    FlowStepDef("daihui_quality", 5, None, False, "alias", False),
]
_STEP_BY_NAME: dict[str, FlowStepDef] = {s.step_name: s for s in _DAIHUI_STEPS}
_REQUIRED_STEPS = {s.step_name for s in _DAIHUI_STEPS if s.required}


def get_step_definition(step_name: str) -> FlowStepDef | None:
    """Return the flow step definition for a form_code/step_name, or None if unknown.

    Unknown step (e.g. P1/P2/P3 tables not part of a traceability flow) → caller skips.
    """
    return _STEP_BY_NAME.get(step_name)


@dataclass
class StepResult:
    status: str  # completed | waiting_for_mapping
    flow_run_id: uuid.UUID | None
    trace_uuid: uuid.UUID | None


class DataflowOrchestrator:
    """Attaches a committed step to its flow_run and updates the trace chain."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_step(
        self,
        *,
        tenant_id: uuid.UUID,
        upload_batch_id: uuid.UUID | None,
        step: FlowStepDef,
        flow_key: str,
        row_hashes: list[str],
        source_file_id: uuid.UUID | None = None,
        process_date: date | None = None,
    ) -> StepResult:
        """Three-stage flow_run lookup, then upsert the trace chain step.

        Anchor step creates the flow_run; non-anchor steps attach via exact/alias
        match, or return waiting_for_mapping (commit is not blocked by the caller).
        """
        flow_run = await self._resolve_flow_run(
            tenant_id=tenant_id,
            upload_batch_id=upload_batch_id,
            step=step,
            flow_key=flow_key,
            process_date=process_date,
        )
        if flow_run is None:
            return StepResult(WAITING_FOR_MAPPING, None, None)

        # Record this step's key as an alias (auto), idempotent on (key_type, key_value).
        if step.business_key:
            await self._ensure_alias(flow_run.id, step.business_key, flow_key)

        chain = await self._find_or_create_chain(flow_run.id)
        await self._upsert_step(
            chain=chain,
            step=step,
            step_hash=compute_step_hash(row_hashes),
            row_count=len(row_hashes),
            source_file_id=source_file_id,
        )
        await self._recompute_and_status(chain, flow_run)
        await self.db.flush()
        return StepResult("completed", flow_run.id, chain.trace_uuid)

    # --- flow_run resolution (design §6 step 11, three stages) -----------------

    async def _resolve_flow_run(
        self,
        *,
        tenant_id: uuid.UUID,
        upload_batch_id: uuid.UUID | None,
        step: FlowStepDef,
        flow_key: str,
        process_date: date | None,
    ) -> FlowRun | None:
        # Stage 1: exact match on flow_runs.
        stmt = select(FlowRun).where(
            FlowRun.tenant_id == tenant_id,
            FlowRun.flow_key == flow_key,
            FlowRun.flow_key_type == (step.business_key or ""),
        )
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return existing

        # Stage 2: alias match (key_type + key_value) → flow_run.
        if step.business_key:
            alias_stmt = select(FlowKeyAlias).where(
                FlowKeyAlias.key_type == step.business_key,
                FlowKeyAlias.key_value == flow_key,
            )
            alias = (await self.db.execute(alias_stmt)).scalar_one_or_none()
            if alias is not None:
                run = await self.db.get(FlowRun, alias.flow_run_id)
                if run is not None:
                    return run

        # Stage 3: anchor creates a new flow_run; non-anchor waits for mapping.
        if step.is_anchor and step.business_key:
            run = FlowRun(
                tenant_id=tenant_id,
                upload_batch_id=upload_batch_id,
                flow_key=flow_key,
                flow_key_type=step.business_key,
                process_date=process_date,
                status="partial",
            )
            self.db.add(run)
            await self.db.flush()
            return run
        return None

    async def _ensure_alias(
        self, flow_run_id: uuid.UUID, key_type: str, key_value: str
    ) -> None:
        stmt = select(FlowKeyAlias).where(
            FlowKeyAlias.key_type == key_type,
            FlowKeyAlias.key_value == key_value,
        )
        if (await self.db.execute(stmt)).scalar_one_or_none() is not None:
            return
        self.db.add(
            FlowKeyAlias(
                flow_run_id=flow_run_id,
                key_type=key_type,
                key_value=key_value,
                confirmed_by="auto",
            )
        )
        await self.db.flush()

    # --- trace chain (design §5) ----------------------------------------------

    async def _find_or_create_chain(self, flow_run_id: uuid.UUID) -> TraceChain:
        stmt = (
            select(TraceChain)
            .where(TraceChain.flow_run_id == flow_run_id)
            .options(selectinload(TraceChain.steps))
        )
        chain = (await self.db.execute(stmt)).scalar_one_or_none()
        if chain is None:
            chain = TraceChain(flow_run_id=flow_run_id, status="partial")
            self.db.add(chain)
            await self.db.flush()
            await self.db.refresh(chain, ["steps"])
        return chain

    async def _upsert_step(
        self,
        *,
        chain: TraceChain,
        step: FlowStepDef,
        step_hash: str,
        row_count: int,
        source_file_id: uuid.UUID | None,
    ) -> None:
        existing = next(
            (s for s in chain.steps if s.step_name == step.step_name), None
        )
        now = datetime.now(timezone.utc)
        if existing is None:
            chain.steps.append(
                TraceChainStep(
                    step_name=step.step_name,
                    step_order=step.step_order,
                    step_hash=step_hash,
                    row_count=row_count,
                    source_file_id=source_file_id,
                    status="completed",
                    completed_at=now,
                )
            )
        else:
            existing.step_hash = step_hash
            existing.row_count = row_count
            existing.source_file_id = source_file_id
            existing.status = "completed"
            existing.completed_at = now

    async def _recompute_and_status(
        self, chain: TraceChain, flow_run: FlowRun
    ) -> None:
        chain.chain_hash = compute_chain_hash(chain.steps)
        completed = {
            s.step_name for s in chain.steps if s.status == "completed"
        }
        done = _REQUIRED_STEPS.issubset(completed)
        chain.status = "completed" if done else "partial"
        flow_run.status = "completed" if done else "partial"
        if done and flow_run.completed_at is None:
            flow_run.completed_at = datetime.now(timezone.utc)
