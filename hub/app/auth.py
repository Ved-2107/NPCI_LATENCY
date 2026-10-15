"""Lightweight RFC 7519 JWT authentication and Role-Based Access Control (RBAC).

Provides signed tokens and role guards for:
- sender
- compliance_officer
- auditor
- admin
"""
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional
from fastapi import Header, HTTPException

SECRET_KEY = os.environ.get("REMITCHAIN_JWT_SECRET", "remitchain-production-grade-secret-key-32b")
TOKEN_EXPIRY_SECONDS = 3600 * 24  # 24 hours

VALID_ROLES = {"sender", "compliance_officer", "auditor", "admin"}


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    padding = "=" * (4 - (len(s) % 4)) if len(s) % 4 != 0 else ""
    return base64.urlsafe_b64decode(s + padding)


def create_access_token(user_id: str, role: str, expires_in: int = TOKEN_EXPIRY_SECONDS) -> str:
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role: {role}. Must be one of {VALID_ROLES}")

    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + expires_in,
    }

    h_str = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_str = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    msg = f"{h_str}.{p_str}".encode("utf-8")
    sig = hmac.new(SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).digest()
    sig_str = _b64url_encode(sig)
    return f"{h_str}.{p_str}.{sig_str}"


def decode_access_token(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed token")

    h_str, p_str, sig_str = parts
    msg = f"{h_str}.{p_str}".encode("utf-8")
    expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).digest()
    actual_sig = _b64url_decode(sig_str)

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise ValueError("Invalid token signature")

    payload = json.loads(_b64url_decode(p_str).decode("utf-8"))
    if time.time() > payload.get("exp", 0):
        raise ValueError("Token has expired")

    return payload


def get_current_user(
    authorization: Optional[str] = Header(None),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> dict:
    """Extract and authenticate user identity and role from Bearer token or development headers."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        try:
            payload = decode_access_token(token)
            return {
                "userId": payload["sub"],
                "role": payload["role"],
                "authenticated": True,
            }
        except Exception as e:
            raise HTTPException(status_code=401, detail={"code": "ERR_INVALID_AUTH", "message": str(e)})

    # Fallback to dev headers if token not supplied
    if x_user_role:
        role = x_user_role.lower()
        if role in VALID_ROLES:
            return {
                "userId": x_user_id or "dev_user",
                "role": role,
                "authenticated": False,
            }

    # Fallback when no auth headers provided:
    # In strict mode, default role is 'sender'.
    # In permissive/demo mode (default), default role is 'admin' to preserve unauthenticated demo flows.
    auth_strict = os.environ.get("REMITCHAIN_AUTH_STRICT", "0") == "1"
    default_role = "sender" if auth_strict else "admin"
    return {
        "userId": x_user_id or "default_user",
        "role": default_role,
        "authenticated": False,
    }


def require_role(*allowed_roles: str):
    """Dependency factory checking that the current user possesses one of the allowed roles."""
    def checker(
        authorization: Optional[str] = Header(None),
        x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
        x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    ) -> dict:
        user = get_current_user(authorization, x_user_role, x_user_id)
        if user["role"] not in allowed_roles and user["role"] != "admin":
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "ERR_FORBIDDEN",
                    "message": f"Role '{user['role']}' is not authorized. Required: {list(allowed_roles)}",
                },
            )
        return user
    return checker
