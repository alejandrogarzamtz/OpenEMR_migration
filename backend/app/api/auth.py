import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import AuditEvent, AuthSession, CommunicationDelivery, PasswordResetToken, User
from ..schemas import Login, PasswordResetConfirm, PasswordResetRequest, Token
from ..security import create_session, create_token, current_staff_session, current_user, password_hash, rotate_session, token_digest

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
STAFF_COOKIE = "staff_refresh_token"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def set_refresh_cookie(response: Response, value: str) -> None:
    response.set_cookie(STAFF_COOKIE, value, max_age=settings.refresh_token_days * 86400, httponly=True, secure=settings.secure_cookies, samesite="strict", path="/api/v1/auth")


@router.post("/token", response_model=Token)
def login(body: Login, request: Request, response: Response, db: Session = Depends(get_db)) -> Token:
    user = db.scalar(select(User).where(User.email == body.email))
    if not user or not user.active or not password_hash.verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    session, refresh_token = create_session(db, "staff", user_id=user.id, ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"))
    db.add(AuditEvent(actor_id=user.id, action="login", resource_type="auth_session", resource_id=session.uuid))
    db.commit()
    set_refresh_cookie(response, refresh_token)
    return Token(access_token=create_token(user, session))


@router.post("/refresh", response_model=Token)
def refresh(response: Response, refresh_token: str | None = Cookie(default=None, alias=STAFF_COOKIE), db: Session = Depends(get_db)) -> Token:
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token is missing")
    digest = token_digest(refresh_token)
    session = db.scalar(select(AuthSession).where(AuthSession.identity_kind == "staff", or_(AuthSession.refresh_token_hash == digest, AuthSession.previous_refresh_token_hash == digest)))
    if not session or session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if session.previous_refresh_token_hash == digest:
        session.revoked_at = utc_now(); session.revoke_reason = "refresh-token-reuse"; db.commit()
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if aware(session.refresh_expires_at) <= utc_now():
        session.revoked_at = utc_now(); session.revoke_reason = "expired"; db.commit()
        raise HTTPException(status_code=401, detail="Refresh token expired")
    user = db.get(User, session.user_id) if session.user_id else None
    if not user or not user.active:
        session.revoked_at = utc_now(); session.revoke_reason = "inactive-identity"; db.commit()
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    next_refresh_token = rotate_session(session)
    db.commit()
    set_refresh_cookie(response, next_refresh_token)
    return Token(access_token=create_token(user, session))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, session: AuthSession = Depends(current_staff_session), user: User = Depends(current_user), db: Session = Depends(get_db)):
    session.revoked_at = utc_now(); session.revoke_reason = "logout"
    db.add(AuditEvent(actor_id=user.id, action="logout", resource_type="auth_session", resource_id=session.uuid))
    db.commit()
    response.delete_cookie(STAFF_COOKIE, path="/api/v1/auth", secure=settings.secure_cookies, httponly=True, samesite="strict")


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(body: PasswordResetRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email, User.active.is_(True)))
    if user:
        now = utc_now()
        for item in db.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))):
            item.used_at = now
        raw_token = secrets.token_urlsafe(48)
        db.add(PasswordResetToken(user_id=user.id, token_hash=token_digest(raw_token), expires_at=now + timedelta(minutes=settings.password_reset_minutes)))
        db.add(CommunicationDelivery(channel="email", recipient=user.email, subject="OpenRM password reset", body=f"Use this one-time link to reset your password: {settings.public_web_url.rstrip('/')}/reset-password?token={raw_token}", template_name="staff-password-reset"))
        db.commit()
    return {"detail": "If the account exists, password reset instructions have been queued."}


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(body: PasswordResetConfirm, db: Session = Depends(get_db)):
    reset = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_digest(body.token)))
    now = utc_now()
    if not reset or reset.used_at is not None or aware(reset.expires_at) <= now:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset token")
    user = db.get(User, reset.user_id)
    if not user or not user.active:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset token")
    user.password_hash = password_hash.hash(body.new_password)
    reset.used_at = now
    for session in db.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))):
        session.revoked_at = now; session.revoke_reason = "password-reset"
    db.add(AuditEvent(actor_id=user.id, action="password-reset", resource_type="user", resource_id=user.uuid))
    db.commit()
