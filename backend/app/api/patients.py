from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent, Patient, PatientAddress, PatientConsent, PatientCustomFieldDefinition, PatientCustomFieldValue, PatientEmployment, PatientNameHistory, PatientRelatedPerson, PatientTelecom, User
from ..schemas import InactivationRequest, PatientAddressCreate, PatientAddressOut, PatientConsentCreate, PatientConsentOut, PatientCreate, PatientCustomFieldOut, PatientCustomFieldValueUpdate, PatientEmploymentCreate, PatientEmploymentOut, PatientNameHistoryCreate, PatientNameHistoryOut, PatientOut, PatientPage, PatientRelatedPersonCreate, PatientRelatedPersonOut, PatientTelecomCreate, PatientTelecomOut, PatientUpdate
from ..security import patient_demographics_user, patient_demographics_write_user
from ..services.patients import patient_by_uuid

router = APIRouter(prefix="/api/v1/patients", tags=["patients"])


def custom_field_out(definition: PatientCustomFieldDefinition, value: PatientCustomFieldValue | None) -> PatientCustomFieldOut:
    return PatientCustomFieldOut(
        uuid=definition.uuid, field_key=definition.field_key, group_key=definition.group_key,
        title=definition.title, sequence=definition.sequence, data_type=definition.data_type,
        list_id=definition.list_id, options=definition.options or [], default_value=definition.default_value,
        max_length=definition.max_length, required=definition.required, description=definition.description,
        validation=definition.validation, typed_mapping=definition.typed_mapping,
        value=value.value_text if value else definition.default_value, value_source=value.source if value else None,
        updated_at=value.updated_at if value else None,
    )


@router.get("/{patient_uuid}/custom-fields", response_model=list[PatientCustomFieldOut])
def list_custom_fields(patient_uuid: str, include_typed: bool = False, db: Session = Depends(get_db), user: User = Depends(patient_demographics_user)):
    patient = patient_by_uuid(db, patient_uuid)
    query = select(PatientCustomFieldDefinition, PatientCustomFieldValue).outerjoin(PatientCustomFieldValue, (PatientCustomFieldValue.definition_id == PatientCustomFieldDefinition.id) & (PatientCustomFieldValue.patient_id == patient.id))
    if not include_typed: query = query.where(PatientCustomFieldDefinition.typed_mapping.is_(False))
    rows = db.execute(query.order_by(PatientCustomFieldDefinition.group_key, PatientCustomFieldDefinition.sequence, PatientCustomFieldDefinition.id)).all()
    db.add(AuditEvent(actor_id=user.id, action="read", resource_type="patient_custom_fields", resource_id=patient.uuid, detail=f"records={len(rows)}; include_typed={include_typed}")); db.commit()
    return [custom_field_out(definition, value) for definition, value in rows]


@router.put("/{patient_uuid}/custom-fields/{definition_uuid}", response_model=PatientCustomFieldOut)
def update_custom_field(patient_uuid: str, definition_uuid: str, body: PatientCustomFieldValueUpdate, db: Session = Depends(get_db), user: User = Depends(patient_demographics_write_user)):
    patient = patient_by_uuid(db, patient_uuid)
    definition = db.scalar(select(PatientCustomFieldDefinition).where(PatientCustomFieldDefinition.uuid == definition_uuid))
    if not definition: raise HTTPException(status_code=404, detail="Custom field definition not found")
    value = body.value.strip() if body.value is not None else None
    value = value or None
    if definition.required and value is None: raise HTTPException(status_code=422, detail="A value is required")
    if value and definition.max_length and definition.max_length > 0 and len(value) > definition.max_length: raise HTTPException(status_code=422, detail="Value exceeds the configured maximum length")
    option_ids = {str(option.get("id")) for option in definition.options or []}
    if value and definition.data_type in {1, 43, 46} and option_ids and value not in option_ids: raise HTTPException(status_code=422, detail="Value is not in the configured option list")
    if value and definition.data_type == 4:
        try: datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError: raise HTTPException(status_code=422, detail="Value must be an ISO date or date-time")
    item = db.scalar(select(PatientCustomFieldValue).where(PatientCustomFieldValue.patient_id == patient.id, PatientCustomFieldValue.definition_id == definition.id))
    if item: item.value_text = value; item.source = "staff"; item.updated_by_id = user.id; item.updated_at = datetime.now(timezone.utc)
    else: item = PatientCustomFieldValue(patient_id=patient.id, definition_id=definition.id, value_text=value, source="staff", updated_by_id=user.id); db.add(item)
    db.flush(); db.add(AuditEvent(actor_id=user.id, action="update", resource_type="patient_custom_field", resource_id=item.uuid, detail=f"patient={patient.uuid}; field={definition.field_key}")); db.commit(); db.refresh(item)
    return custom_field_out(definition, item)


def sync_operational_consent(patient: Patient, purpose: str, permitted: bool) -> None:
    if purpose == "email": patient.allow_email = permitted
    elif purpose == "sms": patient.allow_sms = permitted
    elif purpose == "patient-portal": patient.portal_allowed = permitted


@router.get("/{patient_uuid}/consents", response_model=list[PatientConsentOut])
def list_consents(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(patient_demographics_user)):
    patient = patient_by_uuid(db, patient_uuid)
    items = list(db.scalars(select(PatientConsent).where(PatientConsent.patient_id == patient.id).order_by(PatientConsent.status, PatientConsent.created_at.desc(), PatientConsent.id.desc())))
    db.add(AuditEvent(actor_id=user.id, action="read", resource_type="patient_consent", resource_id=patient.uuid, detail=f"records={len(items)}")); db.commit()
    return items


@router.post("/{patient_uuid}/consents", response_model=PatientConsentOut, status_code=status.HTTP_201_CREATED)
def create_consent(patient_uuid: str, body: PatientConsentCreate, db: Session = Depends(get_db), user: User = Depends(patient_demographics_write_user)):
    patient = patient_by_uuid(db, patient_uuid)
    if body.purpose == "email" and body.decision == "permit" and not patient.email:
        raise HTTPException(status_code=409, detail="Patient email is required before email consent can be granted")
    if body.purpose == "sms" and body.decision == "permit" and not patient.phone:
        raise HTTPException(status_code=409, detail="Patient phone is required before SMS consent can be granted")
    now = datetime.now(timezone.utc)
    for current in db.scalars(select(PatientConsent).where(PatientConsent.patient_id == patient.id, PatientConsent.purpose == body.purpose, PatientConsent.status == "active")):
        current.status = "revoked"; current.revoked_at = now; current.revocation_reason = "Superseded by a newer decision"
    item = PatientConsent(patient_id=patient.id, recorded_by_id=user.id, source="staff", **body.model_dump())
    db.add(item); db.flush(); sync_operational_consent(patient, item.purpose, item.decision == "permit")
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="patient_consent", resource_id=item.uuid, detail=f"patient={patient.uuid}; purpose={item.purpose}; decision={item.decision}")); db.commit(); db.refresh(item)
    return item


@router.post("/{patient_uuid}/consents/{consent_uuid}/revoke", response_model=PatientConsentOut)
def revoke_consent(patient_uuid: str, consent_uuid: str, body: InactivationRequest, db: Session = Depends(get_db), user: User = Depends(patient_demographics_write_user)):
    patient = patient_by_uuid(db, patient_uuid)
    item = db.scalar(select(PatientConsent).where(PatientConsent.uuid == consent_uuid, PatientConsent.patient_id == patient.id))
    if not item: raise HTTPException(status_code=404, detail="Consent not found")
    if item.status != "active": raise HTTPException(status_code=409, detail="Consent is already revoked")
    item.status = "revoked"; item.revoked_at = datetime.now(timezone.utc); item.revocation_reason = body.reason
    sync_operational_consent(patient, item.purpose, False)
    db.add(AuditEvent(actor_id=user.id, action="revoke", resource_type="patient_consent", resource_id=item.uuid, detail=f"patient={patient.uuid}; reason={body.reason}")); db.commit(); db.refresh(item)
    return item


@router.get("/{patient_uuid}/employments", response_model=list[PatientEmploymentOut])
def list_employments(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(patient_demographics_user)):
    patient = patient_by_uuid(db, patient_uuid)
    items = list(db.scalars(select(PatientEmployment).where(PatientEmployment.patient_id == patient.id).order_by(PatientEmployment.active.desc(), PatientEmployment.starts_at.desc(), PatientEmployment.id.desc())))
    db.add(AuditEvent(actor_id=user.id, action="read", resource_type="patient_employment", resource_id=patient.uuid, detail=f"records={len(items)}")); db.commit()
    return items


@router.post("/{patient_uuid}/employments", response_model=PatientEmploymentOut, status_code=status.HTTP_201_CREATED)
def create_employment(patient_uuid: str, body: PatientEmploymentCreate, db: Session = Depends(get_db), user: User = Depends(patient_demographics_write_user)):
    patient = patient_by_uuid(db, patient_uuid)
    item = PatientEmployment(patient_id=patient.id, **body.model_dump())
    db.add(item); db.flush(); db.add(AuditEvent(actor_id=user.id, action="create", resource_type="patient_employment", resource_id=item.uuid, detail=f"patient={patient.uuid}")); db.commit(); db.refresh(item)
    return item


@router.post("/{patient_uuid}/employments/{employment_uuid}/inactivate", response_model=PatientEmploymentOut)
def inactivate_employment(patient_uuid: str, employment_uuid: str, body: InactivationRequest, db: Session = Depends(get_db), user: User = Depends(patient_demographics_write_user)):
    patient = patient_by_uuid(db, patient_uuid)
    item = db.scalar(select(PatientEmployment).where(PatientEmployment.uuid == employment_uuid, PatientEmployment.patient_id == patient.id))
    if not item: raise HTTPException(status_code=404, detail="Employment not found")
    item.active = False; item.inactivated_reason = body.reason
    if not item.ends_at: item.ends_at = datetime.now(timezone.utc)
    db.add(AuditEvent(actor_id=user.id, action="inactivate", resource_type="patient_employment", resource_id=item.uuid, detail=f"patient={patient.uuid}; reason={body.reason}")); db.commit(); db.refresh(item)
    return item


@router.get("/{patient_uuid}/name-history", response_model=list[PatientNameHistoryOut])
def list_name_history(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(patient_demographics_user)):
    patient = patient_by_uuid(db, patient_uuid)
    return list(db.scalars(select(PatientNameHistory).where(PatientNameHistory.patient_id == patient.id).order_by(PatientNameHistory.period_end.desc(), PatientNameHistory.id.desc())))


@router.post("/{patient_uuid}/name-history", response_model=PatientNameHistoryOut, status_code=status.HTTP_201_CREATED)
def create_name_history(patient_uuid: str, body: PatientNameHistoryCreate, db: Session = Depends(get_db), user: User = Depends(patient_demographics_write_user)):
    patient = patient_by_uuid(db, patient_uuid)
    item = PatientNameHistory(patient_id=patient.id, created_by_id=user.id, **body.model_dump())
    db.add(item); db.flush(); db.add(AuditEvent(actor_id=user.id, action="create", resource_type="patient_name_history", resource_id=item.uuid, detail=f"patient={patient.uuid}")); db.commit(); db.refresh(item)
    return item


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
                Patient.id.in_(select(PatientNameHistory.patient_id).where(or_(PatientNameHistory.first_name.ilike(term, escape="\\"), PatientNameHistory.last_name.ilike(term, escape="\\")))),
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
