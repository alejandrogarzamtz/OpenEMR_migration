from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent, Patient, PatientAddress, PatientRelatedPerson, PatientTelecom, User
from ..schemas import InactivationRequest, PatientAddressCreate, PatientAddressOut, PatientCreate, PatientOut, PatientPage, PatientRelatedPersonCreate, PatientRelatedPersonOut, PatientTelecomCreate, PatientTelecomOut, PatientUpdate
from ..security import patient_demographics_user, patient_demographics_write_user
from ..services.patients import patient_by_uuid

router = APIRouter(prefix="/api/v1/patients", tags=["patients"])


def sync_primary_address(patient: Patient, item: PatientAddress | None) -> None:
    patient.address_line_1 = item.line1 if item else None
    patient.address_line_2 = item.line2 if item else None
    patient.city = item.city if item else None
    patient.state = item.state if item else None
    patient.postal_code = item.postal_code if item else None
    patient.country_code = item.country_code if item else None


def sync_primary_telecom(patient: Patient, item: PatientTelecom | None, system: str) -> None:
    if system == "email":
        patient.email = item.value if item else None
    elif system in {"phone", "sms"}:
        patient.phone = item.value if item else None


@router.post("/{patient_uuid}/related-people/{person_uuid}/inactivate", response_model=PatientRelatedPersonOut)
def inactivate_related_person(patient_uuid: str, person_uuid: str, body: InactivationRequest, db: Session = Depends(get_db), user: User = Depends(patient_demographics_write_user)):
    patient = patient_by_uuid(db, patient_uuid)
    item = db.scalar(select(PatientRelatedPerson).where(PatientRelatedPerson.uuid == person_uuid, PatientRelatedPerson.patient_id == patient.id))
    if not item: raise HTTPException(status_code=404, detail="Related person not found")
    item.active = False; item.is_primary_contact = False; item.is_emergency_contact = False
    item.can_make_medical_decisions = False; item.can_receive_medical_info = False
    item.notes = f"{item.notes + ' | ' if item.notes else ''}Inactivated: {body.reason}"
    db.add(AuditEvent(actor_id=user.id, action="inactivate", resource_type="patient_related_person", resource_id=item.uuid, detail=body.reason)); db.commit(); db.refresh(item)
    return item


@router.post("/{patient_uuid}/telecoms/{telecom_uuid}/inactivate", response_model=PatientTelecomOut)
def inactivate_telecom(patient_uuid: str, telecom_uuid: str, body: InactivationRequest, db: Session = Depends(get_db), user: User = Depends(patient_demographics_write_user)):
    patient = patient_by_uuid(db, patient_uuid)
    item = db.scalar(select(PatientTelecom).where(PatientTelecom.uuid == telecom_uuid, PatientTelecom.patient_id == patient.id))
    if not item: raise HTTPException(status_code=404, detail="Patient telecom not found")
    was_primary = item.is_primary
    item.active = False; item.is_primary = False; item.inactivated_reason = body.reason
    if was_primary:
        replacement = db.scalar(select(PatientTelecom).where(PatientTelecom.patient_id == patient.id, PatientTelecom.system == item.system, PatientTelecom.active.is_(True), PatientTelecom.id != item.id).order_by(PatientTelecom.rank, PatientTelecom.id))
        if replacement: replacement.is_primary = True
        sync_primary_telecom(patient, replacement, item.system)
    db.add(AuditEvent(actor_id=user.id, action="inactivate", resource_type="patient_telecom", resource_id=item.uuid, detail=body.reason)); db.commit(); db.refresh(item)
    return item


@router.post("/{patient_uuid}/addresses/{address_uuid}/inactivate", response_model=PatientAddressOut)
def inactivate_address(patient_uuid: str, address_uuid: str, body: InactivationRequest, db: Session = Depends(get_db), user: User = Depends(patient_demographics_write_user)):
    patient = patient_by_uuid(db, patient_uuid)
    item = db.scalar(select(PatientAddress).where(PatientAddress.uuid == address_uuid, PatientAddress.patient_id == patient.id))
    if not item: raise HTTPException(status_code=404, detail="Patient address not found")
    was_primary = item.is_primary
    item.active = False; item.is_primary = False; item.inactivated_reason = body.reason
    if was_primary:
        replacement = db.scalar(select(PatientAddress).where(PatientAddress.patient_id == patient.id, PatientAddress.active.is_(True), PatientAddress.id != item.id).order_by(PatientAddress.priority, PatientAddress.id))
        if replacement: replacement.is_primary = True
        sync_primary_address(patient, replacement)
    db.add(AuditEvent(actor_id=user.id, action="inactivate", resource_type="patient_address", resource_id=item.uuid, detail=body.reason)); db.commit(); db.refresh(item)
    return item


@router.get("/{patient_uuid}/related-people", response_model=list[PatientRelatedPersonOut])
def list_related_people(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(patient_demographics_user)):
    patient = patient_by_uuid(db, patient_uuid)
    return list(db.scalars(select(PatientRelatedPerson).where(PatientRelatedPerson.patient_id == patient.id).order_by(PatientRelatedPerson.active.desc(), PatientRelatedPerson.priority, PatientRelatedPerson.last_name)))


@router.post("/{patient_uuid}/related-people", response_model=PatientRelatedPersonOut, status_code=status.HTTP_201_CREATED)
def create_related_person(patient_uuid: str, body: PatientRelatedPersonCreate, db: Session = Depends(get_db), user: User = Depends(patient_demographics_write_user)):
    patient = patient_by_uuid(db, patient_uuid)
    if body.is_primary_contact:
        for current in db.scalars(select(PatientRelatedPerson).where(PatientRelatedPerson.patient_id == patient.id, PatientRelatedPerson.active.is_(True))): current.is_primary_contact = False
    item = PatientRelatedPerson(patient_id=patient.id, **body.model_dump()); db.add(item); db.flush()
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="patient_related_person", resource_id=item.uuid, detail="relationship-does-not-authorize-portal")); db.commit(); db.refresh(item)
    return item


@router.get("/{patient_uuid}/telecoms", response_model=list[PatientTelecomOut])
def list_telecoms(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(patient_demographics_user)):
    patient = patient_by_uuid(db, patient_uuid)
    return list(db.scalars(select(PatientTelecom).where(PatientTelecom.patient_id == patient.id).order_by(PatientTelecom.active.desc(), PatientTelecom.rank)))


@router.post("/{patient_uuid}/telecoms", response_model=PatientTelecomOut, status_code=status.HTTP_201_CREATED)
def create_telecom(patient_uuid: str, body: PatientTelecomCreate, db: Session = Depends(get_db), user: User = Depends(patient_demographics_write_user)):
    patient = patient_by_uuid(db, patient_uuid)
    if body.is_primary:
        for current in db.scalars(select(PatientTelecom).where(PatientTelecom.patient_id == patient.id, PatientTelecom.system == body.system, PatientTelecom.active.is_(True))): current.is_primary = False
    item = PatientTelecom(patient_id=patient.id, **body.model_dump()); db.add(item); db.flush()
    if item.is_primary: sync_primary_telecom(patient, item, item.system)
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="patient_telecom", resource_id=item.uuid)); db.commit(); db.refresh(item)
    return item


@router.get("/{patient_uuid}/addresses", response_model=list[PatientAddressOut])
def list_addresses(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(patient_demographics_user)):
    patient = patient_by_uuid(db, patient_uuid)
    return list(db.scalars(select(PatientAddress).where(PatientAddress.patient_id == patient.id).order_by(PatientAddress.active.desc(), PatientAddress.priority, PatientAddress.id)))


@router.post("/{patient_uuid}/addresses", response_model=PatientAddressOut, status_code=status.HTTP_201_CREATED)
def create_address(patient_uuid: str, body: PatientAddressCreate, db: Session = Depends(get_db), user: User = Depends(patient_demographics_write_user)):
    patient = patient_by_uuid(db, patient_uuid)
    if body.is_primary:
        for item in db.scalars(select(PatientAddress).where(PatientAddress.patient_id == patient.id, PatientAddress.active.is_(True))):
            item.is_primary = False
    item = PatientAddress(patient_id=patient.id, **body.model_dump())
    db.add(item); db.flush()
    if item.is_primary: sync_primary_address(patient, item)
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="patient_address", resource_id=item.uuid, detail=f"patient={patient.uuid}"))
    db.commit(); db.refresh(item)
    return item


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
