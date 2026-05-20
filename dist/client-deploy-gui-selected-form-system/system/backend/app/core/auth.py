import hashlib
import hmac
import secrets


def generate_api_key() -> str:
    """Generate a new raw API key (to be shown once to the operator)."""
    # urlsafe base64, typically ~43 chars for 32 bytes
    return secrets.token_urlsafe(32)


def hash_api_key(*, raw_key: str, secret_key: str) -> str:
    """Hash raw API key using HMAC-SHA256 with server secret as pepper."""
    if not raw_key:
        raise ValueError("raw_key is required")
    if not secret_key:
        raise ValueError("secret_key is required")
    digest = hmac.new(
        secret_key.encode("utf-8"), raw_key.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return digest


def verify_api_key(*, raw_key: str, secret_key: str, expected_hash: str) -> bool:
    """Constant-time verification for raw API key."""
    if not raw_key or not expected_hash:
        return False
    got = hash_api_key(raw_key=raw_key, secret_key=secret_key)
    return secrets.compare_digest(got, expected_hash)
