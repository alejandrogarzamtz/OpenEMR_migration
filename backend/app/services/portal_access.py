from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Patient, PortalAccessGrant, PortalAccount
from ..security import current_portal_account

PORTAL_SCOPES = frozenset({"appointments", "records", "documents", "forms", "messages", "billing", "questionnaires", "notifications"})


@dataclass(frozen=True)
class PortalPatientContext:
    account: PortalAccount
    patient: Patient
    scopes: frozenset[str]
    grant: PortalAccessGrant | None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def active_grants(db: Session, account: PortalAccount) -> list[tuple[PortalAccessGrant, Patient]]:
    now = utc_now()
    rows = db.execute(select(PortalAccessGrant, Patient).join(Patient, Patient.id == PortalAccessGrant.patient_id).where(PortalAccessGrant.grantee_portal_account_id == account.id, PortalAccessGrant.revoked_at.is_(None), PortalAccessGrant.starts_at <= now, (PortalAccessGrant.expires_at.is_(None) | (PortalAccessGrant.expires_at > now))).order_by(Patient.last_name, Patient.first_name)).all()
    return [(grant, patient) for grant, patient in rows]


def resolve_portal_context(db: Session, account: PortalAccount, patient_uuid: str | None) -> PortalPatientContext:
    if patient_uuid is None:
        if account.patient_id is None:
            raise HTTPException(status_code=400, detail="X-Portal-Patient is required for representative accounts")
        patient = db.get(Patient, account.patient_id)
        if patient is None:
            raise HTTPException(status_code=401, detail="Portal identity is not linked to a patient")
        return PortalPatientContext(account, patient, PORTAL_SCOPES, None)
    patient = db.scalar(select(Patient).where(Patient.uuid == patient_uuid))
    if not patient:
        raise HTTPException(status_code=404, detail="Patient context not found")
    if account.patient_id == patient.id:
        return PortalPatientContext(account, patient, PORTAL_SCOPES, None)
    now = utc_now()
    grant = db.scalar(select(PortalAccessGrant).where(PortalAccessGrant.grantee_portal_account_id == account.id, PortalAccessGrant.patient_id == patient.id, PortalAccessGrant.revoked_at.is_(None), PortalAccessGrant.starts_at <= now, (PortalAccessGrant.expires_at.is_(None) | (PortalAccessGrant.expires_at > now))).order_by(PortalAccessGrant.created_at.desc()))
    if not grant:
        raise HTTPException(status_code=404, detail="Patient context not found")
    return PortalPatientContext(account, patient, frozenset(grant.scopes), grant)


def require_portal_scope(scope: str) -> Callable[..., PortalPatientContext]:
    if scope not in PORTAL_SCOPES:
        raise ValueError(f"Unknown portal scope: {scope}")

    def dependency(patient_uuid: str | None = Header(default=None, alias="X-Portal-Patient"), account: PortalAccount = Depends(current_portal_account), db: Session = Depends(get_db)) -> PortalPatientContext:
        if account.force_password_reset:
            raise HTTPException(status_code=403, detail="Password reset required")
        context = resolve_portal_context(db, account, patient_uuid)
        if context.grant is not None and scope not in context.scopes:
            raise HTTPException(status_code=403, detail="Representative grant does not include this scope")
        return context

    return dependency
