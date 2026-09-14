from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent, Patient, User
from ..schemas import PatientCreate, PatientOut, PatientPage, PatientUpdate
from ..security import patient_demographics_user, patient_demographics_write_user
from ..services.patients import patient_by_uuid

router = APIRouter(prefix="/api/v1/patients", tags=["patients"])


@router.get("", response_model=PatientPage)
def list_patients(
    q: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(patient_demographics_user),
) -> PatientPage:
    filters = []
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        term = f"%{escaped}%"
        filters.append(
            or_(
                Patient.first_name.ilike(term, escape="\\"),
                Patient.last_name.ilike(term, escape="\\"),
                Patient.email.ilike(term, escape="\\"),
            )
        )
    items = db.scalars(
        select(Patient)
        .where(*filters)
        .order_by(Patient.last_name, Patient.first_name)
        .limit(limit)
        .offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(Patient).where(*filters)) or 0
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="patient"))
    db.commit()
    return PatientPage(items=list(items), total=total, limit=limit, offset=offset)


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
def create_patient(
    body: PatientCreate,
    db: Session = Depends(get_db),
    user: User = Depends(patient_demographics_write_user),
) -> Patient:
    patient = Patient(**body.model_dump())
    db.add(patient)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="create",
            resource_type="patient",
            resource_id=patient.uuid,
        )
    )
    db.commit()
    db.refresh(patient)
    return patient


@router.get("/{patient_uuid}", response_model=PatientOut)
def get_patient(
    patient_uuid: str,
    db: Session = Depends(get_db),
    user: User = Depends(patient_demographics_user),
) -> Patient:
    patient = patient_by_uuid(db, patient_uuid)
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="read",
            resource_type="patient",
            resource_id=patient.uuid,
        )
    )
    db.commit()
    return patient


@router.patch("/{patient_uuid}", response_model=PatientOut)
def update_patient(
    patient_uuid: str,
    body: PatientUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(patient_demographics_write_user),
) -> Patient:
    patient = patient_by_uuid(db, patient_uuid)
    changes = body.model_dump(exclude_unset=True)
    if "country_code" in changes and changes["country_code"]:
        changes["country_code"] = changes["country_code"].upper()
    effective_email = changes.get("email", patient.email)
    effective_phone = changes.get("phone", patient.phone)
    if changes.get("allow_email", patient.allow_email) and not effective_email:
        raise HTTPException(status_code=422, detail="email is required when allow_email is enabled")
    if changes.get("allow_sms", patient.allow_sms) and not effective_phone:
        raise HTTPException(status_code=422, detail="phone is required when allow_sms is enabled")
    for field, value in changes.items():
        setattr(patient, field, value)
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="update",
            resource_type="patient",
            resource_id=patient.uuid,
            detail=",".join(sorted(changes)),
        )
    )
    db.commit()
    db.refresh(patient)
    return patient


@router.put("/{patient_uuid}", response_model=PatientOut)
def replace_patient(
    patient_uuid: str,
    body: PatientCreate,
    db: Session = Depends(get_db),
    user: User = Depends(patient_demographics_write_user),
) -> Patient:
    patient = patient_by_uuid(db, patient_uuid)
    changes = body.model_dump()
    for field, value in changes.items():
        setattr(patient, field, value)
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="update",
            resource_type="patient",
            resource_id=patient.uuid,
            detail="full-replacement",
        )
    )
    db.commit()
    db.refresh(patient)
    return patient
