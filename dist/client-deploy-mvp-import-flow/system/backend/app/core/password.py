import base64
import hashlib
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class PasswordHashParams:
    algorithm: str = "pbkdf2_sha256"
    iterations: int = 210_000
    salt_bytes: int = 16


_DEFAULT = PasswordHashParams()


def hash_password(password: str, *, params: PasswordHashParams = _DEFAULT) -> str:
    """Hash password with PBKDF2-HMAC-SHA256.

    Stored format:
        pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>

    No external dependencies.
    """
    pw = (password or "").encode("utf-8")
    if not pw:
        raise ValueError("password is required")

    salt = secrets.token_bytes(params.salt_bytes)
    dk = hashlib.pbkdf2_hmac("sha256", pw, salt, params.iterations)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
    dk_b64 = base64.urlsafe_b64encode(dk).decode("ascii").rstrip("=")
    return f"{params.algorithm}${params.iterations}${salt_b64}${dk_b64}"


def verify_password(password: str, stored: str) -> bool:
    try:
        pw = (password or "").encode("utf-8")
        if not pw:
            return False
        parts = (stored or "").split("$")
        if len(parts) != 4:
            return False
        alg, iters_s, salt_b64, dk_b64 = parts
        if alg != "pbkdf2_sha256":
            return False
        iterations = int(iters_s)

        def _b64decode_nopad(s: str) -> bytes:
            padded = s + "=" * ((4 - (len(s) % 4)) % 4)
            return base64.urlsafe_b64decode(padded.encode("ascii"))

        salt = _b64decode_nopad(salt_b64)
        expected = _b64decode_nopad(dk_b64)
        got = hashlib.pbkdf2_hmac("sha256", pw, salt, iterations)
        return secrets.compare_digest(got, expected)
    except Exception:
        return False
