from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import (
    Appointment,
    AuditEvent,
    ClinicalForm,
    Document,
    Encounter,
    IdentityAuditEvent,
    LabOrder,
    LabResult,
    Patient,
    PortalAccount,
    User,
)
from ..schemas import AppointmentOut, ClinicalFormOut, DocumentOut, LabResultOut, PortalClinicalFormOut, PortalLabResultOut
from ..security import clinical_user, current_portal_account
from ..services.patients import patient_by_uuid
from .appointments import appointment_out

router = APIRouter(prefix="/api/v1", tags=["patient portal"])


def portal_account(account: PortalAccount = Depends(current_portal_account)) -> PortalAccount:
    if account.force_password_reset:
        raise HTTPException(status_code=403, detail="Password reset required")
    return account


def feature(enabled: bool) -> None:
    if not enabled:
        raise HTTPException(status_code=404, detail="Portal feature is not enabled")


def portal_audit(db: Session, account: PortalAccount, action: str, resource_type: str, resource_id: str | None = None) -> None:
    db.add(IdentityAuditEvent(identity_kind="portal", portal_account_id=account.id, patient_id=account.patient_id, action=action, resource_type=resource_type, resource_id=resource_id))


def staff_audit(db: Session, user: User, patient_id: int, action: str, resource_type: str, resource_id: str) -> None:
    db.add(IdentityAuditEvent(identity_kind="staff", user_id=user.id, patient_id=patient_id, action=action, resource_type=resource_type, resource_id=resource_id))
    db.add(AuditEvent(actor_id=user.id, action=action, resource_type=resource_type, resource_id=resource_id))


@router.get("/portal/appointments", response_model=list[AppointmentOut])
def portal_appointments(account: PortalAccount = Depends(portal_account), db: Session = Depends(get_db)):
    feature(settings.portal_appointments_enabled)
    patient = db.get(Patient, account.patient_id)
    items = list(db.scalars(select(Appointment).where(Appointment.patient_id == account.patient_id).order_by(Appointment.starts_at)))
    portal_audit(db, account, "search", "appointment")
    db.commit()
    return [appointment_out(db, item, patient.uuid) for item in items]


@router.get("/portal/results", response_model=list[PortalLabResultOut])
def portal_results(account: PortalAccount = Depends(portal_account), db: Session = Depends(get_db)):
    feature(settings.portal_results_enabled)
    rows = db.execute(
        select(LabResult, LabOrder).join(LabOrder).where(
            LabOrder.patient_id == account.patient_id,
            LabResult.released_to_patient_at.is_not(None),
            LabResult.status.in_(("final", "corrected")),
        ).order_by(LabResult.observed_at.desc())
    ).all()
    portal_audit(db, account, "search", "lab_result")
    db.commit()
    return [PortalLabResultOut(order_uuid=order.uuid, order_name=order.name, **{key: getattr(result, key) for key in PortalLabResultOut.model_fields if key not in {"order_uuid", "order_name"}}) for result, order in rows]


@router.get("/portal/documents", response_model=list[DocumentOut])
def portal_documents(account: PortalAccount = Depends(portal_account), db: Session = Depends(get_db)):
    feature(settings.portal_documents_enabled)
    items = list(db.scalars(select(Document).where(Document.patient_id == account.patient_id, Document.released_to_patient_at.is_not(None)).order_by(Document.uploaded_at.desc())))
    portal_audit(db, account, "search", "document")
    db.commit()
    return items


@router.get("/portal/documents/{document_uuid}/content")
def portal_document_content(document_uuid: str, account: PortalAccount = Depends(portal_account), db: Session = Depends(get_db)):
    feature(settings.portal_documents_enabled)
    document = db.scalar(select(Document).where(Document.uuid == document_uuid, Document.patient_id == account.patient_id, Document.released_to_patient_at.is_not(None)))
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    portal_audit(db, account, "read", "document", document.uuid)
    db.commit()
    safe_name = document.name.replace('"', "")
    return Response(document.content, media_type=document.mime_type, headers={"Content-Disposition": f'attachment; filename="{safe_name}"', "ETag": document.sha256})


@router.get("/portal/forms", response_model=list[PortalClinicalFormOut])
def portal_forms(account: PortalAccount = Depends(portal_account), db: Session = Depends(get_db)):
    feature(settings.portal_forms_enabled)
    rows = db.execute(select(ClinicalForm, Encounter.uuid).join(Encounter).where(ClinicalForm.patient_id == account.patient_id, ClinicalForm.status == "signed", ClinicalForm.released_to_patient_at.is_not(None)).order_by(ClinicalForm.authored_at.desc())).all()
    portal_audit(db, account, "search", "clinical_form")
    db.commit()
    return [PortalClinicalFormOut(encounter_uuid=encounter_uuid, **{key: getattr(item, key) for key in PortalClinicalFormOut.model_fields if key != "encounter_uuid"}) for item, encounter_uuid in rows]


def release_target(db: Session, patient_uuid: str, resource_type: str, resource_uuid: str):
    patient = patient_by_uuid(db, patient_uuid)
    model = {"document": Document, "clinical_form": ClinicalForm}[resource_type]
    item = db.scalar(select(model).where(model.uuid == resource_uuid, model.patient_id == patient.id))
    if not item:
        raise HTTPException(status_code=404, detail=f"{resource_type.replace('_', ' ').title()} not found")
    return patient, item


@router.post("/patients/{patient_uuid}/documents/{document_uuid}/release", response_model=DocumentOut)
def release_document(patient_uuid: str, document_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient, item = release_target(db, patient_uuid, "document", document_uuid)
    item.released_to_patient_at = datetime.now(timezone.utc); item.released_by_id = user.id
    staff_audit(db, user, patient.id, "release", "document", item.uuid); db.commit(); db.refresh(item)
    return item


@router.delete("/patients/{patient_uuid}/documents/{document_uuid}/release", status_code=status.HTTP_204_NO_CONTENT)
def revoke_document(patient_uuid: str, document_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient, item = release_target(db, patient_uuid, "document", document_uuid)
    item.released_to_patient_at = None; item.released_by_id = None
    staff_audit(db, user, patient.id, "revoke", "document", item.uuid); db.commit()


@router.post("/patients/{patient_uuid}/clinical-forms/{form_uuid}/release", response_model=ClinicalFormOut)
def release_form(patient_uuid: str, form_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient, item = release_target(db, patient_uuid, "clinical_form", form_uuid)
    if item.status != "signed" or item.signed_at is None:
        raise HTTPException(status_code=409, detail="Only signed clinical forms can be released")
    item.released_to_patient_at = datetime.now(timezone.utc); item.released_by_id = user.id
    encounter = db.get(Encounter, item.encounter_id)
    staff_audit(db, user, patient.id, "release", "clinical_form", item.uuid); db.commit(); db.refresh(item)
    return ClinicalFormOut(encounter_uuid=encounter.uuid, **{key: getattr(item, key) for key in ClinicalFormOut.model_fields if key != "encounter_uuid"})


@router.delete("/patients/{patient_uuid}/clinical-forms/{form_uuid}/release", status_code=status.HTTP_204_NO_CONTENT)
def revoke_form(patient_uuid: str, form_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient, item = release_target(db, patient_uuid, "clinical_form", form_uuid)
    item.released_to_patient_at = None; item.released_by_id = None
    staff_audit(db, user, patient.id, "revoke", "clinical_form", item.uuid); db.commit()


@router.post("/lab-results/{result_uuid}/release", response_model=LabResultOut)
def release_result(result_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    row = db.execute(select(LabResult, LabOrder).join(LabOrder).where(LabResult.uuid == result_uuid)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Lab result not found")
    item, order = row
    if item.status not in {"final", "corrected"}:
        raise HTTPException(status_code=409, detail="Only final or corrected lab results can be released")
    item.released_to_patient_at = datetime.now(timezone.utc); item.released_by_id = user.id
    staff_audit(db, user, order.patient_id, "release", "lab_result", item.uuid); db.commit(); db.refresh(item)
    return item


@router.post("/lab-orders/{order_uuid}/release-results", response_model=list[LabResultOut])
def release_order_results(order_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    order = db.scalar(select(LabOrder).where(LabOrder.uuid == order_uuid))
    if not order:
        raise HTTPException(status_code=404, detail="Lab order not found")
    items = list(db.scalars(select(LabResult).where(LabResult.order_id == order.id, LabResult.status.in_(("final", "corrected")))))
    if not items:
        raise HTTPException(status_code=409, detail="The order has no final or corrected results to release")
    released_at = datetime.now(timezone.utc)
    for item in items:
        item.released_to_patient_at = released_at
        item.released_by_id = user.id
        staff_audit(db, user, order.patient_id, "release", "lab_result", item.uuid)
    db.commit()
    return items


@router.delete("/lab-results/{result_uuid}/release", status_code=status.HTTP_204_NO_CONTENT)
def revoke_result(result_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    row = db.execute(select(LabResult, LabOrder).join(LabOrder).where(LabResult.uuid == result_uuid)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Lab result not found")
    item, order = row
    item.released_to_patient_at = None; item.released_by_id = None
    staff_audit(db, user, order.patient_id, "revoke", "lab_result", item.uuid); db.commit()
