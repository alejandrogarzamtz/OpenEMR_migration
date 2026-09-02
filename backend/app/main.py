from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .models import Appointment, AuditEvent, Encounter, Patient, User
from .schemas import AppointmentCreate, AppointmentOut, EncounterCreate, EncounterOut, Login, PatientCreate, PatientOut, PatientPage, Token
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
