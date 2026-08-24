"""Dependency-free contract checks for audit-edit routes."""

from __future__ import annotations

import ast
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
ROUTES = ROOT / "kits/audit-edit-kit/src/backend/app/api/routes_edit.py"
GENERIC_ROUTES = ROOT / "kits/generic-forms-kit/src/backend/app/api/routes_generic_forms.py"


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: Any):
        self.status_code = status_code
        self.detail = detail


def load_coerce_changes() -> Callable[..., dict[str, Any]]:
    tree = ast.parse(ROUTES.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_coerce_changes"
    )
    namespace = {
        "Any": Any,
        "Callable": Callable,
        "HTTPException": HTTPException,
        "datetime": datetime,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(ROUTES), "exec"), namespace)
    return namespace["_coerce_changes"]


def load_coerce() -> Callable[[Any, str], Any]:
    tree = ast.parse(GENERIC_ROUTES.read_text(encoding="utf-8-sig"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_coerce")

    class PandasStub:
        @staticmethod
        def isna(_: Any) -> bool:
            return False

    namespace = {"Any": Any, "datetime": datetime, "pd": PandasStub}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(GENERIC_ROUTES), "exec"), namespace)
    return namespace["_coerce"]


def expect_422(call: Callable[[], Any]) -> HTTPException:
    try:
        call()
    except HTTPException as exc:
        assert exc.status_code == 422
        return exc
    raise AssertionError("Expected HTTP 422")


def main() -> None:
    validate = load_coerce_changes()
    coerce = load_coerce()
    for raw in ("true", "1", "yes", "Y", "on"):
        assert coerce(raw, "boolean") is True
    for raw in ("false", "0", "no", "N", "off"):
        assert coerce(raw, "boolean") is False
    assert coerce("banana", "boolean") == "banana"
    assert coerce("2026-08-21T15:30:00", "date") == "2026-08-21"
    assert coerce("not-a-date", "date") == "not-a-date"
    fields = [
        {"name": "count", "type": "integer", "required": True},
        {"fieldKey": "note", "type": "string"},
        {"name": "enabled", "type": "boolean"},
        {"name": "started_on", "type": "date"},
    ]
    assert validate(
        {"count": "2", "note": " ok ", "enabled": "YES", "started_on": "2026-08-21"},
        fields,
        coerce,
    ) == {
        "count": 2,
        "note": "ok",
        "enabled": True,
        "started_on": "2026-08-21",
    }
    expect_422(lambda: validate({}, fields, coerce))
    assert expect_422(lambda: validate({"bad": 1}, fields, coerce)).detail == {
        "invalid_fields": ["bad"]
    }
    expect_422(lambda: validate({"count": None}, fields, coerce))
    expect_422(lambda: validate({"count": "nope"}, fields, coerce))
    expect_422(lambda: validate({"note": {"nested": True}}, fields, coerce))
    expect_422(lambda: validate({"note": ["nested"]}, fields, coerce))
    expect_422(lambda: validate({"enabled": "banana"}, fields, coerce))
    expect_422(lambda: validate({"started_on": "not-a-date"}, fields, coerce))

    routes_tree = ast.parse(ROUTES.read_text(encoding="utf-8"))
    record_edit = next(
        node for node in routes_tree.body if isinstance(node, ast.ClassDef) and node.name == "RecordEditIn"
    )
    changes = next(
        node for node in record_edit.body if isinstance(node, ast.AnnAssign) and node.target.id == "changes"
    )
    assert ast.unparse(changes.annotation) == "dict[str, str | int | float | bool | None]"

    source = ROUTES.read_text(encoding="utf-8")
    for declaration in (
        '@router.patch("/records/{table_code}/{record_id}")',
        '@router.get("/reasons")',
        '@router.post("/reasons",',
        '@router.patch("/reasons/{reason_id}")',
    ):
        assert declaration in source

    # GET /reasons is a read-only catalog browse needed by any actor who can call
    # edit_record()/set_schema() (neither of which is manager-gated); only the catalog
    # mutations (create/update) stay manager-only. Pin each function body's role-check
    # shape so this asymmetry can't silently drift back.
    function_bodies = {
        node.name: ast.dump(node)
        for node in routes_tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name in {"list_reasons", "create_reason", "update_reason"}
    }
    assert "_require_tenant_manager" not in function_bodies["list_reasons"]
    assert "_require_tenant_manager" in function_bodies["create_reason"]
    assert "_require_tenant_manager" in function_bodies["update_reason"]

    audit_contract = json.loads((ROOT / "kits/audit-edit-kit/kit.contract.json").read_text(encoding="utf-8"))
    generic_contract = json.loads((ROOT / "kits/generic-forms-kit/kit.contract.json").read_text(encoding="utf-8"))
    provided_db = {
        item if isinstance(item, str) else item["capability"]
        for item in audit_contract["provides"]["db"]
    }
    assert "db.edit-reasons.validate" in provided_db
    assert "db.edit-reasons.validate" in generic_contract["consumes"]["db"]

    generic_route = GENERIC_ROUTES.read_text(encoding="utf-8-sig")
    assert "reason_id: uuid.UUID" in generic_route
    assert 'DB_CAPABILITIES["db.edit-reasons.validate"]' in generic_route
    for model_path in (
        ROOT / "kits/generic-forms-kit/src/backend/app/models/station.py",
        ROOT / "generated/mvp-import-flow/form-analysis-server/backend/app/models/station.py",
    ):
        model = model_path.read_text(encoding="utf-8")
        for field in ("reason_id", "reason_text", "created_by", "created_at"):
            assert f"{field}: Mapped[" in model

    print("Passed: audit edit route and reason-tracked schema contracts")


if __name__ == "__main__":
    main()
