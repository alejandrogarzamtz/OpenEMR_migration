from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets
from uuid import uuid4
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import AuthSession, Patient, PortalAccount, User

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


def current_user(request:Request,session: AuthSession = Depends(current_staff_session), db: Session = Depends(get_db)) -> User:
    if session.smart_client_id is not None and not request.url.path.startswith("/fhir/"):
        raise HTTPException(status_code=403,detail="SMART Backend Services tokens are restricted to FHIR")
    user = db.get(User, session.user_id) if session.user_id else None
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="Invalid or expired credentials")
    return user


def create_portal_token(account: PortalAccount, session: AuthSession) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(account.id),
        "kind": "portal",
        "jti": session.access_jti,
        "sid": session.uuid,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    if account.patient_id is not None:
        claims["patient"] = str(account.patient_id)
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")


def current_portal_session(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> AuthSession:
    session, _ = authenticated_session(credentials, db, "portal")
    return session


def current_portal_account(session: AuthSession = Depends(current_portal_session), db: Session = Depends(get_db)) -> PortalAccount:
    account = db.get(PortalAccount, session.portal_account_id) if session.portal_account_id else None
    if not account or not account.active:
        raise HTTPException(status_code=401, detail="Invalid or expired portal credentials")
    if account.patient_id is not None:
        patient = db.get(Patient, account.patient_id)
        if not patient or not patient.portal_allowed:
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
    def permission_dependency(request:Request,session:AuthSession=Depends(current_staff_session),user: User = Depends(current_user),db:Session=Depends(get_db)) -> User:
        if not user_has_permission(user, section, value, mode):
            raise HTTPException(status_code=403, detail="Permission denied")
        if session.smart_client_id is not None:
            parts=request.url.path.strip("/").split("/")
            if len(parts)<2 or parts[0]!="fhir":raise HTTPException(status_code=403,detail="SMART Backend Services tokens are restricted to FHIR")
            resource=parts[1]
            if request.method=="POST" and not (len(parts)>2 and parts[2].startswith("$")):operation="c"
            elif request.method in {"PUT","PATCH"}:operation="u"
            elif request.method=="DELETE":operation="d"
            elif len(parts)==2 or (len(parts)>2 and parts[2].startswith("$")):operation="s"
            else:operation="r"
            grants=session.smart_scopes or []
            def covers(scope:str):
                if "/" not in scope or "." not in scope:return False
                context,tail=scope.split("/",1);target,actions=tail.rsplit(".",1)
                return context in {"system","user","patient"} and target in {"*",resource} and operation in actions
            if not any(covers(scope) for scope in grants):raise HTTPException(status_code=403,detail={"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"forbidden","diagnostics":f"Missing SMART {resource}.{operation} scope"}]})
            patient_scoped=any(scope.startswith("patient/") and covers(scope) for scope in grants) and not any(scope.startswith(("system/","user/")) and covers(scope) for scope in grants)
            if patient_scoped and not smart_patient_access(db,request,session,resource,parts[2] if len(parts)>2 else None):raise HTTPException(status_code=403,detail={"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"forbidden","diagnostics":"Resource is outside the authorized patient context"}]})
        return user

    return permission_dependency


def smart_patient_access(db:Session,request:Request,session:AuthSession,resource:str,resource_id:str|None)->bool:
    patient_id=session.smart_patient_id
    if not patient_id:return False
    patient=db.get(Patient,patient_id)
    if not patient:return False
    if resource_id is None:
        reference=request.query_params.get("_id") if resource=="Patient" else request.query_params.get("patient")
        return bool(reference and reference.rstrip("/").rsplit("/",1)[-1]==patient.uuid)
    if resource=="Patient":
        reference=request.query_params.get("patient") if resource_id.startswith("$") else resource_id
        return bool(reference and reference.rstrip("/").rsplit("/",1)[-1]==patient.uuid)
    from .models import Appointment, CarePlan, CareTeam, ClinicalItem, Coverage, Document, Encounter, ExternalProcedure, Immunization, InventoryTransaction, LabOrder, LabResult, PatientRelatedPerson, Prescription, QuestionnaireResponse, VitalSet
    direct={"Condition":ClinicalItem,"AllergyIntolerance":ClinicalItem,"MedicationStatement":ClinicalItem,"Immunization":Immunization,"MedicationRequest":Prescription,"MedicationDispense":InventoryTransaction,"CarePlan":CarePlan,"Goal":CarePlan,"CareTeam":CareTeam,"Appointment":Appointment,"Encounter":Encounter,"Coverage":Coverage,"DocumentReference":Document,"Binary":Document,"Media":Document,"ServiceRequest":LabOrder,"DiagnosticReport":LabOrder,"Specimen":LabOrder,"Procedure":ExternalProcedure,"QuestionnaireResponse":QuestionnaireResponse,"RelatedPerson":PatientRelatedPerson}
    model=direct.get(resource)
    if model:return bool(db.scalar(select(model.id).where(model.uuid==resource_id,model.patient_id==patient_id)))
    if resource=="Observation":
        result=db.scalar(select(LabResult.id).join(LabOrder,LabResult.order_id==LabOrder.id).where(LabResult.uuid==resource_id,LabOrder.patient_id==patient_id))
        if result:return True
        for field in ("systolic","diastolic","heart_rate","respiratory_rate","temperature_c","oxygen_saturation","weight_kg","height_cm","bmi"):
            suffix=f"-{field}"
            if resource_id.endswith(suffix):return bool(db.scalar(select(VitalSet.id).where(VitalSet.uuid==resource_id[:-len(suffix)],VitalSet.patient_id==patient_id)))
    return False


# Legacy phpGACL-compatible section/value names. Route modules use these
# dependencies so authorization cannot be accidentally delegated to the UI.
patient_demographics_user = require_permission("patients", "demo")
patient_demographics_write_user = require_permission("patients", "demo", "write")
patient_report_user = require_permission("patients", "pat_rep")
clinical_user = require_permission("patients", "med")
clinical_write_user = require_permission("patients", "med", "write")
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
