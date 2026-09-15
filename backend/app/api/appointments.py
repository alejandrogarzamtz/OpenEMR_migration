from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Appointment, AuditEvent, Facility, Patient, User
from ..schemas import AppointmentCreate, AppointmentFacilityOut, AppointmentOut, AppointmentUpdate
from ..security import appointment_user, appointment_write_user
from ..services.patients import patient_by_uuid
from ..services.notifications import notify_patient
from ..services.access import facility_scope, require_facility_access

router = APIRouter(prefix="/api/v1/appointments", tags=["appointments"])

ACTIVE_STATUSES = {"scheduled", "confirmed", "arrived", "checked-in", "in-progress", "pending"}


def appointment_out(db: Session, item: Appointment, patient_uuid: str) -> AppointmentOut:
    fields = (
        "uuid", "starts_at", "ends_at", "status", "category_id", "title", "reason",
        "provider_name", "legacy_provider_id", "facility_name", "legacy_facility_id", "room",
        "location", "contact_name", "contact_phone", "contact_email", "language", "all_day",
        "recurrence_rule", "recurrence_group", "send_sms", "send_email",
    )
    facility = db.get(Facility, item.facility_id) if item.facility_id else db.scalar(select(Facility).where(Facility.legacy_facility_id == item.legacy_facility_id)) if item.legacy_facility_id else None
    return AppointmentOut(patient_uuid=patient_uuid, facility_uuid=facility.uuid if facility else None, **{key: getattr(item, key) for key in fields})


def require_appointment_access(db: Session, user: User, item: Appointment) -> None:
    facility_id = item.facility_id
    if not facility_id and item.legacy_facility_id:
        facility_id = db.scalar(select(Facility.id).where(Facility.legacy_facility_id == item.legacy_facility_id))
    require_facility_access(db, user, facility_id)


def ensure_no_conflict(db: Session, item: Appointment, exclude_id: int | None = None) -> None:
    if (item.status or "scheduled") not in ACTIVE_STATUSES:
        return
    resource_filter = []
    if item.legacy_provider_id:
        resource_filter.append(Appointment.legacy_provider_id == item.legacy_provider_id)
    elif item.provider_name:
        resource_filter.append(Appointment.provider_name == item.provider_name)
    if item.legacy_facility_id and item.room:
        resource_filter.append(and_(Appointment.legacy_facility_id == item.legacy_facility_id, Appointment.room == item.room))
    if not resource_filter:
        return
    query = select(Appointment.id).where(
        Appointment.status.in_(ACTIVE_STATUSES),
        Appointment.starts_at < item.ends_at,
        Appointment.ends_at > item.starts_at,
        or_(*resource_filter),
    )
    if exclude_id is not None:
        query = query.where(Appointment.id != exclude_id)
    if db.scalar(query.limit(1)):
        raise HTTPException(status_code=409, detail="Appointment conflicts with an active resource booking")


@router.get("", response_model=list[AppointmentOut])
def list_appointments(
    patient_uuid: str | None = None,
    starts_from: datetime | None = None,
    starts_before: datetime | None = None,
    appointment_status: str | None = Query(default=None, alias="status"),
    provider_id: int | None = None,
    facility_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(appointment_user),
) -> list[AppointmentOut]:
    query = select(Appointment, Patient.uuid).join(Patient)
    scope = facility_scope(db, user)
    if scope is not None:
        legacy_ids = list(db.scalars(select(Facility.legacy_facility_id).where(Facility.id.in_(scope), Facility.legacy_facility_id.is_not(None))))
        query = query.where(or_(Appointment.facility_id.in_(scope), Appointment.legacy_facility_id.in_(legacy_ids)))
    if patient_uuid:
        query = query.where(Patient.uuid == patient_uuid)
    if starts_from:
        query = query.where(Appointment.starts_at >= starts_from)
    if starts_before:
        query = query.where(Appointment.starts_at < starts_before)
    if appointment_status:
        query = query.where(Appointment.status == appointment_status)
    if provider_id:
        query = query.where(Appointment.legacy_provider_id == provider_id)
    if facility_id:
        query = query.where(Appointment.legacy_facility_id == facility_id)
    rows = db.execute(query.order_by(Appointment.starts_at).limit(limit)).all()
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="appointment"))
    db.commit()
    return [appointment_out(db, item, patient_id) for item, patient_id in rows]


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    body: AppointmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(appointment_write_user),
) -> AppointmentOut:
    patient = patient_by_uuid(db, body.patient_uuid)
    facility = db.scalar(select(Facility).where(Facility.uuid == body.facility_uuid)) if body.facility_uuid else None
    if body.facility_uuid and not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
    require_facility_access(db, user, facility.id if facility else None)
    values = body.model_dump(exclude={"patient_uuid", "facility_uuid"})
    if facility:
        values.update(facility_id=facility.id, legacy_facility_id=facility.legacy_facility_id, facility_name=facility.name)
    item = Appointment(patient_id=patient.id, **values)
    ensure_no_conflict(db, item)
    db.add(item)
    db.flush()
    notify_patient(db,patient,"appointment","Appointment update","An appointment update is available in your patient portal.","/portal#appointments")
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="appointment", resource_id=item.uuid))
    db.commit()
    db.refresh(item)
    return appointment_out(db, item, patient.uuid)


@router.get("/facilities", response_model=list[AppointmentFacilityOut])
def list_appointment_facilities(db: Session = Depends(get_db), user: User = Depends(appointment_user)):
    query = select(Facility).where(Facility.active.is_(True), Facility.service_location.is_(True))
    scope = facility_scope(db, user)
    if scope is not None: query = query.where(Facility.id.in_(scope))
    return list(db.scalars(query.order_by(Facility.name)))


@router.get("/{appointment_uuid}", response_model=AppointmentOut)
def get_appointment(
    appointment_uuid: str,
    db: Session = Depends(get_db),
    user: User = Depends(appointment_user),
) -> AppointmentOut:
    row = db.execute(select(Appointment, Patient.uuid).join(Patient).where(Appointment.uuid == appointment_uuid)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Appointment not found")
    item, patient_uuid = row
    require_appointment_access(db, user, item)
    db.add(AuditEvent(actor_id=user.id, action="read", resource_type="appointment", resource_id=item.uuid))
    db.commit()
    return appointment_out(db, item, patient_uuid)


@router.patch("/{appointment_uuid}", response_model=AppointmentOut)
def update_appointment(
    appointment_uuid: str,
    body: AppointmentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(appointment_write_user),
) -> AppointmentOut:
    row = db.execute(select(Appointment, Patient.uuid).join(Patient).where(Appointment.uuid == appointment_uuid)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Appointment not found")
    item, patient_uuid = row
    require_appointment_access(db, user, item)
    changes = body.model_dump(exclude_unset=True)
    if "facility_uuid" in changes:
        value = changes.pop("facility_uuid")
        facility = db.scalar(select(Facility).where(Facility.uuid == value)) if value else None
        if value and not facility: raise HTTPException(status_code=404, detail="Facility not found")
        require_facility_access(db, user, facility.id if facility else None)
        changes.update(facility_id=facility.id if facility else None, facility_name=facility.name if facility else None, legacy_facility_id=facility.legacy_facility_id if facility else None)
    for field, value in changes.items():
        setattr(item, field, value)
    if item.ends_at <= item.starts_at:
        raise HTTPException(status_code=422, detail="ends_at must be after starts_at")
    ensure_no_conflict(db, item, exclude_id=item.id)
    notify_patient(db,db.get(Patient,item.patient_id),"appointment","Appointment update","An appointment update is available in your patient portal.","/portal#appointments")
    db.add(AuditEvent(actor_id=user.id, action="update", resource_type="appointment", resource_id=item.uuid, detail=",".join(sorted(changes))))
    db.commit()
    db.refresh(item)
    return appointment_out(db, item, patient_uuid)


@router.delete("/{appointment_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_appointment(
    appointment_uuid: str,
    db: Session = Depends(get_db),
    user: User = Depends(appointment_write_user),
) -> Response:
    item = db.scalar(select(Appointment).where(Appointment.uuid == appointment_uuid))
    if not item:
        raise HTTPException(status_code=404, detail="Appointment not found")
    require_appointment_access(db, user, item)
    item.status = "cancelled"
    notify_patient(db,db.get(Patient,item.patient_id),"appointment","Appointment cancelled","An appointment cancellation is available in your patient portal.","/portal#appointments")
    db.add(AuditEvent(actor_id=user.id, action="cancel", resource_type="appointment", resource_id=item.uuid))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
