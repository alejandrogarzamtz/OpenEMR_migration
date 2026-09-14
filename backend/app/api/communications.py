import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..config import settings
from ..mfa import decrypt_secret, encrypt_secret, generate_secret, matching_step, provisioning_uri, recovery_codes, recovery_digest
from ..models import (
    AuditEvent,
    AuthSession,
    ClinicalTask,
    CommunicationDelivery,
    Encounter,
    IdentityAuditEvent,
    MessageThread,
    Patient,
    PortalAccount,
    PortalMfaChallenge,
    PortalMfaRegistration,
    PortalPasswordResetToken,
    SecureMessage,
    User,
)
from ..schemas import (
    ClinicalTaskCreate,
    ClinicalTaskOut,
    CommunicationDeliveryOut,
    MessageCreate,
    MessageReply,
    MessageThreadOut,
    PortalAccountCreate,
    PortalAccountOut,
    PortalLogin,
    PortalLoginResult,
    PortalPasswordChange,
    PortalToken,
    SecureMessageOut,
    MfaChallengeComplete,
    MfaCode,
    MfaDisable,
    MfaEnrollmentOut,
    MfaEnrollmentStart,
    MfaRecoveryCodesOut,
    MfaStatusOut,
    PasswordResetConfirm,
    PasswordResetRequest,
    Token,
)
from ..security import (
    administration_user,
    communication_user,
    communication_write_user,
    create_portal_token,
    create_session,
    current_portal_account,
    current_portal_session,
    password_hash,
    rotate_session,
    token_digest,
)
from ..services.patients import patient_by_uuid
from ..services.portal_access import PortalPatientContext, require_portal_scope

router = APIRouter(prefix="/api/v1", tags=["communications"])
PORTAL_COOKIE = "portal_refresh_token"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def set_portal_cookie(response: Response, value: str) -> None:
    response.set_cookie(PORTAL_COOKIE, value, max_age=settings.refresh_token_days * 86400, httponly=True, secure=settings.secure_cookies, samesite="strict", path="/api/v1/portal")


def portal_audit(db: Session, account: PortalAccount, action: str, resource_type: str, resource_id: str | None = None, patient_id: int | None = None) -> None:
    db.add(IdentityAuditEvent(identity_kind="portal", portal_account_id=account.id, patient_id=patient_id if patient_id is not None else account.patient_id, action=action, resource_type=resource_type, resource_id=resource_id))


def issue_portal_session(account: PortalAccount, request: Request, response: Response, db: Session) -> PortalToken:
    account.last_login_at = now_utc()
    session, refresh_token = create_session(db, "portal", portal_account_id=account.id, ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"))
    portal_audit(db, account, "login", "auth_session", session.uuid)
    db.commit()
    set_portal_cookie(response, refresh_token)
    return PortalToken(access_token=create_portal_token(account, session), force_password_reset=account.force_password_reset)


def consume_portal_mfa_code(registration: PortalMfaRegistration, code: str) -> bool:
    step = matching_step(decrypt_secret(registration.encrypted_secret), code)
    if step is not None and (registration.last_used_step is None or step > registration.last_used_step):
        registration.last_used_step = step
        return True
    digest = recovery_digest(code)
    if digest in registration.recovery_code_hashes:
        registration.recovery_code_hashes = [item for item in registration.recovery_code_hashes if item != digest]
        return True
    return False


def account_out(account: PortalAccount, patient: Patient) -> PortalAccountOut:
    return PortalAccountOut(
        uuid=account.uuid,
        patient_uuid=patient.uuid,
        username=account.username,
        email=account.email,
        display_name=account.display_name,
        identity_type=account.identity_type,
        active=account.active,
        force_password_reset=account.force_password_reset,
        last_login_at=account.last_login_at,
    )


def message_out(message: SecureMessage) -> SecureMessageOut:
    return SecureMessageOut(**{key: getattr(message, key) for key in SecureMessageOut.model_fields})


def thread_out(db: Session, thread: MessageThread, patient: Patient, include_messages: bool = True) -> MessageThreadOut:
    messages = []
    if include_messages:
        messages = list(db.scalars(select(SecureMessage).where(SecureMessage.thread_id == thread.id).order_by(SecureMessage.created_at)))
    return MessageThreadOut(
        uuid=thread.uuid,
        patient_uuid=patient.uuid,
        patient_name=f"{patient.first_name} {patient.last_name}",
        subject=thread.subject,
        status=thread.status,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        messages=[message_out(item) for item in messages],
    )


def task_out(task: ClinicalTask, patient: Patient, encounter: Encounter | None, assigned: User | None) -> ClinicalTaskOut:
    return ClinicalTaskOut(
        uuid=task.uuid,
        patient_uuid=patient.uuid,
        encounter_uuid=encounter.uuid if encounter else None,
        assigned_user_uuid=assigned.uuid if assigned else None,
        method=task.method,
        comment=task.comment,
        status=task.status,
        due_at=task.due_at,
        completed_at=task.completed_at,
    )


def queue_patient_notice(db: Session, patient: Patient, message: SecureMessage) -> None:
    if not patient.allow_email or not patient.email:
        return
    db.add(
        CommunicationDelivery(
            patient_id=patient.id,
            message_id=message.id,
            channel="email",
            recipient=patient.email,
            subject="New secure message",
            body="A new secure message is available. Sign in to the patient portal to view it.",
            template_name="secure-message-notice",
        )
    )


def portal_thread(db: Session, context: PortalPatientContext, thread_uuid: str) -> tuple[MessageThread, Patient]:
    row = db.execute(
        select(MessageThread, Patient)
        .join(Patient, Patient.id == MessageThread.patient_id)
        .where(MessageThread.uuid == thread_uuid, MessageThread.patient_id == context.patient.id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Message thread not found")
    return row


def portal_ready_account(account: PortalAccount = Depends(current_portal_account)) -> PortalAccount:
    if account.force_password_reset:
        raise HTTPException(status_code=403, detail="Password reset required")
    return account


@router.post("/patients/{patient_uuid}/portal-account", response_model=PortalAccountOut, status_code=status.HTTP_201_CREATED)
def create_portal_account(body: PortalAccountCreate, patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(communication_write_user)):
    patient = patient_by_uuid(db, patient_uuid)
    if not patient.portal_allowed:
        raise HTTPException(status_code=409, detail="Patient portal access is not enabled")
    account = db.scalar(select(PortalAccount).where(PortalAccount.patient_id == patient.id))
    if account:
        account.username = body.username
        account.password_hash = password_hash.hash(body.temporary_password)
        account.active = True
        account.force_password_reset = True
        account.failed_attempts = 0
        account.locked_until = None
        account.email = patient.email
        account.display_name = f"{patient.first_name} {patient.last_name}"
        account.identity_type = "patient"
    else:
        account = PortalAccount(patient_id=patient.id, username=body.username, email=patient.email, display_name=f"{patient.first_name} {patient.last_name}", identity_type="patient", password_hash=password_hash.hash(body.temporary_password))
        db.add(account)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Portal username is already in use")
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="portal_account", resource_id=account.uuid))
    db.commit()
    db.refresh(account)
    return account_out(account, patient)


@router.get("/patients/{patient_uuid}/portal-account", response_model=PortalAccountOut)
def get_portal_account(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(communication_user)):
    patient = patient_by_uuid(db, patient_uuid)
    account = db.scalar(select(PortalAccount).where(PortalAccount.patient_id == patient.id))
    if not account:
        raise HTTPException(status_code=404, detail="Portal account not found")
    return account_out(account, patient)


@router.post("/portal/auth/token", response_model=PortalLoginResult)
def portal_login(body: PortalLogin, request: Request, response: Response, db: Session = Depends(get_db)) -> PortalLoginResult:
    account = db.scalar(select(PortalAccount).where(PortalAccount.username == body.username))
    current = now_utc()
    locked_until = account.locked_until if account else None
    if locked_until and locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    patient = db.get(Patient, account.patient_id) if account and account.patient_id is not None else None
    patient_access_denied = bool(account and account.patient_id is not None and (not patient or not patient.portal_allowed))
    if not account or not account.active or patient_access_denied or (locked_until and locked_until > current):
        raise HTTPException(status_code=401, detail="Invalid portal credentials")
    if not password_hash.verify(body.password, account.password_hash):
        account.failed_attempts += 1
        if account.failed_attempts >= 5:
            account.locked_until = current + timedelta(minutes=15)
            account.failed_attempts = 0
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid portal credentials")
    account.failed_attempts = 0
    account.locked_until = None
    registration = db.scalar(select(PortalMfaRegistration).where(PortalMfaRegistration.portal_account_id == account.id, PortalMfaRegistration.active.is_(True)))
    if registration:
        challenge_token = secrets.token_urlsafe(48)
        db.add(PortalMfaChallenge(portal_account_id=account.id, token_hash=token_digest(challenge_token), expires_at=current + timedelta(minutes=settings.mfa_challenge_minutes)))
        portal_audit(db, account, "mfa-challenge", "portal_account", account.uuid)
        db.commit()
        return PortalLoginResult(mfa_required=True, challenge_token=challenge_token, force_password_reset=account.force_password_reset)
    token = issue_portal_session(account, request, response, db)
    return PortalLoginResult(access_token=token.access_token, force_password_reset=token.force_password_reset)


@router.post("/portal/auth/mfa/challenge", response_model=PortalToken)
def complete_portal_mfa_challenge(body: MfaChallengeComplete, request: Request, response: Response, db: Session = Depends(get_db)):
    challenge = db.scalar(select(PortalMfaChallenge).where(PortalMfaChallenge.token_hash == token_digest(body.challenge_token)))
    current = now_utc()
    if not challenge or challenge.consumed_at is not None or aware(challenge.expires_at) <= current or challenge.attempts >= 5:
        raise HTTPException(status_code=401, detail="Invalid or expired MFA challenge")
    registration = db.scalar(select(PortalMfaRegistration).where(PortalMfaRegistration.portal_account_id == challenge.portal_account_id, PortalMfaRegistration.active.is_(True)))
    account = db.get(PortalAccount, challenge.portal_account_id)
    challenge.attempts += 1
    patient = db.get(Patient, account.patient_id) if account and account.patient_id is not None else None
    patient_access_denied = bool(account and account.patient_id is not None and (not patient or not patient.portal_allowed))
    if not registration or not account or not account.active or patient_access_denied or not consume_portal_mfa_code(registration, body.code):
        if challenge.attempts >= 5:
            challenge.consumed_at = current
        if account:
            portal_audit(db, account, "mfa-failure", "mfa_challenge", challenge.uuid)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid or expired MFA challenge")
    challenge.consumed_at = current
    portal_audit(db, account, "mfa-success", "mfa_challenge", challenge.uuid)
    return issue_portal_session(account, request, response, db)


@router.post("/portal/auth/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def request_portal_password_reset(body: PasswordResetRequest, db: Session = Depends(get_db)):
    rows = db.execute(select(PortalAccount, Patient).outerjoin(Patient, Patient.id == PortalAccount.patient_id).where(func.lower(PortalAccount.email) == str(body.email).lower(), PortalAccount.active.is_(True), (PortalAccount.patient_id.is_(None) | Patient.portal_allowed.is_(True)))).all()
    if len(rows) == 1:
        account, patient = rows[0]
        current = now_utc()
        recent = db.scalar(select(PortalPasswordResetToken).where(PortalPasswordResetToken.portal_account_id == account.id).order_by(PortalPasswordResetToken.created_at.desc()).limit(1))
        if recent and aware(recent.created_at) > current - timedelta(seconds=settings.password_reset_request_cooldown_seconds):
            return {"detail": "If the portal account exists, password reset instructions have been queued."}
        for item in db.scalars(select(PortalPasswordResetToken).where(PortalPasswordResetToken.portal_account_id == account.id, PortalPasswordResetToken.used_at.is_(None))):
            item.used_at = current
        raw_token = secrets.token_urlsafe(48)
        db.add(PortalPasswordResetToken(portal_account_id=account.id, token_hash=token_digest(raw_token), expires_at=current + timedelta(minutes=settings.password_reset_minutes)))
        db.add(CommunicationDelivery(patient_id=patient.id if patient else None, channel="email", recipient=account.email, subject="OpenRM patient portal password reset", body=f"Use this one-time link to reset your portal password: {settings.public_web_url.rstrip('/')}/portal/reset-password?token={raw_token}", template_name="portal-password-reset"))
        portal_audit(db, account, "password-reset-request", "portal_account", account.uuid)
        db.commit()
    return {"detail": "If the portal account exists, password reset instructions have been queued."}


@router.post("/portal/auth/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_portal_password_reset(body: PasswordResetConfirm, db: Session = Depends(get_db)):
    reset = db.scalar(select(PortalPasswordResetToken).where(PortalPasswordResetToken.token_hash == token_digest(body.token)))
    current = now_utc()
    if not reset or reset.used_at is not None or aware(reset.expires_at) <= current:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset token")
    account = db.get(PortalAccount, reset.portal_account_id)
    if not account or not account.active:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset token")
    account.password_hash = password_hash.hash(body.new_password); account.force_password_reset = False; account.failed_attempts = 0; account.locked_until = None
    reset.used_at = current
    for session in db.scalars(select(AuthSession).where(AuthSession.portal_account_id == account.id, AuthSession.revoked_at.is_(None))):
        session.revoked_at = current; session.revoke_reason = "password-reset"
    portal_audit(db, account, "password-reset", "portal_account", account.uuid)
    db.commit()


@router.post("/portal/auth/refresh", response_model=PortalToken)
def portal_refresh(response: Response, refresh_token: str | None = Cookie(default=None, alias=PORTAL_COOKIE), db: Session = Depends(get_db)):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token is missing")
    digest = token_digest(refresh_token)
    session = db.scalar(select(AuthSession).where(AuthSession.identity_kind == "portal", or_(AuthSession.refresh_token_hash == digest, AuthSession.previous_refresh_token_hash == digest)))
    if not session or session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if session.previous_refresh_token_hash == digest:
        session.revoked_at = now_utc(); session.revoke_reason = "refresh-token-reuse"; db.commit()
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if aware(session.refresh_expires_at) <= now_utc():
        session.revoked_at = now_utc(); session.revoke_reason = "expired"; db.commit()
        raise HTTPException(status_code=401, detail="Refresh token expired")
    account = db.get(PortalAccount, session.portal_account_id) if session.portal_account_id else None
    patient = db.get(Patient, account.patient_id) if account and account.patient_id is not None else None
    patient_access_denied = bool(account and account.patient_id is not None and (not patient or not patient.portal_allowed))
    if not account or not account.active or patient_access_denied:
        session.revoked_at = now_utc(); session.revoke_reason = "inactive-identity"; db.commit()
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    next_refresh_token = rotate_session(session)
    db.commit()
    set_portal_cookie(response, next_refresh_token)
    return PortalToken(access_token=create_portal_token(account, session), force_password_reset=account.force_password_reset)


@router.post("/portal/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def portal_logout(response: Response, session: AuthSession = Depends(current_portal_session), db: Session = Depends(get_db)):
    session.revoked_at = now_utc(); session.revoke_reason = "logout"; db.commit()
    response.delete_cookie(PORTAL_COOKIE, path="/api/v1/portal", secure=settings.secure_cookies, httponly=True, samesite="strict")


@router.post("/portal/password", status_code=status.HTTP_204_NO_CONTENT)
def change_portal_password(body: PortalPasswordChange, account: PortalAccount = Depends(current_portal_account), session: AuthSession = Depends(current_portal_session), db: Session = Depends(get_db)):
    if not account.force_password_reset and (not body.current_password or not password_hash.verify(body.current_password, account.password_hash)):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    account.password_hash = password_hash.hash(body.new_password)
    account.force_password_reset = False
    account.failed_attempts = 0
    account.locked_until = None
    current = now_utc()
    for other in db.scalars(select(AuthSession).where(AuthSession.portal_account_id == account.id, AuthSession.id != session.id, AuthSession.revoked_at.is_(None))):
        other.revoked_at = current; other.revoke_reason = "password-change"
    portal_audit(db, account, "password-change", "portal_account", account.uuid)
    db.commit()


@router.get("/portal/mfa", response_model=MfaStatusOut)
def portal_mfa_status(account: PortalAccount = Depends(portal_ready_account), db: Session = Depends(get_db)):
    registration = db.scalar(select(PortalMfaRegistration).where(PortalMfaRegistration.portal_account_id == account.id, PortalMfaRegistration.active.is_(True)))
    return MfaStatusOut(enabled=bool(registration), method=registration.method if registration else None, confirmed_at=registration.confirmed_at if registration else None, recovery_codes_remaining=len(registration.recovery_code_hashes) if registration else 0)


@router.post("/portal/mfa/enroll", response_model=MfaEnrollmentOut)
def start_portal_mfa_enrollment(body: MfaEnrollmentStart, account: PortalAccount = Depends(portal_ready_account), db: Session = Depends(get_db)):
    if not password_hash.verify(body.password, account.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    registration = db.scalar(select(PortalMfaRegistration).where(PortalMfaRegistration.portal_account_id == account.id))
    if registration and registration.active:
        raise HTTPException(status_code=409, detail="MFA is already enabled")
    secret = generate_secret()
    if registration:
        registration.encrypted_secret = encrypt_secret(secret); registration.recovery_code_hashes = []; registration.last_used_step = None
    else:
        registration = PortalMfaRegistration(portal_account_id=account.id, encrypted_secret=encrypt_secret(secret)); db.add(registration)
    portal_audit(db, account, "mfa-enrollment-start", "portal_account", account.uuid); db.commit()
    return MfaEnrollmentOut(secret=secret, provisioning_uri=provisioning_uri(secret, account.username))


@router.post("/portal/mfa/confirm", response_model=MfaRecoveryCodesOut)
def confirm_portal_mfa_enrollment(body: MfaCode, session: AuthSession = Depends(current_portal_session), account: PortalAccount = Depends(portal_ready_account), db: Session = Depends(get_db)):
    registration = db.scalar(select(PortalMfaRegistration).where(PortalMfaRegistration.portal_account_id == account.id, PortalMfaRegistration.active.is_(False)))
    if not registration:
        raise HTTPException(status_code=409, detail="No pending MFA enrollment")
    step = matching_step(decrypt_secret(registration.encrypted_secret), body.code)
    if step is None:
        raise HTTPException(status_code=400, detail="Invalid authenticator code")
    codes = recovery_codes(); registration.active = True; registration.confirmed_at = now_utc(); registration.last_used_step = step; registration.recovery_code_hashes = [recovery_digest(code) for code in codes]
    current = now_utc()
    for other in db.scalars(select(AuthSession).where(AuthSession.portal_account_id == account.id, AuthSession.id != session.id, AuthSession.revoked_at.is_(None))):
        other.revoked_at = current; other.revoke_reason = "mfa-enabled"
    portal_audit(db, account, "mfa-enabled", "portal_account", account.uuid); db.commit()
    return MfaRecoveryCodesOut(recovery_codes=codes)


@router.delete("/portal/mfa", status_code=status.HTTP_204_NO_CONTENT)
def disable_portal_mfa(body: MfaDisable, session: AuthSession = Depends(current_portal_session), account: PortalAccount = Depends(portal_ready_account), db: Session = Depends(get_db)):
    if not password_hash.verify(body.password, account.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    registration = db.scalar(select(PortalMfaRegistration).where(PortalMfaRegistration.portal_account_id == account.id, PortalMfaRegistration.active.is_(True)))
    if not registration or not consume_portal_mfa_code(registration, body.code):
        raise HTTPException(status_code=401, detail="Invalid MFA code")
    db.delete(registration); current = now_utc()
    for other in db.scalars(select(AuthSession).where(AuthSession.portal_account_id == account.id, AuthSession.id != session.id, AuthSession.revoked_at.is_(None))):
        other.revoked_at = current; other.revoke_reason = "mfa-disabled"
    portal_audit(db, account, "mfa-disabled", "portal_account", account.uuid); db.commit()


@router.get("/portal/me")
def portal_me(account: PortalAccount = Depends(portal_ready_account), db: Session = Depends(get_db)):
    patient = db.get(Patient, account.patient_id) if account.patient_id else None
    return {"account_uuid": account.uuid, "username": account.username, "display_name": account.display_name, "email": account.email, "patient_uuid": patient.uuid if patient else None}


@router.get("/messages", response_model=list[MessageThreadOut])
def list_staff_threads(patient_uuid: str | None = None, thread_status: str | None = Query(default=None, pattern="^(open|closed)$"), db: Session = Depends(get_db), user: User = Depends(communication_user)):
    query = select(MessageThread, Patient).join(Patient, Patient.id == MessageThread.patient_id)
    if patient_uuid:
        query = query.where(Patient.uuid == patient_uuid)
    if thread_status:
        query = query.where(MessageThread.status == thread_status)
    rows = db.execute(query.order_by(MessageThread.updated_at.desc())).all()
    return [thread_out(db, thread, patient, include_messages=False) for thread, patient in rows]


@router.post("/patients/{patient_uuid}/messages", response_model=MessageThreadOut, status_code=status.HTTP_201_CREATED)
def create_staff_thread(body: MessageCreate, patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(communication_write_user)):
    patient = patient_by_uuid(db, patient_uuid)
    thread = MessageThread(patient_id=patient.id, subject=body.subject, assigned_user_id=user.id)
    db.add(thread)
    db.flush()
    message = SecureMessage(thread_id=thread.id, sender_kind="staff", sender_user_id=user.id, sender_name=user.email, body=body.body, read_by_staff_at=now_utc())
    db.add(message)
    db.flush()
    queue_patient_notice(db, patient, message)
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="message_thread", resource_id=thread.uuid))
    db.commit()
    db.refresh(thread)
    return thread_out(db, thread, patient)


@router.get("/messages/{thread_uuid}", response_model=MessageThreadOut)
def get_staff_thread(thread_uuid: str, db: Session = Depends(get_db), user: User = Depends(communication_user)):
    row = db.execute(select(MessageThread, Patient).join(Patient).where(MessageThread.uuid == thread_uuid)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Message thread not found")
    thread, patient = row
    db.execute(select(SecureMessage).where(SecureMessage.thread_id == thread.id))
    for message in db.scalars(select(SecureMessage).where(SecureMessage.thread_id == thread.id, SecureMessage.read_by_staff_at.is_(None))):
        message.read_by_staff_at = now_utc()
    db.commit()
    return thread_out(db, thread, patient)


@router.post("/messages/{thread_uuid}/replies", response_model=MessageThreadOut)
def staff_reply(body: MessageReply, thread_uuid: str, db: Session = Depends(get_db), user: User = Depends(communication_write_user)):
    row = db.execute(select(MessageThread, Patient).join(Patient).where(MessageThread.uuid == thread_uuid)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Message thread not found")
    thread, patient = row
    if thread.status != "open":
        raise HTTPException(status_code=409, detail="Message thread is closed")
    message = SecureMessage(thread_id=thread.id, sender_kind="staff", sender_user_id=user.id, sender_name=user.email, body=body.body, read_by_staff_at=now_utc())
    db.add(message)
    db.flush()
    thread.updated_at = now_utc()
    queue_patient_notice(db, patient, message)
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="secure_message", resource_id=message.uuid))
    db.commit()
    return thread_out(db, thread, patient)


@router.patch("/messages/{thread_uuid}/close", response_model=MessageThreadOut)
def close_thread(thread_uuid: str, db: Session = Depends(get_db), user: User = Depends(communication_write_user)):
    row = db.execute(select(MessageThread, Patient).join(Patient).where(MessageThread.uuid == thread_uuid)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Message thread not found")
    thread, patient = row
    thread.status = "closed"
    thread.updated_at = now_utc()
    db.add(AuditEvent(actor_id=user.id, action="update", resource_type="message_thread", resource_id=thread.uuid, detail="status=closed"))
    db.commit()
    return thread_out(db, thread, patient)


@router.get("/portal/messages", response_model=list[MessageThreadOut])
def list_portal_threads(context: PortalPatientContext = Depends(require_portal_scope("messages")), db: Session = Depends(get_db)):
    patient = context.patient
    threads = db.scalars(select(MessageThread).where(MessageThread.patient_id == patient.id).order_by(MessageThread.updated_at.desc())).all()
    portal_audit(db, context.account, "search", "message_thread", patient_id=patient.id); db.commit()
    return [thread_out(db, thread, patient, include_messages=False) for thread in threads]


@router.post("/portal/messages", response_model=MessageThreadOut, status_code=status.HTTP_201_CREATED)
def create_portal_thread(body: MessageCreate, context: PortalPatientContext = Depends(require_portal_scope("messages")), db: Session = Depends(get_db)):
    account = context.account; patient = context.patient
    thread = MessageThread(patient_id=patient.id, subject=body.subject)
    db.add(thread)
    db.flush()
    db.add(SecureMessage(thread_id=thread.id, sender_kind="patient", sender_portal_account_id=account.id, sender_name=account.display_name or account.username, body=body.body, read_by_patient_at=now_utc()))
    portal_audit(db, account, "create", "message_thread", thread.uuid, patient.id)
    db.commit()
    db.refresh(thread)
    return thread_out(db, thread, patient)


@router.get("/portal/messages/{thread_uuid}", response_model=MessageThreadOut)
def get_portal_thread(thread_uuid: str, context: PortalPatientContext = Depends(require_portal_scope("messages")), db: Session = Depends(get_db)):
    thread, patient = portal_thread(db, context, thread_uuid)
    for message in db.scalars(select(SecureMessage).where(SecureMessage.thread_id == thread.id, SecureMessage.read_by_patient_at.is_(None))):
        message.read_by_patient_at = now_utc()
    portal_audit(db, context.account, "read", "message_thread", thread.uuid, patient.id)
    db.commit()
    return thread_out(db, thread, patient)


@router.post("/portal/messages/{thread_uuid}/replies", response_model=MessageThreadOut)
def portal_reply(body: MessageReply, thread_uuid: str, context: PortalPatientContext = Depends(require_portal_scope("messages")), db: Session = Depends(get_db)):
    account = context.account; thread, patient = portal_thread(db, context, thread_uuid)
    if thread.status != "open":
        raise HTTPException(status_code=409, detail="Message thread is closed")
    message = SecureMessage(thread_id=thread.id, sender_kind="patient", sender_portal_account_id=account.id, sender_name=account.display_name or account.username, body=body.body, read_by_patient_at=now_utc())
    db.add(message)
    thread.updated_at = now_utc()
    db.flush(); portal_audit(db, account, "create", "secure_message", message.uuid, patient.id)
    db.commit()
    return thread_out(db, thread, patient)


@router.get("/tasks", response_model=list[ClinicalTaskOut])
def list_tasks(task_status: str | None = Query(default=None, pattern="^(open|completed|cancelled)$"), db: Session = Depends(get_db), user: User = Depends(communication_user)):
    query = select(ClinicalTask, Patient, Encounter, User).join(Patient, Patient.id == ClinicalTask.patient_id).outerjoin(Encounter, Encounter.id == ClinicalTask.encounter_id).outerjoin(User, User.id == ClinicalTask.assigned_to_id)
    if task_status:
        query = query.where(ClinicalTask.status == task_status)
    return [task_out(*row) for row in db.execute(query.order_by(ClinicalTask.due_at, ClinicalTask.id.desc())).all()]


@router.post("/tasks", response_model=ClinicalTaskOut, status_code=status.HTTP_201_CREATED)
def create_task(body: ClinicalTaskCreate, db: Session = Depends(get_db), user: User = Depends(communication_write_user)):
    patient = patient_by_uuid(db, body.patient_uuid)
    encounter = None
    if body.encounter_uuid:
        encounter = db.scalar(select(Encounter).where(Encounter.uuid == body.encounter_uuid, Encounter.patient_id == patient.id))
        if not encounter:
            raise HTTPException(status_code=404, detail="Encounter not found for patient")
    assigned = db.scalar(select(User).where(User.uuid == body.assigned_user_uuid)) if body.assigned_user_uuid else user
    if body.assigned_user_uuid and not assigned:
        raise HTTPException(status_code=404, detail="Assigned user not found")
    task = ClinicalTask(patient_id=patient.id, encounter_id=encounter.id if encounter else None, created_by_id=user.id, assigned_to_id=assigned.id, method=body.method, comment=body.comment, due_at=body.due_at)
    db.add(task)
    db.flush()
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="clinical_task", resource_id=task.uuid))
    db.commit()
    db.refresh(task)
    return task_out(task, patient, encounter, assigned)


@router.patch("/tasks/{task_uuid}/complete", response_model=ClinicalTaskOut)
def complete_task(task_uuid: str, db: Session = Depends(get_db), user: User = Depends(communication_write_user)):
    row = db.execute(select(ClinicalTask, Patient, Encounter, User).join(Patient, Patient.id == ClinicalTask.patient_id).outerjoin(Encounter, Encounter.id == ClinicalTask.encounter_id).outerjoin(User, User.id == ClinicalTask.assigned_to_id).where(ClinicalTask.uuid == task_uuid)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Clinical task not found")
    task, patient, encounter, assigned = row
    task.status = "completed"
    task.completed_at = now_utc()
    db.add(AuditEvent(actor_id=user.id, action="update", resource_type="clinical_task", resource_id=task.uuid, detail="status=completed"))
    db.commit()
    return task_out(task, patient, encounter, assigned)


@router.get("/communications/outbox", response_model=list[CommunicationDeliveryOut])
def list_outbox(delivery_status: str | None = Query(default=None, pattern="^(pending|sent|failed)$"), db: Session = Depends(get_db), user: User = Depends(administration_user)):
    query = select(CommunicationDelivery)
    if delivery_status:
        query = query.where(CommunicationDelivery.status == delivery_status)
    return list(db.scalars(query.order_by(CommunicationDelivery.queued_at.desc()).limit(500)))


@router.post("/communications/outbox/{delivery_uuid}/retry", response_model=CommunicationDeliveryOut)
def retry_delivery(delivery_uuid: str, db: Session = Depends(get_db), user: User = Depends(administration_user)):
    delivery = db.scalar(select(CommunicationDelivery).where(CommunicationDelivery.uuid == delivery_uuid))
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    if delivery.status == "sent":
        raise HTTPException(status_code=409, detail="Sent delivery cannot be retried")
    delivery.status = "pending"
    delivery.failed_at = None
    delivery.error_message = None
    delivery.queued_at = now_utc()
    db.add(AuditEvent(actor_id=user.id, action="update", resource_type="communication_delivery", resource_id=delivery.uuid, detail="status=pending"))
    db.commit()
    db.refresh(delivery)
    return delivery
