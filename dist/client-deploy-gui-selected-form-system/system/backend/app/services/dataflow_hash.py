"""Dataflow fingerprint & trace-chain hashes.

Pure functions, no DB. Implements dynamic_csv_dataflow_trace_design.txt §4.
Core invariant: column order must NOT affect col_set_hash / schema_hash —
sort before hashing (CSV export column order is unstable).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_schema_fingerprints(
    columns: Sequence[str], dtypes: Sequence[str]
) -> dict[str, str]:
    """Two-layer schema fingerprint (sorted → order-independent).

    col_set_hash: sorted column names only (loose match, tolerates dtype drift).
    schema_hash:  sorted (name, dtype) pairs (exact match).
    Both truncated to 16 hex chars, matching the design's example.
    """
    col_set_hash = _sha256_hex(str(sorted(columns)))[:16]
    schema_hash = _sha256_hex(str(sorted(zip(columns, dtypes))))[:16]
    return {"col_set_hash": col_set_hash, "schema_hash": schema_hash}


def compute_row_hash(values: Iterable[object]) -> str:
    """Hash of a single row's business-key + important values (dedupe)."""
    return _sha256_hex("|".join("" if v is None else str(v) for v in values))


def compute_step_hash(row_hashes: Iterable[str]) -> str:
    """Aggregate hash for one step = hash of its row_hashes (order-independent)."""
    return _sha256_hex("|".join(sorted(row_hashes)))


def compute_chain_hash(steps: Iterable[object]) -> str | None:
    """Chain hash from completed steps, concatenated by step_order.

    `steps` items must expose `.step_hash` and `.step_order` (e.g. TraceChainStep).
    Only steps with a non-null step_hash are included; NULL steps are not yet uploaded.
    Returns None when no step is completed (empty chain).
    """
    completed = sorted(
        (s for s in steps if getattr(s, "step_hash", None)),
        key=lambda s: s.step_order,
    )
    if not completed:
        return None
    return _sha256_hex("|".join(s.step_hash for s in completed))


if __name__ == "__main__":
    # Invariant 1: column order does not change the fingerprints.
    a = compute_schema_fingerprints(["批號", "數量", "總重量"], ["str", "int", "float"])
    b = compute_schema_fingerprints(["總重量", "批號", "數量"], ["float", "str", "int"])
    assert a == b, (a, b)

    # Invariant 2: same columns, different dtype → same col_set_hash, different schema_hash.
    c = compute_schema_fingerprints(["批號"], ["int"])
    d = compute_schema_fingerprints(["批號"], ["str"])
    assert c["col_set_hash"] == d["col_set_hash"]
    assert c["schema_hash"] != d["schema_hash"]

    # Invariant 3: chain_hash follows step_order, ignores insertion order, skips NULL steps.
    class _S:
        def __init__(self, order, h):
            self.step_order, self.step_hash = order, h

    h1 = compute_chain_hash([_S(2, "p001"), _S(5, "e001")])
    h2 = compute_chain_hash([_S(5, "e001"), _S(2, "p001")])
    assert h1 == h2 and h1 is not None
    assert compute_chain_hash([_S(1, None), _S(2, None)]) is None

    print("dataflow_hash self-check OK")
