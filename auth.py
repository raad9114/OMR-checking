from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from rbac import UserPrincipal


PBKDF2_ALGORITHM = "sha256"
PBKDF2_ITERATIONS = 390000


class AuthenticationError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def hash_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"pbkdf2_{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations, salt, expected = password_hash.split("$", 3)
        if scheme != f"pbkdf2_{PBKDF2_ALGORITHM}":
            return False
        digest = hashlib.pbkdf2_hmac(
            PBKDF2_ALGORITHM,
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False


@dataclass(frozen=True)
class LoginResult:
    user: UserPrincipal
    message: str


def principal_from_record(record: Mapping[str, Any]) -> UserPrincipal:
    permissions = record.get("permissions") or []
    return UserPrincipal(
        id=int(record["id"]),
        name=str(record.get("name") or ""),
        username=str(record.get("username") or ""),
        email=str(record.get("email") or ""),
        role_name=str(record.get("role_name") or ""),
        permissions=set(permissions),
        is_active=bool(record.get("is_active", True)),
    )


def authenticate(identity: str, password: str, repository: Any, ip_address: str = "") -> LoginResult:
    user = repository.find_user_for_login(identity)
    if not user:
        repository.record_failed_login(identity, ip_address)
        raise AuthenticationError("Invalid username/email or password.")
    if not user.get("is_active", True):
        repository.audit_log(user.get("id"), "login.blocked_inactive", "users", user.get("id"), None, None, ip_address)
        raise AuthenticationError("This account is inactive.")
    if not verify_password(password, user.get("password_hash", "")):
        repository.record_failed_login(identity, ip_address, user_id=user.get("id"))
        raise AuthenticationError("Invalid username/email or password.")
    repository.record_successful_login(user["id"], ip_address)
    fresh_user = repository.get_user_with_permissions(user["id"])
    return LoginResult(principal_from_record(fresh_user), "Logged in successfully.")


def change_password(user_id: int, old_password: str, new_password: str, repository: Any) -> None:
    user = repository.get_user_with_permissions(user_id)
    if not verify_password(old_password, user.get("password_hash", "")):
        raise AuthenticationError("Current password is incorrect.")
    repository.update_user_password(user_id, hash_password(new_password))


def admin_reset_password(user_id: int, new_password: str, repository: Any, acting_user_id: int) -> None:
    repository.update_user_password(user_id, hash_password(new_password), acting_user_id=acting_user_id)
