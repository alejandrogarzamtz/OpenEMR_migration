from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .models import Appointment, AuditEvent, Charge, Claim, ClaimPayment, ClinicalForm, ClinicalItem, Coverage, Document, Encounter, Immunization, LabOrder, LabResult, Patient, Payer, Pharmacy, Prescription, ProcedureOrderLine, ProcedureReport, QuestionnaireDefinition, QuestionnaireResponse, User, VitalSet
from .schemas import AppointmentOut, ChargeCreate, ChargeOut, ClaimCreate, ClaimOut, ClinicalFormCreate, ClinicalFormOut, ClinicalFormUpdate, ClinicalItemCreate, ClinicalItemOut, ClinicalSignatureCreate, ClinicalSignatureOut, ClinicalSummary, CoverageCreate, CoverageOut, DocumentOut, EncounterCreate, EncounterOut, ImmunizationCreate, ImmunizationOut, LabOrderCreate, LabOrderDetail, LabOrderOut, LabResultCreate, LabResultOut, PaymentCreate, PrescriptionCreate, PrescriptionOut, ProcedureReportOut, QuestionnaireDefinitionOut, QuestionnaireResponseCreate, QuestionnaireResponseOut, VitalSetCreate, VitalSetOut
from .security import (
    clinical_user,
)
from .fhir import router as fhir_router
from .api.auth import router as auth_router
from .api.appointments import router as appointments_router
from .api.patients import router as patients_router
from .api.patient_flow import router as patient_flow_router
from .api.inventory import router as inventory_router
from .api.administration import router as administration_router
from .api.reports import router as reports_router
from .api.communications import router as communications_router
from .api.portal import router as portal_router
from .api.chart_reports import router as chart_reports_router
from .api.care_plans import router as care_plans_router
from .api.clinical_form_links import router as clinical_form_links_router
from .api.care_teams import router as care_teams_router
from .api.patient_preferences import router as patient_preferences_router
from .api.patient_education import router as patient_education_router
from .api.social_history import router as social_history_router
from .api.patient_providers import router as patient_providers_router
from .bootstrap import lifespan
from .services.patients import patient_by_uuid
from .services.clinical_signatures import create_encounter_signature, create_signature, encounter_locked, encounter_signatures, form_locked, form_signatures, verify_encounter_signature_chain, verify_signature_chain
from .services.clinical_forms import ClinicalFormValidationError, FORM_DEFINITIONS, validate_clinical_form_content
from .security import password_hash


app = FastAPI(title="OpenEMR Next API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_router)
app.include_router(appointments_router)
app.include_router(patients_router)
app.include_router(patient_flow_router)
app.include_router(inventory_router)
app.include_router(administration_router)
app.include_router(reports_router)
app.include_router(communications_router)
app.include_router(portal_router)
app.include_router(chart_reports_router)
app.include_router(care_plans_router)
app.include_router(clinical_form_links_router)
app.include_router(care_teams_router)
app.include_router(patient_preferences_router)
app.include_router(patient_education_router)
app.include_router(social_history_router)
app.include_router(patient_providers_router)
app.include_router(fhir_router)


@app.get("/health")
def health():
    return {"status": "ok"}


def encounter_out(item: Encounter, patient_uuid: str, appointment_uuid: str | None, db: Session) -> EncounterOut:
    signatures=encounter_signatures(db,item.id)
    return EncounterOut(patient_uuid=patient_uuid,appointment_uuid=appointment_uuid,locked=any(signature.is_lock for signature in signatures),signature_count=len(signatures),**{k:getattr(item,k) for k in ("uuid","occurred_at","type","status","chief_complaint","clinical_note")})


@app.post("/api/v1/encounters", response_model=EncounterOut, status_code=201)
def create_encounter(body: EncounterCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, body.patient_uuid)
    appointment = None
    if body.appointment_uuid:
        appointment = db.scalar(select(Appointment).where(Appointment.uuid == body.appointment_uuid, Appointment.patient_id == patient.id))
        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found for patient")
        appointment.status = "arrived"
    item = Encounter(patient_id=patient.id, appointment_id=appointment.id if appointment else None, facility_id=appointment.facility_id if appointment else None, legacy_facility_id=appointment.legacy_facility_id if appointment else None, facility_name=appointment.facility_name if appointment else None, legacy_provider_id=appointment.legacy_provider_id if appointment else None, provider_name=appointment.provider_name if appointment else None, **body.model_dump(exclude={"patient_uuid", "appointment_uuid"}))
    db.add(item); db.flush(); db.add(AuditEvent(actor_id=user.id, action="create", resource_type="encounter", resource_id=item.uuid)); db.commit(); db.refresh(item)
    return encounter_out(item,patient.uuid,appointment.uuid if appointment else None,db)


@app.get("/api/v1/patients/{patient_uuid}/encounters", response_model=list[EncounterOut])
def list_encounters(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    rows = db.execute(select(Encounter, Appointment.uuid).outerjoin(Appointment).where(Encounter.patient_id == patient.id).order_by(Encounter.occurred_at.desc())).all()
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="encounter", resource_id=patient.uuid)); db.commit()
    return [encounter_out(item,patient.uuid,a_uuid,db) for item,a_uuid in rows]


@app.post("/api/v1/patients/{patient_uuid}/clinical-items", response_model=ClinicalItemOut, status_code=201)
def create_clinical_item(patient_uuid: str, body: ClinicalItemCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    item = ClinicalItem(patient_id=patient.id, **body.model_dump())
    db.add(item)
    db.flush()
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type=body.category, resource_id=item.uuid))
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/v1/patients/{patient_uuid}/clinical-items", response_model=list[ClinicalItemOut])
def list_clinical_items(patient_uuid: str, category: str | None = Query(default=None, pattern="^(problem|allergy|medication)$"), db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    query = select(ClinicalItem).where(ClinicalItem.patient_id == patient.id)
    if category:
        query = query.where(ClinicalItem.category == category)
    items = db.scalars(query.order_by(ClinicalItem.created_at.desc())).all()
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type=category or "clinical_item", resource_id=patient.uuid))
    db.commit()
    return list(items)


@app.patch("/api/v1/patients/{patient_uuid}/clinical-items/{item_uuid}/status", response_model=ClinicalItemOut)
def update_clinical_item_status(patient_uuid: str, item_uuid: str, status_value: str = Query(pattern="^(active|inactive|resolved|entered-in-error)$"), db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    item = db.scalar(select(ClinicalItem).where(ClinicalItem.uuid == item_uuid, ClinicalItem.patient_id == patient.id))
    if not item:
        raise HTTPException(status_code=404, detail="Clinical item not found")
    item.status = status_value
    db.add(AuditEvent(actor_id=user.id, action="update", resource_type=item.category, resource_id=item.uuid, detail=f"status={status_value}"))
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/v1/patients/{patient_uuid}/summary", response_model=ClinicalSummary)
def clinical_summary(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    items = db.scalars(select(ClinicalItem).where(ClinicalItem.patient_id == patient.id, ClinicalItem.status == "active").order_by(ClinicalItem.created_at.desc())).all()
    encounter_rows = db.execute(select(Encounter, Appointment.uuid).outerjoin(Appointment).where(Encounter.patient_id == patient.id).order_by(Encounter.occurred_at.desc()).limit(10)).all()
    encounters = [encounter_out(item,patient.uuid,a_uuid,db) for item,a_uuid in encounter_rows]
    db.add(AuditEvent(actor_id=user.id, action="read", resource_type="clinical_summary", resource_id=patient.uuid))
    db.commit()
    return ClinicalSummary(patient=patient, problems=[x for x in items if x.category == "problem"], allergies=[x for x in items if x.category == "allergy"], medications=[x for x in items if x.category == "medication"], encounters=encounters)


def encounter_for_patient(db: Session, patient: Patient, encounter_uuid: str | None) -> Encounter | None:
    if not encounter_uuid:
        return None
    encounter = db.scalar(select(Encounter).where(Encounter.uuid == encounter_uuid, Encounter.patient_id == patient.id))
    if not encounter:
        raise HTTPException(status_code=404, detail="Encounter not found for patient")
    return encounter


def order_out(order: LabOrder, encounter_uuid: str | None = None) -> LabOrderOut:
    fields=("uuid","ordered_at","code","name","priority","instructions","status","collected_at","transmitted_at","control_id","activity","specimen_type","specimen_location","specimen_volume","clinical_history","external_id","order_diagnosis","procedure_order_type")
    return LabOrderOut(encounter_uuid=encounter_uuid, **{key: getattr(order, key) for key in fields})


@app.post("/api/v1/patients/{patient_uuid}/lab-orders", response_model=LabOrderOut, status_code=201)
def create_lab_order(patient_uuid: str, body: LabOrderCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    encounter = encounter_for_patient(db, patient, body.encounter_uuid)
    order = LabOrder(patient_id=patient.id, encounter_id=encounter.id if encounter else None, **body.model_dump(exclude={"encounter_uuid"}))
    db.add(order); db.flush()
    db.add(ProcedureOrderLine(order_id=order.id,sequence=1,code=order.code,name=order.name,source="1"))
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="lab_order", resource_id=order.uuid)); db.commit(); db.refresh(order)
    return order_out(order, encounter.uuid if encounter else None)


@app.get("/api/v1/patients/{patient_uuid}/lab-orders", response_model=list[LabOrderOut])
def list_lab_orders(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    rows = db.execute(select(LabOrder, Encounter.uuid).outerjoin(Encounter).where(LabOrder.patient_id == patient.id).order_by(LabOrder.ordered_at.desc())).all()
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="lab_order", resource_id=patient.uuid)); db.commit()
    return [order_out(order, encounter_uuid) for order, encounter_uuid in rows]


@app.post("/api/v1/lab-orders/{order_uuid}/results", response_model=LabResultOut, status_code=201)
def create_lab_result(order_uuid: str, body: LabResultCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    order = db.scalar(select(LabOrder).where(LabOrder.uuid == order_uuid))
    if not order:
        raise HTTPException(status_code=404, detail="Lab order not found")
    result = LabResult(order_id=order.id, **body.model_dump())
    order.status = "complete" if body.status in {"final", "corrected"} else "in-progress"
    db.add(result); db.flush(); db.add(AuditEvent(actor_id=user.id, action="create", resource_type="lab_result", resource_id=result.uuid)); db.commit(); db.refresh(result)
    return result


@app.get("/api/v1/lab-orders/{order_uuid}", response_model=LabOrderDetail)
def get_lab_order(order_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    row = db.execute(select(LabOrder, Encounter.uuid).outerjoin(Encounter).where(LabOrder.uuid == order_uuid)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Lab order not found")
    order, encounter_uuid = row
    lines=list(db.scalars(select(ProcedureOrderLine).where(ProcedureOrderLine.order_id==order.id).order_by(ProcedureOrderLine.sequence)))
    reports=list(db.scalars(select(ProcedureReport).where(ProcedureReport.order_id==order.id).order_by(ProcedureReport.reported_at,ProcedureReport.id)))
    result_rows=db.execute(select(LabResult,ProcedureReport).outerjoin(ProcedureReport,LabResult.report_id==ProcedureReport.id).where(LabResult.order_id==order.id).order_by(LabResult.observed_at,LabResult.id)).all()
    results=[LabResultOut.model_validate(result).model_copy(update={"report":ProcedureReportOut.model_validate(report) if report else None}) for result,report in result_rows]
    db.add(AuditEvent(actor_id=user.id, action="read", resource_type="lab_order", resource_id=order.uuid)); db.commit()
    return LabOrderDetail(**order_out(order, encounter_uuid).model_dump(),lines=lines,reports=reports,results=results)


@app.post("/api/v1/patients/{patient_uuid}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(patient_uuid: str, encounter_uuid: str | None = None, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    encounter = encounter_for_patient(db, patient, encounter_uuid)
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Document exceeds 10 MiB limit")
    if not content:
        raise HTTPException(status_code=422, detail="Document is empty")
    document = Document(patient_id=patient.id, encounter_id=encounter.id if encounter else None, name=file.filename or "document", mime_type=file.content_type or "application/octet-stream", content=content, sha256=sha256(content).hexdigest())
    db.add(document); db.flush(); db.add(AuditEvent(actor_id=user.id, action="create", resource_type="document", resource_id=document.uuid)); db.commit(); db.refresh(document)
    return document


@app.get("/api/v1/patients/{patient_uuid}/documents", response_model=list[DocumentOut])
def list_documents(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    documents = list(db.scalars(select(Document).where(Document.patient_id == patient.id).order_by(Document.uploaded_at.desc())))
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="document", resource_id=patient.uuid)); db.commit()
    return documents


@app.get("/api/v1/patients/{patient_uuid}/documents/{document_uuid}/content")
def download_document(patient_uuid: str, document_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    document = db.scalar(select(Document).where(Document.uuid == document_uuid, Document.patient_id == patient.id))
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    db.add(AuditEvent(actor_id=user.id, action="read", resource_type="document", resource_id=document.uuid)); db.commit()
    safe_name = document.name.replace('"', "")
    return Response(document.content, media_type=document.mime_type, headers={"Content-Disposition": f'attachment; filename="{safe_name}"', "ETag": document.sha256})


@app.post("/api/v1/patients/{patient_uuid}/coverages", response_model=CoverageOut, status_code=201)
def create_coverage(patient_uuid: str, body: CoverageCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    payer = db.scalar(select(Payer).where(Payer.name == body.payer_name, Payer.payer_identifier == body.payer_identifier))
    if not payer:
        payer = Payer(name=body.payer_name, payer_identifier=body.payer_identifier); db.add(payer); db.flush()
    coverage = Coverage(patient_id=patient.id, payer_id=payer.id, **body.model_dump(exclude={"payer_name", "payer_identifier"}))
    db.add(coverage); db.flush(); db.add(AuditEvent(actor_id=user.id, action="create", resource_type="coverage", resource_id=coverage.uuid)); db.commit(); db.refresh(coverage)
    return CoverageOut(uuid=coverage.uuid, **body.model_dump())


@app.get("/api/v1/patients/{patient_uuid}/coverages", response_model=list[CoverageOut])
def list_coverages(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    rows = db.execute(select(Coverage, Payer).join(Payer).where(Coverage.patient_id == patient.id).order_by(Coverage.priority)).all()
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="coverage", resource_id=patient.uuid)); db.commit()
    return [CoverageOut(uuid=c.uuid, payer_name=p.name, payer_identifier=p.payer_identifier, **{k:getattr(c,k) for k in ("priority","plan_name","policy_number","group_number","subscriber_name","relationship","starts_on","ends_on")}) for c,p in rows]


@app.post("/api/v1/patients/{patient_uuid}/charges", response_model=ChargeOut, status_code=201)
def create_charge(patient_uuid: str, body: ChargeCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid); encounter = encounter_for_patient(db, patient, body.encounter_uuid)
    charge = Charge(patient_id=patient.id, encounter_id=encounter.id, **body.model_dump(exclude={"encounter_uuid"}))
    db.add(charge); db.flush(); db.add(AuditEvent(actor_id=user.id, action="create", resource_type="charge", resource_id=charge.uuid)); db.commit(); db.refresh(charge)
    return ChargeOut(uuid=charge.uuid, **body.model_dump())


@app.get("/api/v1/patients/{patient_uuid}/charges", response_model=list[ChargeOut])
def list_unclaimed_charges(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    rows = db.execute(select(Charge, Encounter.uuid).join(Encounter).where(Charge.patient_id == patient.id, Charge.claim_id.is_(None),Charge.active.is_(True)).order_by(Charge.id)).all()
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="charge", resource_id=patient.uuid)); db.commit()
    return [ChargeOut(uuid=charge.uuid, encounter_uuid=encounter_uuid, **{key:getattr(charge,key) for key in ("code_system","code","description","units","unit_price","billed_at","modifier","authorized","billed","justification","active")}) for charge,encounter_uuid in rows]


def serialize_claim(db: Session, claim: Claim) -> ClaimOut:
    encounter = db.get(Encounter, claim.encounter_id); coverage = db.get(Coverage, claim.coverage_id) if claim.coverage_id else None
    charges = list(db.scalars(select(Charge).where(Charge.claim_id == claim.id,Charge.active.is_(True)))); payments = list(db.scalars(select(ClaimPayment).where(ClaimPayment.claim_id == claim.id)))
    paid = sum((payment.amount for payment in payments), Decimal("0.00"))
    return ClaimOut(uuid=claim.uuid, encounter_uuid=encounter.uuid, coverage_uuid=coverage.uuid if coverage else None, status=claim.status, total=claim.total, paid=paid, balance=claim.total-paid, charges=[ChargeOut(uuid=x.uuid, encounter_uuid=encounter.uuid, **{key:getattr(x,key) for key in ("code_system","code","description","units","unit_price","billed_at","modifier","authorized","billed","justification","active")}) for x in charges], payments=payments, created_at=claim.created_at)


@app.post("/api/v1/patients/{patient_uuid}/claims", response_model=ClaimOut, status_code=201)
def create_claim(patient_uuid: str, body: ClaimCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid); encounter = encounter_for_patient(db, patient, body.encounter_uuid)
    coverage = None
    if body.coverage_uuid:
        coverage = db.scalar(select(Coverage).where(Coverage.uuid == body.coverage_uuid, Coverage.patient_id == patient.id))
        if not coverage: raise HTTPException(status_code=404, detail="Coverage not found for patient")
    charges = list(db.scalars(select(Charge).where(Charge.uuid.in_(body.charge_uuids), Charge.patient_id == patient.id, Charge.encounter_id == encounter.id, Charge.claim_id.is_(None),Charge.active.is_(True))))
    if len(charges) != len(set(body.charge_uuids)): raise HTTPException(status_code=422, detail="Charges must be unclaimed and belong to encounter")
    total = sum((charge.unit_price * charge.units for charge in charges), Decimal("0.00"))
    claim = Claim(patient_id=patient.id, encounter_id=encounter.id, coverage_id=coverage.id if coverage else None, total=total)
    db.add(claim); db.flush()
    for charge in charges: charge.claim_id = claim.id
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="claim", resource_id=claim.uuid)); db.commit(); db.refresh(claim)
    return serialize_claim(db, claim)


@app.post("/api/v1/claims/{claim_uuid}/submit", response_model=ClaimOut)
def submit_claim(claim_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    claim = db.scalar(select(Claim).where(Claim.uuid == claim_uuid))
    if not claim: raise HTTPException(status_code=404, detail="Claim not found")
    if claim.status != "draft": raise HTTPException(status_code=409, detail="Only draft claims can be submitted")
    claim.status="submitted"; claim.submitted_at=datetime.now(timezone.utc); db.add(AuditEvent(actor_id=user.id, action="submit", resource_type="claim", resource_id=claim.uuid)); db.commit(); db.refresh(claim)
    return serialize_claim(db, claim)


@app.post("/api/v1/claims/{claim_uuid}/payments", response_model=ClaimOut, status_code=201)
def post_payment(claim_uuid: str, body: PaymentCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    claim = db.scalar(select(Claim).where(Claim.uuid == claim_uuid))
    if not claim: raise HTTPException(status_code=404, detail="Claim not found")
    paid = db.scalar(select(func.coalesce(func.sum(ClaimPayment.amount), 0)).where(ClaimPayment.claim_id == claim.id))
    if Decimal(paid) + body.amount > claim.total: raise HTTPException(status_code=422, detail="Payment exceeds claim balance")
    payment=ClaimPayment(claim_id=claim.id, **body.model_dump()); db.add(payment); db.flush()
    if Decimal(paid)+body.amount == claim.total: claim.status="paid"
    db.add(AuditEvent(actor_id=user.id, action="payment", resource_type="claim", resource_id=claim.uuid, detail=f"amount={body.amount}")); db.commit(); db.refresh(claim)
    return serialize_claim(db, claim)


@app.get("/api/v1/patients/{patient_uuid}/claims", response_model=list[ClaimOut])
def list_claims(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    claims = list(db.scalars(select(Claim).where(Claim.patient_id == patient.id).order_by(Claim.created_at.desc())))
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="claim", resource_id=patient.uuid)); db.commit()
    return [serialize_claim(db, claim) for claim in claims]


@app.post("/api/v1/patients/{patient_uuid}/immunizations", response_model=ImmunizationOut, status_code=201)
def create_immunization(patient_uuid: str, body: ImmunizationCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid); encounter=encounter_for_patient(db,patient,body.encounter_uuid)
    item=Immunization(patient_id=patient.id,encounter_id=encounter.id if encounter else None,**body.model_dump(exclude={"encounter_uuid"})); db.add(item); db.flush(); db.add(AuditEvent(actor_id=user.id,action="create",resource_type="immunization",resource_id=item.uuid)); db.commit(); db.refresh(item)
    return ImmunizationOut(uuid=item.uuid,encounter_uuid=encounter.uuid if encounter else None,**body.model_dump(exclude={"encounter_uuid"}))


@app.get("/api/v1/patients/{patient_uuid}/immunizations", response_model=list[ImmunizationOut])
def list_immunizations(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid); rows=db.execute(select(Immunization,Encounter.uuid).outerjoin(Encounter).where(Immunization.patient_id==patient.id).order_by(Immunization.administered_at.desc())).all(); db.add(AuditEvent(actor_id=user.id,action="search",resource_type="immunization",resource_id=patient.uuid)); db.commit()
    return [ImmunizationOut(uuid=x.uuid,encounter_uuid=e,**{k:getattr(x,k) for k in ("administered_at","cvx_code","vaccine_name","manufacturer","lot_number","route","site","dose","status","refusal_reason","note")}) for x,e in rows]


@app.post("/api/v1/patients/{patient_uuid}/vitals", response_model=VitalSetOut, status_code=201)
def create_vitals(patient_uuid: str, body: VitalSetCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid); encounter=encounter_for_patient(db,patient,body.encounter_uuid); data=body.model_dump(exclude={"encounter_uuid"}); bmi=None
    if body.weight_kg and body.height_cm: bmi=(body.weight_kg/((body.height_cm/Decimal("100"))**2)).quantize(Decimal("0.01"))
    item=VitalSet(patient_id=patient.id,encounter_id=encounter.id if encounter else None,bmi=bmi,**data); db.add(item); db.flush(); db.add(AuditEvent(actor_id=user.id,action="create",resource_type="vitals",resource_id=item.uuid)); db.commit(); db.refresh(item)
    return VitalSetOut(uuid=item.uuid,encounter_uuid=encounter.uuid if encounter else None,bmi=item.bmi,**data)


@app.get("/api/v1/patients/{patient_uuid}/vitals", response_model=list[VitalSetOut])
def list_vitals(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid); rows=db.execute(select(VitalSet,Encounter.uuid).outerjoin(Encounter).where(VitalSet.patient_id==patient.id).order_by(VitalSet.observed_at.desc())).all(); db.add(AuditEvent(actor_id=user.id,action="search",resource_type="vitals",resource_id=patient.uuid)); db.commit()
    return [VitalSetOut(uuid=x.uuid,encounter_uuid=e,**{k:getattr(x,k) for k in ("observed_at","systolic","diastolic","weight_kg","height_cm","temperature_c","heart_rate","respiratory_rate","oxygen_saturation","bmi","note")}) for x,e in rows]


@app.post("/api/v1/patients/{patient_uuid}/prescriptions", response_model=PrescriptionOut, status_code=201)
def create_prescription(patient_uuid: str, body: PrescriptionCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid); encounter=encounter_for_patient(db,patient,body.encounter_uuid); pharmacy=None
    if body.pharmacy_uuid:
        pharmacy=db.scalar(select(Pharmacy).where(Pharmacy.uuid==body.pharmacy_uuid))
        if not pharmacy: raise HTTPException(status_code=404,detail="Pharmacy not found")
    item=Prescription(patient_id=patient.id,encounter_id=encounter.id if encounter else None,pharmacy_id=pharmacy.id if pharmacy else None,**body.model_dump(exclude={"encounter_uuid","pharmacy_uuid"})); db.add(item); db.flush(); db.add(AuditEvent(actor_id=user.id,action="create",resource_type="prescription",resource_id=item.uuid)); db.commit(); db.refresh(item)
    return prescription_out(item,encounter.uuid if encounter else None,pharmacy)


def prescription_out(item: Prescription, encounter_uuid: str | None, pharmacy: Pharmacy | None) -> PrescriptionOut:
    fields=("prescribed_at","start_date","end_date","drug_name","rxnorm_code","dosage_instructions","quantity","refills","substitutions_allowed","indication","dosage","size","route","per_refill","filled_date","note","prn","usage_category","usage_category_title","request_intent","request_intent_title","diagnosis","modified_at","filled_by_legacy_id","provider_legacy_id","drug_legacy_id","form_legacy_id","unit_legacy_id","interval_legacy_id","medication_legacy_id","legacy_recorded_at","legacy_user","site","prescription_guid","erx_source","erx_uploaded","erx_drug_info","external_id","ntx","rtx","transaction_date")
    return PrescriptionOut(uuid=item.uuid,status=item.status,encounter_uuid=encounter_uuid,pharmacy_uuid=pharmacy.uuid if pharmacy else None,pharmacy_name=pharmacy.name if pharmacy else None,**{key:getattr(item,key) for key in fields})


@app.get("/api/v1/patients/{patient_uuid}/prescriptions", response_model=list[PrescriptionOut])
def list_prescriptions(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid); rows=db.execute(select(Prescription,Encounter.uuid,Pharmacy).outerjoin(Encounter,Prescription.encounter_id==Encounter.id).outerjoin(Pharmacy,Prescription.pharmacy_id==Pharmacy.id).where(Prescription.patient_id==patient.id).order_by(Prescription.prescribed_at.desc().nullslast(),Prescription.id.desc())).all(); db.add(AuditEvent(actor_id=user.id,action="search",resource_type="prescription",resource_id=patient.uuid)); db.commit()
    return [prescription_out(item,encounter_uuid,pharmacy) for item,encounter_uuid,pharmacy in rows]


@app.get("/api/v1/clinical-form-definitions")
def clinical_form_definitions(user: User = Depends(clinical_user)):
    return FORM_DEFINITIONS


def validated_form_content(form_type: str, content: dict) -> dict:
    try:
        return validate_clinical_form_content(form_type, content)
    except ClinicalFormValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/v1/patients/{patient_uuid}/clinical-forms", response_model=ClinicalFormOut, status_code=201)
def create_clinical_form(patient_uuid: str, body: ClinicalFormCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid); encounter = encounter_for_patient(db, patient, body.encounter_uuid)
    if encounter_locked(db, encounter.id): raise HTTPException(status_code=423, detail="Encounter is electronically signed and locked")
    data=body.model_dump(exclude={"encounter_uuid"});data["content"]=validated_form_content(body.form_type,body.content)
    item = ClinicalForm(patient_id=patient.id, encounter_id=encounter.id, author_id=user.id, **data); db.add(item); db.flush()
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="clinical_form", resource_id=item.uuid)); db.commit(); db.refresh(item)
    return ClinicalFormOut(encounter_uuid=encounter.uuid, **{k: getattr(item, k) for k in ("uuid", "form_type", "title", "content", "status", "authored_at", "signed_at")})


def clinical_form_out(item: ClinicalForm, encounter_uuid: str, db: Session) -> ClinicalFormOut:
    signatures = form_signatures(db, item.id)
    return ClinicalFormOut(encounter_uuid=encounter_uuid, locked=form_locked(db,item), signature_count=len(signatures), **{k:getattr(item,k) for k in ("uuid","form_type","title","content","status","authored_at","signed_at","released_to_patient_at")})


@app.get("/api/v1/patients/{patient_uuid}/clinical-forms", response_model=list[ClinicalFormOut])
def list_clinical_forms(patient_uuid: str, encounter_uuid: str | None = None, form_type: str | None = None, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid); query = select(ClinicalForm, Encounter.uuid).join(Encounter).where(ClinicalForm.patient_id == patient.id)
    if encounter_uuid: query = query.where(Encounter.uuid == encounter_uuid)
    if form_type: query = query.where(ClinicalForm.form_type == form_type)
    rows = db.execute(query.order_by(ClinicalForm.authored_at.desc())).all(); db.add(AuditEvent(actor_id=user.id, action="search", resource_type="clinical_form", resource_id=patient.uuid)); db.commit()
    return [clinical_form_out(x, e, db) for x, e in rows]


@app.put("/api/v1/patients/{patient_uuid}/clinical-forms/{form_uuid}", response_model=ClinicalFormOut)
def update_clinical_form(patient_uuid: str, form_uuid: str, body: ClinicalFormUpdate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    row = db.execute(select(ClinicalForm, Encounter.uuid).join(Encounter).where(ClinicalForm.uuid == form_uuid, ClinicalForm.patient_id == patient.id).with_for_update()).first()
    if not row: raise HTTPException(status_code=404, detail="Clinical form not found")
    item, encounter_uuid = row
    if form_locked(db, item): raise HTTPException(status_code=423, detail="Clinical form is electronically signed and locked")
    item.title = body.title; item.content = validated_form_content(item.form_type,body.content)
    db.add(AuditEvent(actor_id=user.id, action="update", resource_type="clinical_form", resource_id=item.uuid)); db.commit(); db.refresh(item)
    return clinical_form_out(item, encounter_uuid, db)


@app.post("/api/v1/patients/{patient_uuid}/clinical-forms/{form_uuid}/sign", response_model=ClinicalSignatureOut, status_code=201)
def sign_clinical_form(patient_uuid: str, form_uuid: str, body: ClinicalSignatureCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid); row = db.execute(select(ClinicalForm, Encounter.uuid).join(Encounter).where(ClinicalForm.uuid == form_uuid, ClinicalForm.patient_id == patient.id).with_for_update()).first()
    if not row: raise HTTPException(status_code=404, detail="Clinical form not found")
    item, encounter_uuid = row
    if not password_hash.verify(body.password, user.password_hash): raise HTTPException(status_code=401, detail="Signature reauthentication failed")
    if form_locked(db, item) and not body.amendment: raise HTTPException(status_code=409, detail="A locked form requires an amendment note for another signature")
    signature = create_signature(db, item, user, lock=body.lock, attestation=body.attestation, amendment=body.amendment)
    item.status = "signed"; item.signed_at = signature.signed_at; item.signed_by_id = user.id
    db.add(AuditEvent(actor_id=user.id, action="sign", resource_type="clinical_form", resource_id=item.uuid, detail=f"signature={signature.uuid}; lock={body.lock}; content_hash={signature.content_hash}")); db.commit(); db.refresh(signature)
    return ClinicalSignatureOut(**{key:getattr(signature,key) for key in ("uuid","target_type","signer_name","signer_role","signed_at","auth_method","is_lock","attestation","amendment","content_hash","previous_signature_hash","signature_hash")}, integrity_valid=True)


@app.get("/api/v1/patients/{patient_uuid}/clinical-forms/{form_uuid}/signatures", response_model=list[ClinicalSignatureOut])
def list_clinical_signatures(patient_uuid: str, form_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid); item = db.scalar(select(ClinicalForm).where(ClinicalForm.uuid == form_uuid, ClinicalForm.patient_id == patient.id))
    if not item: raise HTTPException(status_code=404, detail="Clinical form not found")
    signatures = form_signatures(db, item.id); validity = verify_signature_chain(db, item, signatures)
    db.add(AuditEvent(actor_id=user.id, action="verify", resource_type="clinical_signature", resource_id=item.uuid, detail=f"records={len(signatures)}; valid={all(validity)}")); db.commit()
    return [ClinicalSignatureOut(**{key:getattr(signature,key) for key in ("uuid","target_type","signer_name","signer_role","signed_at","auth_method","is_lock","attestation","amendment","content_hash","previous_signature_hash","signature_hash")}, integrity_valid=valid) for signature,valid in zip(signatures,validity)]


@app.post("/api/v1/patients/{patient_uuid}/encounters/{encounter_uuid}/sign",response_model=ClinicalSignatureOut,status_code=201)
def sign_encounter(patient_uuid:str,encounter_uuid:str,body:ClinicalSignatureCreate,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);encounter=db.scalar(select(Encounter).where(Encounter.uuid==encounter_uuid,Encounter.patient_id==patient.id).with_for_update())
    if not encounter:raise HTTPException(status_code=404,detail="Encounter not found")
    if not password_hash.verify(body.password,user.password_hash):raise HTTPException(status_code=401,detail="Signature reauthentication failed")
    if encounter_locked(db,encounter.id) and not body.amendment:raise HTTPException(status_code=409,detail="A locked encounter requires an amendment note for another signature")
    signature=create_encounter_signature(db,encounter,user,lock=body.lock,attestation=body.attestation,amendment=body.amendment)
    db.add(AuditEvent(actor_id=user.id,action="sign",resource_type="encounter",resource_id=encounter.uuid,detail=f"signature={signature.uuid}; lock={body.lock}; content_hash={signature.content_hash}"));db.commit();db.refresh(signature)
    return ClinicalSignatureOut(**{key:getattr(signature,key) for key in ("uuid","target_type","signer_name","signer_role","signed_at","auth_method","is_lock","attestation","amendment","content_hash","previous_signature_hash","signature_hash")},integrity_valid=True)


@app.get("/api/v1/patients/{patient_uuid}/encounters/{encounter_uuid}/signatures",response_model=list[ClinicalSignatureOut])
def list_encounter_signatures(patient_uuid:str,encounter_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);encounter=db.scalar(select(Encounter).where(Encounter.uuid==encounter_uuid,Encounter.patient_id==patient.id))
    if not encounter:raise HTTPException(status_code=404,detail="Encounter not found")
    signatures=encounter_signatures(db,encounter.id);validity=verify_encounter_signature_chain(db,encounter,signatures)
    db.add(AuditEvent(actor_id=user.id,action="verify",resource_type="encounter_signature",resource_id=encounter.uuid,detail=f"records={len(signatures)}; valid={all(validity)}"));db.commit()
    return [ClinicalSignatureOut(**{key:getattr(signature,key) for key in ("uuid","target_type","signer_name","signer_role","signed_at","auth_method","is_lock","attestation","amendment","content_hash","previous_signature_hash","signature_hash")},integrity_valid=valid) for signature,valid in zip(signatures,validity)]


@app.get("/api/v1/questionnaires", response_model=list[QuestionnaireDefinitionOut])
def list_questionnaires(db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    rows = list(db.scalars(select(QuestionnaireDefinition).where(QuestionnaireDefinition.active.is_(True)).order_by(QuestionnaireDefinition.code)))
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="questionnaire_definition")); db.commit(); return rows


def questionnaire_interpretation(code: str, score: int) -> str:
    if code == "PHQ-9":
        return "minimal" if score < 5 else "mild" if score < 10 else "moderate" if score < 15 else "moderately-severe" if score < 20 else "severe"
    return "minimal" if score < 5 else "mild" if score < 10 else "moderate" if score < 15 else "severe"


@app.post("/api/v1/patients/{patient_uuid}/questionnaire-responses", response_model=QuestionnaireResponseOut, status_code=201)
def create_questionnaire_response(patient_uuid: str, body: QuestionnaireResponseCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid); definition = db.scalar(select(QuestionnaireDefinition).where(QuestionnaireDefinition.uuid == body.questionnaire_uuid, QuestionnaireDefinition.active.is_(True)))
    if not definition: raise HTTPException(status_code=404, detail="Questionnaire not found")
    encounter = encounter_for_patient(db, patient, body.encounter_uuid); expected = {item["id"] for item in definition.questions}
    if set(body.answers) != expected or any(not isinstance(value, int) or value < 0 or value > 3 for value in body.answers.values()): raise HTTPException(status_code=422, detail="Every questionnaire item requires an integer answer from 0 to 3")
    score = sum(body.answers.values()); item = QuestionnaireResponse(patient_id=patient.id, encounter_id=encounter.id if encounter else None, questionnaire_id=definition.id, answers=body.answers, score=score, interpretation=questionnaire_interpretation(definition.code, score), author_id=user.id)
    db.add(item); db.flush(); db.add(AuditEvent(actor_id=user.id, action="create", resource_type="questionnaire_response", resource_id=item.uuid, detail=f"{definition.code} score={score}")); db.commit(); db.refresh(item)
    return QuestionnaireResponseOut(uuid=item.uuid, code=definition.code, score=item.score, interpretation=item.interpretation, authored_at=item.authored_at, **body.model_dump())


@app.get("/api/v1/patients/{patient_uuid}/questionnaire-responses", response_model=list[QuestionnaireResponseOut])
def list_questionnaire_responses(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid); rows = db.execute(select(QuestionnaireResponse, QuestionnaireDefinition, Encounter.uuid).join(QuestionnaireDefinition).outerjoin(Encounter).where(QuestionnaireResponse.patient_id == patient.id).order_by(QuestionnaireResponse.authored_at.desc())).all()
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="questionnaire_response", resource_id=patient.uuid)); db.commit()
    return [QuestionnaireResponseOut(uuid=x.uuid, questionnaire_uuid=q.uuid, encounter_uuid=e, answers=x.answers, code=q.code, score=x.score, interpretation=x.interpretation, authored_at=x.authored_at) for x, q, e in rows]
