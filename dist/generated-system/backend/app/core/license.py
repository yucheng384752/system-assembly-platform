"""
License verification for Form System Kit Composer generated systems.
Checks RSA-PSS signature, expiry, and machine fingerprint from license.lic at startup.
Failure is logged as a warning; it does NOT block app startup.

Machine fingerprint priority:
  1. TPM 2.0 EK public key hash  (hardware-bound, non-exportable)
  2. /etc/machine-id fallback     (Linux only, spoofable — logged as warning)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Public key embedded at package generation time (RSA-2048 SubjectPublicKeyInfo PEM)
_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAt1wQ/q3fbmYmd8545NJk
/qEyMwtmPRaJFpoALjvxEvrfVIe/H58X1UTkGCept4Ata20HUvr1D8LUsr3jxJUi
48INzbau+HKxwq+fvEaaGPNdgIKZpLOM0TM/g/cdtIvneWsmn4ZEV6q8UTTql7Zp
5mveUc6KY6QWtqEPOxFwVl7RXWxpF/yBu2S0itRdo5ZNkT/70BbJEuL/PAQbuMlw
cb9f08cCqoCsARydnO2znpT6f5mMXodZY/5GJIm3UlcXpSFZWOm3T5Gds46SdRUk
/4X9IffUlLFmHvV0y7sJmQ1WDquDJDuJydls5Y3ByvaokjNdbGhAr9k09QlXy7hy
EwIDAQAB
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
    """
    Returns a hardware-bound machine fingerprint (SHA-256 hex, 64 chars).
    Tries TPM 2.0 EK first; falls back to /etc/machine-id with a warning.
    Returns None if neither source is available.
    """
    fp = _tpm_ek_fingerprint()
    if fp is not None:
        logger.debug("license: fingerprint source=tpm2-ek")
        return fp

    # Fallback: /etc/machine-id (Linux/systemd — trivially spoofable via file copy)
    machine_id_path = Path("/etc/machine-id")
    if machine_id_path.exists():
        logger.warning(
            "license: TPM 2.0 not available — falling back to /etc/machine-id "
            "(weaker binding; install tpm2-tools and add service user to 'tss' group)"
        )
        raw = machine_id_path.read_text("utf-8").strip().lower()
        return hashlib.sha256(raw.encode()).hexdigest()

    return None


def _tpm_ek_fingerprint() -> str | None:
    """SHA-256 of TPM 2.0 Endorsement Key public key bytes. Hardware-bound."""
    try:
        if platform.system() == "Windows":
            return _tpm_ek_windows()
        return _tpm_ek_linux()
    except Exception as exc:  # noqa: BLE001
        logger.debug("TPM EK fingerprint error: %s", exc)
        return None


def _tpm_ek_linux() -> str | None:
    """
    Derives EK public key via tpm2_createek (tpm2-tools >= 4.x).
    The EK is deterministic: same TPM always yields the same public key bytes.

    Prerequisites:
      - apt-get install tpm2-tools          (Ubuntu/Debian)
      - usermod -aG tss <service-user>      (grants /dev/tpmrm0 access without root)
      - docker-compose: devices: [/dev/tpmrm0:/dev/tpmrm0]  (if containerised)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        ctx_path = Path(tmpdir) / "ek.ctx"
        pub_path = Path(tmpdir) / "ek.pub"
        try:
            result = subprocess.run(
                ["tpm2_createek", "-c", str(ctx_path), "-G", "rsa", "-u", str(pub_path)],
                capture_output=True,
                timeout=10,
            )
        except FileNotFoundError:
            logger.debug("tpm2_createek not found — install: apt-get install tpm2-tools")
            return None
        except subprocess.TimeoutExpired:
            logger.debug("tpm2_createek timed out — /dev/tpmrm0 may be inaccessible or service user not in tss group")
            return None

        if result.returncode != 0:
            logger.debug(
                "tpm2_createek exit %d: %s",
                result.returncode,
                result.stderr.decode(errors="replace").strip(),
            )
            return None

        if not pub_path.exists():
            return None

        return hashlib.sha256(pub_path.read_bytes()).hexdigest()


def _tpm_ek_windows() -> str | None:
    """
    Reads TPM EK public key hash via PowerShell Get-TpmEndorsementKeyInfo.
    Available on Windows 8+ with TPM 2.0 chip (all Windows 11 machines).
    """
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "$ek = Get-TpmEndorsementKeyInfo -HashAlgorithm Sha256; "
            "if ($ek -and $ek.PublicKeyHash) "
            "{ $ek.PublicKeyHash.Replace('-','').ToLower() } else { exit 1 }",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0 or not result.stdout.strip():
        logger.debug("Get-TpmEndorsementKeyInfo failed: %s", result.stderr.strip())
        return None
    # Double-hash so Windows and Linux fingerprints share the same 64-char hex format
    return hashlib.sha256(result.stdout.strip().encode()).hexdigest()
