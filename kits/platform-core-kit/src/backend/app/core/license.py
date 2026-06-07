"""
License verification for Form System Kit Composer generated systems.
Checks RSA-PSS signature, expiry, and machine fingerprint from license.lic at startup.
Failure is logged as a warning; it does NOT block app startup.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Public key embedded at package generation time (RSA-2048 SubjectPublicKeyInfo PEM)
_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAms0567xqNQST0UP8AS3j
8TehTrLfKCO9BxXKT4R2RLQcHqe41hMqfFQ8HlL0IdN4tbh0L4RJyz49Jkd2fvH7
RtqoygGTtMCwa3eT7dBaL9q8QX0qjYxQ+qcICP4VBd/d/qgWej/UG+Sr7DWE193L
BjmbFbqngraWpRO/3aP1uPcMkH0BMU58vRrN/ft4f6uGBrCidanamyiZLUkmHNuz
T7CnIb9FQHcBvDKKKNLUVql+PhvKqmRUNCVeRTklsosaMueIYNnVYLzY7Q6wW+At
n8nEgV0cwTS6q2ySisKTSyeyMlFggMH/qffc56ES6SAW/coD1WQb1mm8SDUxh7vi
IwIDAQAB
-----END PUBLIC KEY-----"""


@dataclass
class LicenseResult:
    valid: bool
    licensee: str = ""
    expires_at: str = ""
    reason: str = ""


def _find_license_file() -> Path | None:
    candidates = [
        Path(__file__).parents[4] / "license.lic",   # system/license.lic
        Path(__file__).parents[5] / "license.lic",   # one level up (deploy package root)
        Path(os.getcwd()) / "license.lic",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def verify_license() -> LicenseResult:
    lic_path = _find_license_file()
    if lic_path is None:
        return LicenseResult(valid=False, reason="license.lic not found")

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.exceptions import InvalidSignature
        import base64
    except ImportError:
        return LicenseResult(valid=False, reason="cryptography package not installed")

    try:
        lic_data = json.loads(lic_path.read_text("utf-8"))
        payload_str: str = lic_data["payload"]
        sig_b64: str = lic_data["signature"]
    except Exception as exc:
        return LicenseResult(valid=False, reason=f"malformed license.lic: {exc}")

    # Verify RSA-PSS signature
    try:
        pub_key = serialization.load_pem_public_key(_PUBLIC_KEY_PEM.encode())
        pub_key.verify(
            base64.b64decode(sig_b64),
            payload_str.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
    except InvalidSignature:
        return LicenseResult(valid=False, reason="signature verification failed")
    except Exception as exc:
        return LicenseResult(valid=False, reason=f"signature error: {exc}")

    # Check expiry
    try:
        payload = json.loads(payload_str)
        expires_at = payload.get("expiresAt", "")
        if expires_at:
            expiry_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expiry_dt:
                return LicenseResult(valid=False, expires_at=expires_at, reason="license expired")
        licensee = payload.get("licensee", {})
        licensee_str = f"{licensee.get('name', '')} <{licensee.get('email', '')}>"
    except Exception as exc:
        return LicenseResult(valid=False, reason=f"payload parse error: {exc}")

    # Check machine fingerprint (if embedded in license)
    expected_fp = payload.get("machineFingerprint")
    if expected_fp:
        current_fp = _get_machine_fingerprint()
        if current_fp is None:
            return LicenseResult(valid=False, reason="cannot read machine-id for fingerprint check")
        if current_fp != expected_fp:
            return LicenseResult(valid=False, reason="machine fingerprint mismatch — license issued for a different machine")

    return LicenseResult(valid=True, licensee=licensee_str, expires_at=expires_at)


def _get_machine_fingerprint() -> str | None:
    """SHA-256 of /etc/machine-id (Linux). Returns None if unavailable."""
    machine_id_path = Path("/etc/machine-id")
    if not machine_id_path.exists():
        return None
    raw = machine_id_path.read_text("utf-8").strip().lower()
    return hashlib.sha256(raw.encode()).hexdigest()
