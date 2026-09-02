from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .models import Appointment, AuditEvent, Charge, Claim, ClaimPayment, ClinicalItem, Coverage, Document, Encounter, Immunization, LabOrder, LabResult, Patient, Payer, Pharmacy, Prescription, User, VitalSet
from .schemas import AppointmentCreate, AppointmentOut, ChargeCreate, ChargeOut, ClaimCreate, ClaimOut, ClinicalItemCreate, ClinicalItemOut, ClinicalSummary, CoverageCreate, CoverageOut, DocumentOut, EncounterCreate, EncounterOut, ImmunizationCreate, ImmunizationOut, LabOrderCreate, LabOrderDetail, LabOrderOut, LabResultCreate, LabResultOut, Login, PatientCreate, PatientOut, PatientPage, PaymentCreate, PaymentOut, PrescriptionCreate, PrescriptionOut, Token, VitalSetCreate, VitalSetOut
from .security import clinical_user, create_token, password_hash
from .fhir import router as fhir_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Unit tests use an isolated in-memory database. Deployed databases are
    # changed exclusively through Alembic before the API process starts.
    if settings.database_url == "sqlite://":
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.email == "admin@example.com")):
            db.add(User(email="admin@example.com", password_hash=password_hash.hash("change-me-now"), role="admin"))
            db.commit()
    yield


app = FastAPI(title="OpenEMR Next API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(fhir_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/auth/token", response_model=Token)
def login(body: Login, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))
    if not user or not password_hash.verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return Token(access_token=create_token(user))


@app.get("/api/v1/patients", response_model=PatientPage)
def list_patients(q: str | None = None, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    filters = []
    if q:
        filters.append(or_(Patient.first_name.ilike(f"%{q}%"), Patient.last_name.ilike(f"%{q}%"), Patient.email.ilike(f"%{q}%")))
    items = db.scalars(select(Patient).where(*filters).order_by(Patient.last_name, Patient.first_name).limit(limit).offset(offset)).all()
    total = db.scalar(select(func.count()).select_from(Patient).where(*filters)) or 0
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="patient", detail=f"query={q or ''}"))
    db.commit()
    return PatientPage(items=list(items), total=total, limit=limit, offset=offset)


@app.post("/api/v1/patients", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
def create_patient(body: PatientCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = Patient(**body.model_dump())
    db.add(patient)
    db.flush()
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="patient", resource_id=patient.uuid))
    db.commit()
    db.refresh(patient)
    return patient


@app.get("/api/v1/patients/{patient_uuid}", response_model=PatientOut)
def get_patient(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = db.scalar(select(Patient).where(Patient.uuid == patient_uuid))
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    db.add(AuditEvent(actor_id=user.id, action="read", resource_type="patient", resource_id=patient.uuid))
    db.commit()
    return patient


def patient_by_uuid(db: Session, patient_uuid: str) -> Patient:
    patient = db.scalar(select(Patient).where(Patient.uuid == patient_uuid))
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@app.get("/api/v1/appointments", response_model=list[AppointmentOut])
def list_appointments(patient_uuid: str | None = None, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    query = select(Appointment, Patient.uuid).join(Patient).order_by(Appointment.starts_at)
    if patient_uuid:
        query = query.where(Patient.uuid == patient_uuid)
    rows = db.execute(query).all()
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="appointment")); db.commit()
    return [AppointmentOut(patient_uuid=p_uuid, **{k: getattr(item, k) for k in ("uuid", "starts_at", "ends_at", "status", "reason", "provider_name")}) for item, p_uuid in rows]


@app.post("/api/v1/appointments", response_model=AppointmentOut, status_code=201)
def create_appointment(body: AppointmentCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    if body.ends_at <= body.starts_at:
        raise HTTPException(status_code=422, detail="ends_at must be after starts_at")
    patient = patient_by_uuid(db, body.patient_uuid)
    item = Appointment(patient_id=patient.id, **body.model_dump(exclude={"patient_uuid"}))
    db.add(item); db.flush(); db.add(AuditEvent(actor_id=user.id, action="create", resource_type="appointment", resource_id=item.uuid)); db.commit(); db.refresh(item)
    return AppointmentOut(patient_uuid=patient.uuid, **{k: getattr(item, k) for k in ("uuid", "starts_at", "ends_at", "status", "reason", "provider_name")})


@app.post("/api/v1/encounters", response_model=EncounterOut, status_code=201)
def create_encounter(body: EncounterCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, body.patient_uuid)
    appointment = None
    if body.appointment_uuid:
        appointment = db.scalar(select(Appointment).where(Appointment.uuid == body.appointment_uuid, Appointment.patient_id == patient.id))
        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found for patient")
        appointment.status = "arrived"
    item = Encounter(patient_id=patient.id, appointment_id=appointment.id if appointment else None, **body.model_dump(exclude={"patient_uuid", "appointment_uuid"}))
    db.add(item); db.flush(); db.add(AuditEvent(actor_id=user.id, action="create", resource_type="encounter", resource_id=item.uuid)); db.commit(); db.refresh(item)
    return EncounterOut(patient_uuid=patient.uuid, appointment_uuid=appointment.uuid if appointment else None, **{k: getattr(item, k) for k in ("uuid", "occurred_at", "type", "status", "chief_complaint", "clinical_note")})


@app.get("/api/v1/patients/{patient_uuid}/encounters", response_model=list[EncounterOut])
def list_encounters(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    rows = db.execute(select(Encounter, Appointment.uuid).outerjoin(Appointment).where(Encounter.patient_id == patient.id).order_by(Encounter.occurred_at.desc())).all()
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="encounter", resource_id=patient.uuid)); db.commit()
    return [EncounterOut(patient_uuid=patient.uuid, appointment_uuid=a_uuid, **{k: getattr(item, k) for k in ("uuid", "occurred_at", "type", "status", "chief_complaint", "clinical_note")}) for item, a_uuid in rows]


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
    encounters = [EncounterOut(patient_uuid=patient.uuid, appointment_uuid=a_uuid, **{k: getattr(item, k) for k in ("uuid", "occurred_at", "type", "status", "chief_complaint", "clinical_note")}) for item, a_uuid in encounter_rows]
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
    return LabOrderOut(encounter_uuid=encounter_uuid, **{key: getattr(order, key) for key in ("uuid", "ordered_at", "code", "name", "priority", "instructions", "status")})


@app.post("/api/v1/patients/{patient_uuid}/lab-orders", response_model=LabOrderOut, status_code=201)
def create_lab_order(patient_uuid: str, body: LabOrderCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid)
    encounter = encounter_for_patient(db, patient, body.encounter_uuid)
    order = LabOrder(patient_id=patient.id, encounter_id=encounter.id if encounter else None, **body.model_dump(exclude={"encounter_uuid"}))
    db.add(order); db.flush(); db.add(AuditEvent(actor_id=user.id, action="create", resource_type="lab_order", resource_id=order.uuid)); db.commit(); db.refresh(order)
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
    results = list(db.scalars(select(LabResult).where(LabResult.order_id == order.id).order_by(LabResult.observed_at)))
    db.add(AuditEvent(actor_id=user.id, action="read", resource_type="lab_order", resource_id=order.uuid)); db.commit()
    return LabOrderDetail(**order_out(order, encounter_uuid).model_dump(), results=results)


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
    rows = db.execute(select(Charge, Encounter.uuid).join(Encounter).where(Charge.patient_id == patient.id, Charge.claim_id.is_(None)).order_by(Charge.id)).all()
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="charge", resource_id=patient.uuid)); db.commit()
    return [ChargeOut(uuid=charge.uuid, encounter_uuid=encounter_uuid, code_system=charge.code_system, code=charge.code, description=charge.description, units=charge.units, unit_price=charge.unit_price) for charge,encounter_uuid in rows]


def serialize_claim(db: Session, claim: Claim) -> ClaimOut:
    encounter = db.get(Encounter, claim.encounter_id); coverage = db.get(Coverage, claim.coverage_id) if claim.coverage_id else None
    charges = list(db.scalars(select(Charge).where(Charge.claim_id == claim.id))); payments = list(db.scalars(select(ClaimPayment).where(ClaimPayment.claim_id == claim.id)))
    paid = sum((payment.amount for payment in payments), Decimal("0.00"))
    return ClaimOut(uuid=claim.uuid, encounter_uuid=encounter.uuid, coverage_uuid=coverage.uuid if coverage else None, status=claim.status, total=claim.total, paid=paid, balance=claim.total-paid, charges=[ChargeOut(uuid=x.uuid, encounter_uuid=encounter.uuid, code_system=x.code_system, code=x.code, description=x.description, units=x.units, unit_price=x.unit_price) for x in charges], payments=payments, created_at=claim.created_at)


@app.post("/api/v1/patients/{patient_uuid}/claims", response_model=ClaimOut, status_code=201)
def create_claim(patient_uuid: str, body: ClaimCreate, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid); encounter = encounter_for_patient(db, patient, body.encounter_uuid)
    coverage = None
    if body.coverage_uuid:
        coverage = db.scalar(select(Coverage).where(Coverage.uuid == body.coverage_uuid, Coverage.patient_id == patient.id))
        if not coverage: raise HTTPException(status_code=404, detail="Coverage not found for patient")
    charges = list(db.scalars(select(Charge).where(Charge.uuid.in_(body.charge_uuids), Charge.patient_id == patient.id, Charge.encounter_id == encounter.id, Charge.claim_id.is_(None))))
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
    return PrescriptionOut(uuid=item.uuid,status=item.status,**body.model_dump())


@app.get("/api/v1/patients/{patient_uuid}/prescriptions", response_model=list[PrescriptionOut])
def list_prescriptions(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid); rows=db.execute(select(Prescription,Encounter.uuid,Pharmacy.uuid).outerjoin(Encounter,Prescription.encounter_id==Encounter.id).outerjoin(Pharmacy,Prescription.pharmacy_id==Pharmacy.id).where(Prescription.patient_id==patient.id).order_by(Prescription.prescribed_at.desc())).all(); db.add(AuditEvent(actor_id=user.id,action="search",resource_type="prescription",resource_id=patient.uuid)); db.commit()
    return [PrescriptionOut(uuid=x.uuid,encounter_uuid=e,pharmacy_uuid=p,status=x.status,**{k:getattr(x,k) for k in ("prescribed_at","start_date","end_date","drug_name","rxnorm_code","dosage_instructions","quantity","refills","substitutions_allowed","indication")}) for x,e,p in rows]
