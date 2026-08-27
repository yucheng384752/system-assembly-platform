from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def _candidate_roots() -> list[Path]:
    here = Path(__file__).resolve()
    return [here.parents[i] for i in range(min(len(here.parents), 8))]


@lru_cache(maxsize=1)
def load_kit_contracts() -> list[dict[str, Any]]:
    for root in _candidate_roots():
        kits_dir = root / "kits"
        if not kits_dir.is_dir():
            continue
        contracts: list[dict[str, Any]] = []
        for path in sorted(kits_dir.glob("*/kit.contract.json")):
            contracts.append(json.loads(path.read_text(encoding="utf-8")))
        if contracts:
            return contracts
    return []


def capability_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for contract in load_kit_contracts():
        kit = contract.get("kit")
        for api in contract.get("provides", {}).get("api", []) or []:
            if isinstance(api, dict) and api.get("capability"):
                index[api["capability"]] = {**api, "kit": kit, "kind": "api"}
        for db in contract.get("provides", {}).get("db", []) or []:
            if isinstance(db, str):
                index[db] = {"capability": db, "kit": kit, "kind": "db"}
            elif isinstance(db, dict) and db.get("capability"):
                index[db["capability"]] = {**db, "kit": kit, "kind": "db"}
    return index
