from contextlib import asynccontextmanager
from hashlib import sha256
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .models import Appointment, AuditEvent, ClinicalItem, Document, Encounter, LabOrder, LabResult, Patient, User
from .schemas import AppointmentCreate, AppointmentOut, ClinicalItemCreate, ClinicalItemOut, ClinicalSummary, DocumentOut, EncounterCreate, EncounterOut, LabOrderCreate, LabOrderDetail, LabOrderOut, LabResultCreate, LabResultOut, Login, PatientCreate, PatientOut, PatientPage, Token
from .security import clinical_user, create_token, password_hash


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.email == "admin@example.com")):
            db.add(User(email="admin@example.com", password_hash=password_hash.hash("change-me-now"), role="admin"))
            db.commit()
    yield


app = FastAPI(title="OpenEMR Next API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


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
