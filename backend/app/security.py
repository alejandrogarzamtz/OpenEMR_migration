from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import User

password_hash = PasswordHash.recommended()
bearer = HTTPBearer()


def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    expiry = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    claims = {
        "sub": str(user.id),
        "jti": str(uuid4()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": expiry,
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "jti", "iss", "aud", "iat", "nbf", "exp"]},
        )
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        user = None
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="Invalid or expired credentials")
    return user


def user_has_permission(user: User, section: str, value: str, mode: str = "read") -> bool:
    grants = set(user.permissions or [])
    candidates = {
        "*:*:*",
        f"{section}:*:*",
        f"{section}:{value}:*",
        f"{section}:{value}:{mode}",
    }
    return bool(grants & candidates)


def require_permission(section: str, value: str, mode: str = "read") -> Callable[..., User]:
    def permission_dependency(user: User = Depends(current_user)) -> User:
        if not user_has_permission(user, section, value, mode):
            raise HTTPException(status_code=403, detail="Permission denied")
        return user

    return permission_dependency


# Legacy phpGACL-compatible section/value names. Route modules use these
# dependencies so authorization cannot be accidentally delegated to the UI.
patient_demographics_user = require_permission("patients", "demo")
patient_demographics_write_user = require_permission("patients", "demo", "write")
clinical_user = require_permission("patients", "med")
appointment_user = require_permission("patients", "appt")
appointment_write_user = require_permission("patients", "appt", "write")
encounter_user = require_permission("encounters", "auth_a")
document_user = require_permission("patients", "docs")
billing_user = require_permission("acct", "bill")
