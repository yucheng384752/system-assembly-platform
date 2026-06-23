"""
License verification for Form System Kit Composer generated systems.
Checks RSA-PSS signature, expiry, and TPM machine binding (PKI challenge-response).
Failure is logged as a warning; it does NOT block app startup.

Machine binding (PKI challenge-response, requires TPM 2.0):
  - license.lic embeds machinePublicKey (RSA-2048 PEM from TPM signing key handle 0x81000001)
  - At verification, backend calls tpm2_sign to sign a random nonce with the persisted key
  - Signature is verified against machinePublicKey in the license
  - The TPM private key never leaves the chip — cryptographically non-exportable
  - No machine-id fallback: licenses without machinePublicKey are floating (unbound)
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_TPM_SIGNING_HANDLE = "0x81000001"

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
        Path(__file__).parents[5] / "license.lic",   # deploy package root
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

    # Verify RSA-PSS license signature (issuer signs the payload)
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

    # TPM machine binding (PKI challenge-response)
    expected_pubkey_pem = payload.get("machinePublicKey")
    if expected_pubkey_pem:
        if not _verify_tpm_possession(expected_pubkey_pem):
            return LicenseResult(
                valid=False,
                reason=(
                    "TPM machine binding failed — "
                    f"ensure TPM handle {_TPM_SIGNING_HANDLE} is provisioned "
                    "and accessible (run 01_tpm_full_setup.sh)"
                ),
            )
        logger.info("license: TPM machine binding verified via challenge-response")

    return LicenseResult(valid=True, licensee=licensee_str, expires_at=expires_at)


def _verify_tpm_possession(pubkey_pem: str) -> bool:
    """
    Challenge-response: ask TPM to sign a random nonce, verify with the public key
    embedded in the license. Returns True only if the TPM holds the matching private key.
    """
    nonce = os.urandom(32)
    sig = _tpm_sign_nonce(nonce)
    if sig is None:
        logger.warning(
            "license: TPM signing unavailable — "
            "tpm2_sign not found or handle %s not provisioned",
            _TPM_SIGNING_HANDLE,
        )
        return False
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        pub = serialization.load_pem_public_key(pubkey_pem.encode())
        pub.verify(sig, nonce, padding.PKCS1v15(), hashes.SHA256())
        logger.debug("license: TPM challenge-response OK (handle=%s)", _TPM_SIGNING_HANDLE)
        return True
    except Exception as exc:
        logger.warning("license: TPM challenge-response failed: %s", exc)
        return False


def _tpm_sign_nonce(nonce: bytes) -> bytes | None:
    """
    Ask TPM handle 0x81000001 to sign a nonce with RSASSA-PKCS1v15-SHA256.
    Tries --format plain first (tpm2-tools >= 4.x); falls back to parsing TPMT_SIGNATURE.
    Returns raw RSA signature bytes, or None if unavailable.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        nonce_path = Path(tmpdir) / "nonce.bin"
        sig_path   = Path(tmpdir) / "sig.bin"
        nonce_path.write_bytes(nonce)

        base_cmd = [
            "tpm2_sign",
            "--key-context", _TPM_SIGNING_HANDLE,
            "--hash-algorithm", "sha256",
            "--scheme", "rsassa",
            "--signature", str(sig_path),
            str(nonce_path),
        ]

        # Attempt 1: --format plain → raw RSA bytes directly
        try:
            r = subprocess.run(
                [*base_cmd[:6], "--format", "plain", *base_cmd[6:]],
                capture_output=True, timeout=10,
            )
            if r.returncode == 0 and sig_path.exists():
                return sig_path.read_bytes()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        except Exception:
            pass

        # Attempt 2: default TPMT_SIGNATURE format → parse manually
        sig_path.unlink(missing_ok=True)
        try:
            r = subprocess.run(base_cmd, capture_output=True, timeout=10)
            if r.returncode == 0 and sig_path.exists():
                return _parse_tpmt_rsassa_sig(sig_path.read_bytes())
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        except Exception:
            pass

        return None


def _parse_tpmt_rsassa_sig(data: bytes) -> bytes | None:
    """
    Extract raw RSA signature bytes from a TPMT_SIGNATURE structure (RSASSA scheme).
    Layout: [2B alg][2B hash][2B sig_size][sig_size bytes]
    """
    if len(data) < 6:
        return None
    sig_size = int.from_bytes(data[4:6], "big")
    if len(data) < 6 + sig_size or sig_size == 0:
        return None
    return data[6 : 6 + sig_size]
