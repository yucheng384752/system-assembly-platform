"""
License verification for Form System Kit Composer generated systems.
Checks RSA-PSS signature, expiry, and machine binding. Startup code must treat
invalid results as fatal.

Machine binding:
  - machineFingerprint accepts only the TPM EK certificate SHA-256.
  - /etc/machine-id or Windows MachineGuid fallback is diagnostic-only and not accepted for binding.
  - machinePublicKey remains supported for existing TPM challenge-response licenses.
  - license.lic may embed machinePublicKey (RSA-2048 PEM from TPM signing key handle 0x81000001)
  - At verification, backend calls tpm2_sign to sign a random nonce with the persisted key
  - Signature is verified against machinePublicKey in the license
  - The TPM private key never leaves the chip — cryptographically non-exportable
  - Install tpm2-tools to activate TPM EK certificate binding on Linux.
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

_TPM_SIGNING_HANDLE = "0x81000001"

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
    here = Path(__file__).resolve()
    candidates = [
        Path(os.getcwd()) / "license.lic",
        Path(os.getcwd()).parent / "license.lic",
    ]
    for idx in (3, 4, 5):
        try:
            candidates.insert(idx - 3, here.parents[idx] / "license.lic")
        except IndexError:
            continue
    for p in candidates:
        try:
            if p.exists():
                return p
        except (OSError, ValueError):
            continue
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
        # salt_length=32 matches Node.js RSA_PSS_SALTLEN_DIGEST for SHA-256.
        # PSS.DIGEST_LENGTH is only available in cryptography >= 41; use the
        # literal value so older deployments (Ubuntu 22.04 default) are supported.
        pub_key.verify(
            base64.b64decode(sig_b64),
            payload_str.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=32,
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

    # Machine fingerprint binding requires TPM EK; machine-id fallback is diagnostic-only.
    # Keep machinePublicKey support below for existing TPM challenge-response licenses.
    expected_fp = payload.get("machineFingerprint")
    if expected_fp:
        current_fp = _tpm_ek_fingerprint()
        if current_fp is None:
            return LicenseResult(
                valid=False,
                reason="machine-bound license requires a TPM EK fingerprint; machine-id/MachineGuid fallback is not accepted",
            )
        if current_fp != expected_fp:
            return LicenseResult(valid=False, reason="machine fingerprint mismatch - license issued for a different machine")

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


def _tpm_subprocess_env() -> dict:
    """
    回傳給 tpm2_* subprocess 的環境變數。
    若 os.environ 已有 TPM2TOOLS_TCTI 則沿用；否則偵測 swtpm 狀態目錄，
    自動指向 swtpm socket（後端進程通常未繼承 /etc/profile.d/ 的 TCTI）。
    """
    env = dict(os.environ)
    if env.get("TPM2TOOLS_TCTI"):
        return env
    # swtpm 由 01_tpm_full_setup.sh 佈建於 /opt/hiba/tpm/swtpm-state
    swtpm_marker = Path("/opt/hiba/tpm/swtpm-state/.initialized")
    if swtpm_marker.exists():
        env["TPM2TOOLS_TCTI"] = "swtpm:host=127.0.0.1,port=2321"
    return env


def _tpm_sign_nonce(nonce: bytes) -> bytes | None:
    """
    Ask TPM handle 0x81000001 to sign a nonce with RSASSA-PKCS1v15-SHA256.
    Tries --format plain first (tpm2-tools >= 4.x); falls back to parsing TPMT_SIGNATURE.
    Returns raw RSA signature bytes, or None if unavailable.
    """
    sub_env = _tpm_subprocess_env()
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
                capture_output=True, timeout=10, env=sub_env,
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
            r = subprocess.run(base_cmd, capture_output=True, timeout=10, env=sub_env)
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


def _get_machine_fingerprint() -> str | None:
    """Return TPM EK SHA-256 when available; otherwise diagnostic-only machine-id/MachineGuid SHA-256."""
    tpm = _tpm_ek_fingerprint()
    if tpm:
        logger.debug("license: fingerprint source=tpm-ek")
        return tpm
    fallback = _machine_id_fingerprint()
    if fallback:
        logger.warning("license: TPM fingerprint unavailable; falling back to machine-id/MachineGuid")
    return fallback


def _tpm_ek_fingerprint() -> str | None:
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                [
                    "powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "$ek = Get-TpmEndorsementKeyInfo -HashAlgorithm Sha256; "
                    "if ($ek -and $ek.PublicKeyHash) "
                    "{ $ek.PublicKeyHash.Replace('-','').ToLower() } else { exit 1 }",
                ],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                return hashlib.sha256(result.stdout.strip().encode()).hexdigest()
            return None

        result = subprocess.run(
            ["tpm2_getekcertificate", "--ek-certificate", "/dev/stdout"],
            capture_output=True, timeout=5, env=_tpm_subprocess_env(),
        )
        if result.returncode == 0 and result.stdout:
            return hashlib.sha256(result.stdout).hexdigest()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    except Exception as exc:
        logger.debug("license: TPM EK fingerprint unavailable: %s", exc)
    return None


def _machine_id_fingerprint() -> str | None:
    if platform.system() == "Windows":
        try:
            result = subprocess.run(
                [
                    "powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "(Get-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Cryptography' -Name MachineGuid).MachineGuid",
                ],
                capture_output=True, text=True, timeout=10,
            )
            raw = result.stdout.strip().lower() if result.returncode == 0 else ""
            return hashlib.sha256(raw.encode()).hexdigest() if raw else None
        except Exception:
            return None

    machine_id_path = Path("/etc/machine-id")
    if not machine_id_path.exists():
        return None
    try:
        raw = machine_id_path.read_text("utf-8").strip().lower()
        return hashlib.sha256(raw.encode()).hexdigest() if raw else None
    except (OSError, UnicodeDecodeError):
        return None
