"""Dependency-free contract and behavior checks for analytics/upload history."""

from __future__ import annotations

import ast
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ROUTES = ROOT / "kits/analytics-kit/src/backend/app/api/routes_analytics.py"
CAPABILITIES = ROOT / "kits/platform-core-kit/src/backend/app/core/db_capabilities.py"
# UploadJob is NOT a kit-source model — it's provided by the baseline that assembly always
# copies first (generated/mvp-import-flow/form-analysis-server), and upload-validation-kit's
# manifest registers baseline routes_upload.py/routes_validate.py directly. db.upload.jobs.list
# only reads this existing model; it must never be redefined under kits/, or it will collide
# with (and break) the baseline's own routes_upload.py at assembly time.
UPLOAD_MODEL = ROOT / "generated/mvp-import-flow/form-analysis-server/backend/app/models/upload_job.py"


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: Any):
        self.status_code = status_code
        self.detail = detail


def load_functions(*names: str) -> dict[str, Any]:
    tree = ast.parse(ROUTES.read_text(encoding="utf-8"))
    functions = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    namespace = {
        "Any": Any,
        "HTTPException": HTTPException,
        "date": date,
        "timedelta": timedelta,
        "MAX_RANGE_DAYS": 366,
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(ROUTES), "exec"), namespace)
    return namespace


def capabilities(tree: ast.Module) -> set[str]:
    mapping = next(
        node for node in tree.body if isinstance(node, ast.Assign) and node.targets[0].id == "DB_CAPABILITIES"
    )
    return {key.value for key in mapping.value.keys}


def contract_capabilities(path: Path, section: str) -> set[str]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    return {
        item if isinstance(item, str) else item["capability"]
        for item in contract[section]["db"]
    }


def main() -> None:
    source = ROUTES.read_text(encoding="utf-8")
    for declaration in (
        '@router.get("/upload-history")',
        '@router.get("/upload-history/export")',
        '@router.get("/trend")',
    ):
        assert declaration in source

    # UploadJob is a pre-existing baseline model (see UPLOAD_MODEL comment above) — this is a
    # subset check that the fields db.upload.jobs.list actually reads still exist with the
    # expected types, not a full pin of a model this feature doesn't own.
    model_tree = ast.parse(UPLOAD_MODEL.read_text(encoding="utf-8"))
    model = next(node for node in model_tree.body if isinstance(node, ast.ClassDef) and node.name == "UploadJob")
    annotations = {
        node.target.id: ast.unparse(node.annotation)
        for node in model.body
        if isinstance(node, ast.AnnAssign)
    }
    assert annotations.items() >= {
        "process_id": "Mapped[uuid.UUID]",
        "filename": "Mapped[str]",
        "status": "Mapped[JobStatus]",
        "total_rows": "Mapped[int | None]",
        "valid_rows": "Mapped[int | None]",
        "invalid_rows": "Mapped[int | None]",
        "created_at": "Mapped[datetime]",
        "tenant_id": "Mapped[uuid.UUID | None]",
        "actor_label_snapshot": "Mapped[str | None]",
    }.items()
    status_enum = next(node for node in model_tree.body if isinstance(node, ast.ClassDef) and node.name == "JobStatus")
    status_values = {
        stmt.value.value
        for stmt in status_enum.body
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant)
    }
    assert status_values == {"PENDING", "VALIDATED", "IMPORTED"}

    capability_tree = ast.parse(CAPABILITIES.read_text(encoding="utf-8"))
    registered = capabilities(capability_tree)
    assert {"db.records.trend", "db.upload.jobs.list"} <= registered
    assert "db.upload.jobs.create" not in registered
    search = next(
        node for node in capability_tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "search_records"
    )
    assert {"date_from", "date_to"} <= {arg.arg for arg in search.args.args}
    capability_source = CAPABILITIES.read_text(encoding="utf-8")
    assert "func.date(GenericRecord.created_at)" in capability_source
    assert "Too many records; narrow the date range" in capability_source

    upload = contract_capabilities(ROOT / "kits/upload-validation-kit/kit.contract.json", "provides")
    station = contract_capabilities(ROOT / "kits/station-data-link-kit/kit.contract.json", "provides")
    analytics = contract_capabilities(ROOT / "kits/analytics-kit/kit.contract.json", "consumes")
    assert upload == {"db.upload.jobs.list"}  # .create was dropped — no write path, see Decisions #2/#3
    assert "db.records.trend" in station
    assert {"db.upload.jobs.list", "db.records.trend", "db.records.search", "db.forms.list"} <= analytics

    # generic-forms-kit is explicitly out of scope this round (Decisions #2) — its contract
    # must not have picked up any upload-jobs dependency.
    generic = contract_capabilities(ROOT / "kits/generic-forms-kit/kit.contract.json", "consumes")
    assert "db.upload.jobs.create" not in generic
    assert "db.upload.jobs.list" not in generic
    generic_routes_source = (
        ROOT / "kits/generic-forms-kit/src/backend/app/api/routes_generic_forms.py"
    ).read_text(encoding="utf-8")
    assert "upload.jobs" not in generic_routes_source
    assert "_save_upload_history" not in generic_routes_source

    helpers = load_functions("_bucket_start", "_rebucket", "_date_range")
    daily = [
        {"bucket_start": "2026-01-31", "count": 2, "sum": 4.0, "value_count": 2},
        {"bucket_start": "2026-02-01", "count": 3, "sum": 9.0, "value_count": 3},
        {"bucket_start": "2026-02-02", "count": 5, "sum": 20.0, "value_count": 4},
        {"bucket_start": "2026-02-09", "count": 7, "sum": None, "value_count": 0},
    ]
    weeks = helpers["_rebucket"](daily, "week")
    assert [(item["bucket_start"], item["count"]) for item in weeks] == [
        ("2026-01-26", 5),
        ("2026-02-02", 5),
        ("2026-02-09", 7),
    ]
    months = helpers["_rebucket"](daily, "month")
    assert [(item["bucket_start"], item["count"]) for item in months] == [
        ("2026-01-01", 2),
        ("2026-02-01", 15),
    ]
    assert weeks[0]["sum"] == 13.0 and weeks[0]["avg"] == 2.6

    try:
        helpers["_date_range"]("2025-01-01", "2026-02-01")
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("Expected overlong range to return 422")

    assert 'detail="field must reference a numeric field"' in source
    assert 'result["total"] > EXPORT_LIMIT' in source
    assert 'detail="Too many rows to export; narrow the filters"' in source
    assert '.encode("utf-8-sig")' in source
    print("Passed: analytics routes, upload history, trend behavior, and kit contracts")


if __name__ == "__main__":
    main()
