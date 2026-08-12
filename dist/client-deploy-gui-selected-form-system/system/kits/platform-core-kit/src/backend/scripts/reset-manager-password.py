"""
Break-glass: reset a manager account password directly in the database.
Use when the manager cannot log in and no other admin account is available.

Usage (run from the backend directory):
    python scripts/reset-manager-password.py --username admin
    python scripts/reset-manager-password.py --username admin --new-password "MyP@ss!"
    python scripts/reset-manager-password.py --username admin --list
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import os
import secrets
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Inline password hashing — mirrors app/core/password.py, no app imports needed
# ---------------------------------------------------------------------------

def hash_password(password: str, iterations: int = 210_000) -> str:
    pw = password.encode("utf-8")
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw, salt, iterations)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
    dk_b64 = base64.urlsafe_b64encode(dk).decode("ascii").rstrip("=")
    return f"pbkdf2_sha256${iterations}${salt_b64}${dk_b64}"


# ---------------------------------------------------------------------------
# Database connection — reads DATABASE_URL from .env in cwd or parent dirs
# ---------------------------------------------------------------------------

def _load_env() -> None:
    for parent in [Path.cwd(), Path.cwd().parent, Path(__file__).parents[2]]:
        env_file = parent / ".env"
        if env_file.exists():
            for line in env_file.read_text("utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
            return


def _get_engine():
    try:
        from sqlalchemy import create_engine
    except ImportError:
        sys.exit("ERROR: sqlalchemy not installed. Run: pip install sqlalchemy")

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        sys.exit("ERROR: DATABASE_URL not set. Make sure .env is present.")

    # psycopg2 driver alias
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    return create_engine(db_url)


# ---------------------------------------------------------------------------
# Main operations
# ---------------------------------------------------------------------------

def list_managers(engine) -> None:
    from sqlalchemy import text
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT u.username, u.role, u.is_active, u.must_change_password, t.code "
            "FROM tenant_users u JOIN tenants t ON t.id = u.tenant_id "
            "WHERE u.role IN ('manager','admin') ORDER BY t.code, u.username"
        )).fetchall()
    if not rows:
        print("No manager/admin accounts found.")
        return
    print(f"{'Username':<20} {'Role':<10} {'Active':<8} {'MustChange':<12} {'Tenant'}")
    print("-" * 60)
    for row in rows:
        print(f"{row[0]:<20} {row[1]:<10} {str(row[2]):<8} {str(row[3]):<12} {row[4]}")


def reset_password(engine, username: str, new_password: str) -> None:
    from sqlalchemy import text

    new_hash = hash_password(new_password)

    with engine.begin() as conn:
        result = conn.execute(text(
            "UPDATE tenant_users SET password_hash = :h, must_change_password = true "
            "WHERE username = :u AND role IN ('manager','admin') "
            "RETURNING username, role"
        ), {"h": new_hash, "u": username})
        updated = result.fetchall()

    if not updated:
        sys.exit(f"ERROR: No manager/admin account found with username '{username}'.")

    for row in updated:
        print(f"OK  Reset password for {row[0]} ({row[1]}) — must_change_password set to true")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset manager account password (break-glass)")
    parser.add_argument("--username", "-u", required=False, help="Manager username to reset")
    parser.add_argument("--new-password", "-p", required=False, help="New password (prompted if omitted)")
    parser.add_argument("--list", "-l", action="store_true", help="List all manager/admin accounts")
    args = parser.parse_args()

    _load_env()
    engine = _get_engine()

    if args.list:
        list_managers(engine)
        return

    if not args.username:
        parser.error("--username is required unless --list is used")

    new_password = args.new_password
    if not new_password:
        new_password = getpass.getpass(f"New password for '{args.username}': ")
        confirm = getpass.getpass("Confirm password: ")
        if new_password != confirm:
            sys.exit("ERROR: Passwords do not match.")

    if len(new_password) < 8:
        sys.exit("ERROR: Password must be at least 8 characters.")

    reset_password(engine, args.username, new_password)
    print("Done. The account will be prompted to change password on next login.")


if __name__ == "__main__":
    main()
