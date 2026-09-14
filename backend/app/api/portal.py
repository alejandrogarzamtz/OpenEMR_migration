from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import (
    Appointment,
    AuditEvent,
    Charge,
    Claim,
    ClaimPayment,
    ClinicalForm,
    Document,
    Encounter,
    IdentityAuditEvent,
    LabOrder,
    LabResult,
    Patient,
    PortalAccount,
    PaymentIntent,
    User,
)
from ..schemas import AppointmentOut, ChargeOut, ClaimOut, ClinicalFormOut, DocumentOut, LabResultOut, PaymentOut, PortalClinicalFormOut, PortalLabResultOut, PortalPaymentIntentCreate, PortalPaymentIntentOut, PortalStatementOut
from ..security import clinical_user, current_portal_account
from ..services.patients import patient_by_uuid
from ..services.payments import payment_processor
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


def portal_claim_out(db: Session, claim: Claim) -> ClaimOut:
    encounter = db.get(Encounter, claim.encounter_id)
    coverage_uuid = None
    if claim.coverage_id:
        from ..models import Coverage
        coverage = db.get(Coverage, claim.coverage_id)
        coverage_uuid = coverage.uuid if coverage else None
    charges = list(db.scalars(select(Charge).where(Charge.claim_id == claim.id).order_by(Charge.id)))
    payments = list(db.scalars(select(ClaimPayment).where(ClaimPayment.claim_id == claim.id).order_by(ClaimPayment.posted_at)))
    paid = sum((item.amount for item in payments), Decimal("0.00"))
    return ClaimOut(
        uuid=claim.uuid, encounter_uuid=encounter.uuid, coverage_uuid=coverage_uuid,
        status=claim.status, total=claim.total, paid=paid, balance=claim.total-paid,
        charges=[ChargeOut(uuid=item.uuid, encounter_uuid=encounter.uuid, code_system=item.code_system, code=item.code, description=item.description, units=item.units, unit_price=item.unit_price) for item in charges],
        payments=[PaymentOut.model_validate(item) for item in payments], created_at=claim.created_at,
        released_to_patient_at=claim.released_to_patient_at,
    )


def payment_intent_out(intent: PaymentIntent, claim_uuid: str) -> PortalPaymentIntentOut:
    return PortalPaymentIntentOut(claim_uuid=claim_uuid, **{key: getattr(intent, key) for key in PortalPaymentIntentOut.model_fields if key != "claim_uuid"})


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


@router.get("/portal/billing/statement", response_model=PortalStatementOut)
def portal_statement(account: PortalAccount = Depends(portal_account), db: Session = Depends(get_db)):
    feature(settings.portal_billing_enabled)
    claims = list(db.scalars(select(Claim).where(Claim.patient_id == account.patient_id, Claim.released_to_patient_at.is_not(None)).order_by(Claim.created_at.desc())))
    rows = [portal_claim_out(db, claim) for claim in claims]
    total = sum((row.total for row in rows), Decimal("0.00")); paid = sum((row.paid for row in rows), Decimal("0.00"))
    portal_audit(db, account, "read", "patient_statement")
    db.commit()
    return PortalStatementOut(currency=settings.billing_currency.upper(), payments_available=settings.payment_provider != "disabled" and (settings.payment_provider != "test" or settings.deployment_environment == "test"), total_charges=total, total_paid=paid, balance=total-paid, claims=rows)


@router.get("/portal/billing/payment-intents", response_model=list[PortalPaymentIntentOut])
def portal_payment_intents(account: PortalAccount = Depends(portal_account), db: Session = Depends(get_db)):
    feature(settings.portal_billing_enabled)
    rows = db.execute(select(PaymentIntent, Claim.uuid).join(Claim).where(PaymentIntent.portal_account_id == account.id, PaymentIntent.patient_id == account.patient_id).order_by(PaymentIntent.created_at.desc())).all()
    portal_audit(db, account, "search", "payment_intent")
    db.commit()
    return [payment_intent_out(intent, claim_uuid) for intent, claim_uuid in rows]


@router.post("/portal/billing/payment-intents", response_model=PortalPaymentIntentOut, status_code=status.HTTP_201_CREATED)
def create_portal_payment_intent(body: PortalPaymentIntentCreate, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=100), account: PortalAccount = Depends(portal_account), db: Session = Depends(get_db)):
    feature(settings.portal_billing_enabled)
    currency = settings.billing_currency.upper()
    fingerprint = sha256(f"{body.claim_uuid}|{body.amount:.2f}|{currency}".encode()).hexdigest()
    existing = db.scalar(select(PaymentIntent).where(PaymentIntent.portal_account_id == account.id, PaymentIntent.idempotency_key == idempotency_key))
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key was already used for a different payment")
        claim = db.get(Claim, existing.claim_id)
        return payment_intent_out(existing, claim.uuid)
    claim = db.scalar(select(Claim).where(Claim.uuid == body.claim_uuid, Claim.patient_id == account.patient_id, Claim.released_to_patient_at.is_not(None)).with_for_update())
    if not claim:
        raise HTTPException(status_code=404, detail="Released claim not found")
    paid = Decimal(db.scalar(select(func.coalesce(func.sum(ClaimPayment.amount), 0)).where(ClaimPayment.claim_id == claim.id)))
    reserved = Decimal(db.scalar(select(func.coalesce(func.sum(PaymentIntent.amount), 0)).where(PaymentIntent.claim_id == claim.id, PaymentIntent.status == "processing")))
    if body.amount > claim.total - paid - reserved:
        raise HTTPException(status_code=422, detail="Payment exceeds the available claim balance")
    intent = PaymentIntent(patient_id=account.patient_id, portal_account_id=account.id, claim_id=claim.id, idempotency_key=idempotency_key, request_fingerprint=fingerprint, amount=body.amount, currency=currency, provider=settings.payment_provider, status="processing")
    db.add(intent); db.flush(); portal_audit(db, account, "create", "payment_intent", intent.uuid); db.commit(); db.refresh(intent)

    result = payment_processor(settings.payment_provider, settings.deployment_environment).charge(amount=body.amount, currency=currency, token=body.payment_method_token, idempotency_key=intent.uuid)
    intent = db.scalar(select(PaymentIntent).where(PaymentIntent.id == intent.id).with_for_update())
    claim = db.scalar(select(Claim).where(Claim.id == intent.claim_id).with_for_update())
    if result.succeeded and intent.status == "processing":
        payment = ClaimPayment(claim_id=claim.id, amount=intent.amount, method="portal-card", reference=result.reference)
        db.add(payment); db.flush(); intent.claim_payment_id = payment.id; intent.status = "succeeded"; intent.processor_reference = result.reference
        paid = Decimal(db.scalar(select(func.coalesce(func.sum(ClaimPayment.amount), 0)).where(ClaimPayment.claim_id == claim.id)))
        if paid == claim.total: claim.status = "paid"
    elif intent.status == "processing":
        intent.status = "failed"; intent.failure_code = result.failure_code
    intent.completed_at = datetime.now(timezone.utc)
    portal_audit(db, account, intent.status, "payment_intent", intent.uuid); db.commit(); db.refresh(intent)
    return payment_intent_out(intent, claim.uuid)


def release_target(db: Session, patient_uuid: str, resource_type: str, resource_uuid: str):
    patient = patient_by_uuid(db, patient_uuid)
    model = {"document": Document, "clinical_form": ClinicalForm}[resource_type]
    item = db.scalar(select(model).where(model.uuid == resource_uuid, model.patient_id == patient.id))
    if not item:
        raise HTTPException(status_code=404, detail=f"{resource_type.replace('_', ' ').title()} not found")
    return patient, item


@router.post("/patients/{patient_uuid}/claims/{claim_uuid}/release", response_model=ClaimOut)
def release_claim(patient_uuid: str, claim_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    claim = db.scalar(select(Claim).where(Claim.uuid == claim_uuid, Claim.patient_id == patient.id))
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.total <= 0:
        raise HTTPException(status_code=409, detail="Only claims with a positive balance can be released")
    claim.released_to_patient_at = datetime.now(timezone.utc); claim.released_by_id = user.id
    staff_audit(db, user, patient.id, "release", "claim", claim.uuid); db.commit(); db.refresh(claim)
    return portal_claim_out(db, claim)


@router.delete("/patients/{patient_uuid}/claims/{claim_uuid}/release", status_code=status.HTTP_204_NO_CONTENT)
def revoke_claim(patient_uuid: str, claim_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    claim = db.scalar(select(Claim).where(Claim.uuid == claim_uuid, Claim.patient_id == patient.id))
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if db.scalar(select(PaymentIntent.id).where(PaymentIntent.claim_id == claim.id, PaymentIntent.status == "processing").limit(1)):
        raise HTTPException(status_code=409, detail="Claim has a payment in progress")
    claim.released_to_patient_at = None; claim.released_by_id = None
    staff_audit(db, user, patient.id, "revoke", "claim", claim.uuid); db.commit()


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
