from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets
from uuid import uuid4
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import AuthSession, PortalAccount, User

password_hash = PasswordHash.recommended()
bearer = HTTPBearer()


def token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def create_session(
    db: Session,
    identity_kind: str,
    *,
    user_id: int | None = None,
    portal_account_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[AuthSession, str]:
    refresh_token = secrets.token_urlsafe(48)
    session = AuthSession(
        identity_kind=identity_kind,
        user_id=user_id,
        portal_account_id=portal_account_id,
        access_jti=str(uuid4()),
        refresh_token_hash=token_digest(refresh_token),
        refresh_expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days),
        ip_address=ip_address,
        user_agent=user_agent[:500] if user_agent else None,
    )
    db.add(session)
    db.flush()
    return session, refresh_token


def rotate_session(session: AuthSession) -> str:
    refresh_token = secrets.token_urlsafe(48)
    session.previous_refresh_token_hash = session.refresh_token_hash
    session.refresh_token_hash = token_digest(refresh_token)
    session.access_jti = str(uuid4())
    session.last_used_at = datetime.now(timezone.utc)
    return refresh_token


def create_token(user: User, session: AuthSession) -> str:
    now = datetime.now(timezone.utc)
    expiry = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    claims = {
        "sub": str(user.id),
        "kind": "staff",
        "jti": session.access_jti,
        "sid": session.uuid,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": expiry,
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")


def authenticated_session(credentials: HTTPAuthorizationCredentials, db: Session, expected_kind: str) -> tuple[AuthSession, dict]:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "sid", "kind", "jti", "iss", "aud", "iat", "nbf", "exp"]},
        )
        session = db.scalar(select(AuthSession).where(AuthSession.uuid == payload["sid"]))
        if (
            payload.get("kind") != expected_kind
            or not session
            or session.identity_kind != expected_kind
            or session.revoked_at is not None
            or session.access_jti != payload.get("jti")
        ):
            raise ValueError("session mismatch")
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired credentials")
    return session, payload


def current_staff_session(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> AuthSession:
    session, _ = authenticated_session(credentials, db, "staff")
    return session


def current_user(session: AuthSession = Depends(current_staff_session), db: Session = Depends(get_db)) -> User:
    user = db.get(User, session.user_id) if session.user_id else None
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="Invalid or expired credentials")
    return user


def create_portal_token(account: PortalAccount, session: AuthSession) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(account.id),
        "patient": str(account.patient_id),
        "kind": "portal",
        "jti": session.access_jti,
        "sid": session.uuid,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")


def current_portal_session(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> AuthSession:
    session, _ = authenticated_session(credentials, db, "portal")
    return session


def current_portal_account(session: AuthSession = Depends(current_portal_session), db: Session = Depends(get_db)) -> PortalAccount:
    account = db.get(PortalAccount, session.portal_account_id) if session.portal_account_id else None
    if not account or not account.active:
        raise HTTPException(status_code=401, detail="Invalid or expired portal credentials")
    return account


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
inventory_user = require_permission("inventory", "lots")
inventory_write_user = require_permission("inventory", "lots", "write")
inventory_dispense_user = require_permission("inventory", "consumption", "write")
administration_user = require_permission("admin", "users")
administration_write_user = require_permission("admin", "users", "write")
communication_user = require_permission("patients", "notes")
communication_write_user = require_permission("patients", "notes", "write")
