from datetime import date, datetime, timezone
from uuid import uuid4
from decimal import Decimal
from sqlalchemy import JSON, Date, DateTime, ForeignKey, LargeBinary, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_user_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), default="clinician")
    active: Mapped[bool] = mapped_column(default=True)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list)


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_pid: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    first_name: Mapped[str] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str] = mapped_column(String(100), index=True)
    preferred_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    suffix: Mapped[str | None] = mapped_column(String(50), nullable=True)
    date_of_birth: Mapped[date] = mapped_column(Date, index=True)
    sex: Mapped[str] = mapped_column(String(30))
    gender_identity: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sexual_orientation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pronouns: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language: Mapped[str | None] = mapped_column(String(100), nullable=True)
    race: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ethnicity: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address_line_1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    portal_allowed: Mapped[bool] = mapped_column(default=False)
    allow_email: Mapped[bool] = mapped_column(default=False)
    allow_sms: Mapped[bool] = mapped_column(default=False)
    deceased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deceased_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"), nullable=True, index=True)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    merged_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    merge_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PatientMerge(Base):
    __tablename__ = "patient_merges"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    source_patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), unique=True, index=True)
    target_patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    source_uuid: Mapped[str] = mapped_column(String(36), index=True)
    target_uuid: Mapped[str] = mapped_column(String(36), index=True)
    reason: Mapped[str] = mapped_column(String(500))
    duplicate_score: Mapped[int] = mapped_column(default=0)
    matched_fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    moved_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    resolved_conflicts: Mapped[list] = mapped_column(JSON, default=list)
    merged_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class PatientAddress(Base):
    __tablename__ = "patient_addresses"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    use: Mapped[str] = mapped_column(String(30), default="home")
    type: Mapped[str] = mapped_column(String(30), default="both")
    line1: Mapped[str] = mapped_column(String(255))
    line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    district: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[int] = mapped_column(default=1)
    active: Mapped[bool] = mapped_column(default=True)
    is_primary: Mapped[bool] = mapped_column(default=False)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    inactivated_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PatientTelecom(Base):
    __tablename__ = "patient_telecoms"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    system: Mapped[str] = mapped_column(String(30))
    use: Mapped[str] = mapped_column(String(30), default="home")
    value: Mapped[str] = mapped_column(String(255))
    rank: Mapped[int] = mapped_column(default=1)
    active: Mapped[bool] = mapped_column(default=True)
    is_primary: Mapped[bool] = mapped_column(default=False)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    inactivated_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PatientRelatedPerson(Base):
    __tablename__ = "patient_related_persons"
    __table_args__ = (UniqueConstraint("patient_id", "legacy_source", name="uq_patient_related_person_legacy_source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str] = mapped_column(String(100))
    relationship_code: Mapped[str] = mapped_column(String(63), index=True)
    role_code: Mapped[str] = mapped_column(String(63), index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sex: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[int] = mapped_column(default=1)
    active: Mapped[bool] = mapped_column(default=True)
    is_primary_contact: Mapped[bool] = mapped_column(default=False)
    is_emergency_contact: Mapped[bool] = mapped_column(default=False)
    can_make_medical_decisions: Mapped[bool] = mapped_column(default=False)
    can_receive_medical_info: Mapped[bool] = mapped_column(default=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    legacy_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PatientNameHistory(Base):
    __tablename__ = "patient_name_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    prefix: Mapped[str | None] = mapped_column(String(50), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str] = mapped_column(String(100), index=True)
    suffix: Mapped[str | None] = mapped_column(String(50), nullable=True)
    use: Mapped[str] = mapped_column(String(30), default="old")
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PatientEmployment(Base):
    __tablename__ = "patient_employments"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_employer_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    employer_name: Mapped[str] = mapped_column(String(255))
    occupation_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(default=True)
    inactivated_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PatientConsent(Base):
    __tablename__ = "patient_consents"
    __table_args__ = (UniqueConstraint("patient_id", "legacy_field", name="uq_patient_consent_legacy_field"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(50), index=True)
    decision: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="staff")
    legacy_field: Mapped[str | None] = mapped_column(String(100), nullable=True)
    legacy_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PatientCustomFieldDefinition(Base):
    __tablename__ = "patient_custom_field_definitions"
    __table_args__ = (UniqueConstraint("legacy_form_id", "field_key", "sequence", name="uq_patient_custom_field_layout"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_form_id: Mapped[str] = mapped_column(String(31), default="DEM")
    field_key: Mapped[str] = mapped_column(String(100), index=True)
    group_key: Mapped[str | None] = mapped_column(String(31), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    sequence: Mapped[int] = mapped_column(default=0)
    data_type: Mapped[int] = mapped_column(default=2)
    list_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    options: Mapped[list[dict]] = mapped_column(JSON, default=list)
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_length: Mapped[int | None] = mapped_column(nullable=True)
    required: Mapped[bool] = mapped_column(default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    codes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    typed_mapping: Mapped[bool] = mapped_column(default=False)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PatientCustomFieldValue(Base):
    __tablename__ = "patient_custom_field_values"
    __table_args__ = (UniqueConstraint("patient_id", "definition_id", name="uq_patient_custom_field_value"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    definition_id: Mapped[int] = mapped_column(ForeignKey("patient_custom_field_definitions.id"), index=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="staff")
    legacy_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(50))
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class IdentityAuditEvent(Base):
    """Audit trail for both workforce and patient-portal identities."""

    __tablename__ = "identity_audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    identity_kind: Mapped[str] = mapped_column(String(20), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    portal_account_id: Mapped[int | None] = mapped_column(ForeignKey("portal_accounts.id"), nullable=True, index=True)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(50))
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class Facility(Base):
    __tablename__ = "facilities"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_facility_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    fax: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    npi: Mapped[str | None] = mapped_column(String(15), nullable=True)
    taxonomy: Mapped[str | None] = mapped_column(String(15), nullable=True)
    service_location: Mapped[bool] = mapped_column(default=True)
    billing_location: Mapped[bool] = mapped_column(default=True)
    accepts_assignment: Mapped[bool] = mapped_column(default=True)
    active: Mapped[bool] = mapped_column(default=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Warehouse(Base):
    __tablename__ = "warehouses"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_option_id: Mapped[str | None] = mapped_column(String(31), unique=True, nullable=True)
    code: Mapped[str] = mapped_column(String(31), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("facilities.id"), nullable=True, index=True)
    sequence: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool] = mapped_column(default=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Practitioner(Base):
    __tablename__ = "practitioners"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_user_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(255))
    middle_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(30), nullable=True)
    specialty: Mapped[str | None] = mapped_column(String(255), nullable=True)
    npi: Mapped[str | None] = mapped_column(String(15), nullable=True, index=True)
    taxonomy: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    primary_facility_id: Mapped[int | None] = mapped_column(ForeignKey("facilities.id"), nullable=True)
    calendar_enabled: Mapped[bool] = mapped_column(default=False)
    active: Mapped[bool] = mapped_column(default=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class UserFacilityAccess(Base):
    __tablename__ = "user_facility_access"
    __table_args__ = (UniqueConstraint("user_id", "facility_id", "warehouse_id", name="uq_user_facility_warehouse"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), index=True)
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"), nullable=True, index=True)


class PractitionerFacilityAccess(Base):
    __tablename__ = "practitioner_facility_access"
    __table_args__ = (UniqueConstraint("practitioner_id", "facility_id", "warehouse_code", name="uq_practitioner_facility_warehouse"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    practitioner_id: Mapped[int] = mapped_column(ForeignKey("practitioners.id"), index=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), index=True)
    warehouse_code: Mapped[str] = mapped_column(String(31), default="")


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_event_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    legacy_provider_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    legacy_facility_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("facilities.id"), nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(nullable=True)
    title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="scheduled")
    legacy_status: Mapped[str | None] = mapped_column(String(15), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    facility_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    room: Mapped[str | None] = mapped_column(String(20), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str | None] = mapped_column(String(30), nullable=True)
    all_day: Mapped[bool] = mapped_column(default=False)
    recurrence_rule: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recurrence_group: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    send_sms: Mapped[bool] = mapped_column(default=False)
    send_email: Mapped[bool] = mapped_column(default=False)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PatientFlowEpisode(Base):
    __tablename__ = "patient_flow_episodes"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_tracker_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"), nullable=True, index=True)
    encounter_id: Mapped[int | None] = mapped_column(ForeignKey("encounters.id"), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    random_drug_test: Mapped[bool | None] = mapped_column(nullable=True)
    drug_screen_completed: Mapped[bool] = mapped_column(default=False)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PatientFlowEvent(Base):
    __tablename__ = "patient_flow_events"
    __table_args__ = (UniqueConstraint("episode_id", "sequence", name="uq_patient_flow_event_sequence"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("patient_flow_episodes.id"), index=True)
    sequence: Mapped[int] = mapped_column()
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(30))
    legacy_status: Mapped[str | None] = mapped_column(String(31), nullable=True)
    room: Mapped[str | None] = mapped_column(String(20), nullable=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class InventoryProduct(Base):
    __tablename__ = "inventory_products"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_drug_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    ndc_number: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    drug_code: Mapped[str | None] = mapped_column(String(25), nullable=True)
    form: Mapped[str | None] = mapped_column(String(31), nullable=True)
    size: Mapped[str | None] = mapped_column(String(25), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(31), nullable=True)
    route: Mapped[str | None] = mapped_column(String(31), nullable=True)
    reorder_point: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    max_level: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    allow_combining: Mapped[bool] = mapped_column(default=False)
    allow_multiple: Mapped[bool] = mapped_column(default=True)
    consumable: Mapped[bool] = mapped_column(default=False)
    dispensable: Mapped[bool] = mapped_column(default=True)
    active: Mapped[bool] = mapped_column(default=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class InventoryLot(Base):
    __tablename__ = "inventory_lots"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_inventory_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("inventory_products.id"), index=True)
    lot_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    expiration: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    warehouse_id: Mapped[str] = mapped_column(String(31), default="", index=True)
    vendor_id: Mapped[int | None] = mapped_column(nullable=True)
    on_hand: Mapped[int] = mapped_column(default=0)
    destroyed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    destruction_method: Mapped[str | None] = mapped_column(String(255), nullable=True)
    destruction_witness: Mapped[str | None] = mapped_column(String(255), nullable=True)
    destruction_notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_sale_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("inventory_products.id"), index=True)
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_lots.id"), nullable=True, index=True)
    destination_lot_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_lots.id"), nullable=True)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"), nullable=True, index=True)
    encounter_id: Mapped[int | None] = mapped_column(ForeignKey("encounters.id"), nullable=True)
    prescription_id: Mapped[int | None] = mapped_column(ForeignKey("prescriptions.id"), nullable=True)
    transaction_type: Mapped[str] = mapped_column(String(20), index=True)
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[int] = mapped_column()
    fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    billed: Mapped[bool] = mapped_column(default=False)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ReportRun(Base):
    __tablename__ = "report_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    report_key: Mapped[str] = mapped_column(String(100), index=True)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    columns: Mapped[list] = mapped_column(JSON, default=list)
    rows: Mapped[list] = mapped_column(JSON, default=list)
    totals: Mapped[dict] = mapped_column(JSON, default=dict)
    row_count: Mapped[int] = mapped_column(default=0)
    checksum: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class PortalAccount(Base):
    __tablename__ = "portal_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_access_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"), unique=True, nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    identity_type: Mapped[str] = mapped_column(String(30), default="patient", index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(default=True)
    force_password_reset: Mapped[bool] = mapped_column(default=True)
    failed_attempts: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PortalAccessGrant(Base):
    __tablename__ = "portal_access_grants"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    grantee_portal_account_id: Mapped[int] = mapped_column(ForeignKey("portal_accounts.id"), index=True)
    relationship_code: Mapped[str] = mapped_column(String(50))
    scopes: Mapped[list[str]] = mapped_column(JSON)
    consent_basis: Mapped[str] = mapped_column(String(50))
    evidence_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    granted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    revoked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    identity_kind: Mapped[str] = mapped_column(String(20), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    portal_account_id: Mapped[int | None] = mapped_column(ForeignKey("portal_accounts.id"), nullable=True, index=True)
    access_jti: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    previous_refresh_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    refresh_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PortalPasswordResetToken(Base):
    __tablename__ = "portal_password_reset_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    portal_account_id: Mapped[int] = mapped_column(ForeignKey("portal_accounts.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MfaRegistration(Base):
    __tablename__ = "mfa_registrations"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    method: Mapped[str] = mapped_column(String(20), default="totp")
    encrypted_secret: Mapped[bytes] = mapped_column(LargeBinary)
    recovery_code_hashes: Mapped[list[str]] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(default=False, index=True)
    last_used_step: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MfaChallenge(Base):
    __tablename__ = "mfa_challenges"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PortalMfaRegistration(Base):
    __tablename__ = "portal_mfa_registrations"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    portal_account_id: Mapped[int] = mapped_column(ForeignKey("portal_accounts.id"), unique=True, index=True)
    method: Mapped[str] = mapped_column(String(20), default="totp")
    encrypted_secret: Mapped[bytes] = mapped_column(LargeBinary)
    recovery_code_hashes: Mapped[list[str]] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(default=False, index=True)
    last_used_step: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PortalMfaChallenge(Base):
    __tablename__ = "portal_mfa_challenges"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    portal_account_id: Mapped[int] = mapped_column(ForeignKey("portal_accounts.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)



class MessageThread(Base):
    __tablename__ = "message_threads"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_thread_key: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class SecureMessage(Base):
    __tablename__ = "secure_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_message_key: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("message_threads.id"), index=True)
    sender_kind: Mapped[str] = mapped_column(String(20))
    sender_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    sender_portal_account_id: Mapped[int | None] = mapped_column(ForeignKey("portal_accounts.id"), nullable=True)
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    read_by_patient_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_by_staff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ClinicalTask(Base):
    __tablename__ = "clinical_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_task_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[int | None] = mapped_column(ForeignKey("encounters.id"), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    method: Mapped[str] = mapped_column(String(30))
    comment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class CommunicationDelivery(Base):
    __tablename__ = "communication_deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_email_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"), nullable=True, index=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("secure_messages.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(20), index=True)
    recipient: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    template_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(default=0)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Encounter(Base):
    __tablename__ = "encounters"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_encounter_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    type: Mapped[str] = mapped_column(String(50), default="ambulatory")
    status: Mapped[str] = mapped_column(String(30), default="open")
    chief_complaint: Mapped[str | None] = mapped_column(Text, nullable=True)
    clinical_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ClinicalItem(Base):
    """Normalized replacement for OpenEMR's polymorphic `lists` records."""

    __tablename__ = "clinical_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_list_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(255))
    code_system: Mapped[str | None] = mapped_column(String(30), nullable=True)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    onset_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reaction: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dosage: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LabOrder(Base):
    __tablename__ = "lab_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_order_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[int | None] = mapped_column(ForeignKey("encounters.id"), nullable=True)
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    priority: Mapped[str] = mapped_column(String(31), default="routine")
    status: Mapped[str] = mapped_column(String(31), default="pending")
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)


class LabResult(Base):
    __tablename__ = "lab_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_result_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("lab_orders.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    value: Mapped[str] = mapped_column(String(255))
    unit: Mapped[str | None] = mapped_column(String(31), nullable=True)
    reference_range: Mapped[str | None] = mapped_column(String(255), nullable=True)
    interpretation: Mapped[str | None] = mapped_column(String(31), nullable=True)
    status: Mapped[str] = mapped_column(String(31), default="final")
    released_to_patient_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    released_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_document_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[int | None] = mapped_column(ForeignKey("encounters.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    released_to_patient_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    released_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class PatientPhoto(Base):
    __tablename__ = "patient_photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_document_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(30))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column()
    is_primary: Mapped[bool] = mapped_column(default=True, index=True)
    active: Mapped[bool] = mapped_column(default=True, index=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    inactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    inactivated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    inactivated_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Payer(Base):
    __tablename__ = "payers"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_payer_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    payer_identifier: Mapped[str | None] = mapped_column(String(25), nullable=True)
    active: Mapped[bool] = mapped_column(default=True)


class Coverage(Base):
    __tablename__ = "coverages"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_insurance_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    payer_id: Mapped[int] = mapped_column(ForeignKey("payers.id"))
    priority: Mapped[str] = mapped_column(String(20), default="primary")
    plan_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    policy_number: Mapped[str] = mapped_column(String(255))
    group_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subscriber_name: Mapped[str] = mapped_column(String(255))
    relationship: Mapped[str] = mapped_column(String(50), default="self")
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_claim_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters.id"), index=True)
    coverage_id: Mapped[int | None] = mapped_column(ForeignKey("coverages.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    released_to_patient_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    released_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Charge(Base):
    __tablename__ = "charges"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_billing_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters.id"), index=True)
    claim_id: Mapped[int | None] = mapped_column(ForeignKey("claims.id"), nullable=True, index=True)
    code_system: Mapped[str] = mapped_column(String(15))
    code: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(String(255))
    units: Mapped[int] = mapped_column(default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class ClaimPayment(Base):
    __tablename__ = "claim_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()))
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(String(50))
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PaymentIntent(Base):
    __tablename__ = "payment_intents"
    __table_args__ = (UniqueConstraint("portal_account_id", "idempotency_key", name="uq_payment_intent_portal_idempotency"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    portal_account_id: Mapped[int] = mapped_column(ForeignKey("portal_accounts.id"), index=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    claim_payment_id: Mapped[int | None] = mapped_column(ForeignKey("claim_payments.id"), nullable=True, unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    provider: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), index=True)
    processor_reference: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Immunization(Base):
    __tablename__ = "immunizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_immunization_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[int | None] = mapped_column(ForeignKey("encounters.id"), nullable=True)
    administered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cvx_code: Mapped[str] = mapped_column(String(64))
    vaccine_name: Mapped[str] = mapped_column(String(255))
    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lot_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    route: Mapped[str | None] = mapped_column(String(100), nullable=True)
    site: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dose: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="completed")
    refusal_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class VitalSet(Base):
    __tablename__ = "vital_sets"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_vitals_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[int | None] = mapped_column(ForeignKey("encounters.id"), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    systolic: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    diastolic: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    heart_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    respiratory_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    oxygen_saturation: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    bmi: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Pharmacy(Base):
    __tablename__ = "pharmacies"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()))
    legacy_pharmacy_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    ncpdp: Mapped[str | None] = mapped_column(String(20), nullable=True)
    npi: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Prescription(Base):
    __tablename__ = "prescriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_prescription_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[int | None] = mapped_column(ForeignKey("encounters.id"), nullable=True)
    pharmacy_id: Mapped[int | None] = mapped_column(ForeignKey("pharmacies.id"), nullable=True)
    prescribed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    drug_name: Mapped[str] = mapped_column(String(150))
    rxnorm_code: Mapped[str | None] = mapped_column(String(25), nullable=True)
    dosage_instructions: Mapped[str] = mapped_column(Text)
    quantity: Mapped[str | None] = mapped_column(String(31), nullable=True)
    refills: Mapped[int] = mapped_column(default=0)
    substitutions_allowed: Mapped[bool] = mapped_column(default=True)
    indication: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")


class ClinicalForm(Base):
    """Versionable encounter form that preserves both standard and custom OpenEMR data."""

    __tablename__ = "clinical_forms"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_form_key: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters.id"), index=True)
    form_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    authored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    released_to_patient_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    released_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ClinicalFormDocumentLink(Base):
    __tablename__ = "clinical_form_document_links"
    __table_args__ = (UniqueConstraint("clinical_form_id", "document_id", "legacy_clinical_note_id", name="uq_clinical_form_document"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    legacy_link_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    legacy_clinical_note_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    clinical_form_id: Mapped[int] = mapped_column(ForeignKey("clinical_forms.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ClinicalFormResultLink(Base):
    __tablename__ = "clinical_form_result_links"
    __table_args__ = (UniqueConstraint("clinical_form_id", "lab_result_id", "legacy_clinical_note_id", name="uq_clinical_form_result"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    legacy_link_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    legacy_clinical_note_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    clinical_form_id: Mapped[int] = mapped_column(ForeignKey("clinical_forms.id"), index=True)
    lab_result_id: Mapped[int] = mapped_column(ForeignKey("lab_results.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)


class CarePlan(Base):
    """Longitudinal coded care-plan entry, independent from its legacy form container."""

    __tablename__ = "care_plans"
    __table_args__ = (UniqueConstraint("legacy_form_id", "legacy_row_key", name="uq_care_plan_legacy_row"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_form_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    legacy_row_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters.id"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    code: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    code_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    plan_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    note_related_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(31), nullable=True)
    reason_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason_status: Mapped[str | None] = mapped_column(String(31), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    target_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    engagement_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    active: Mapped[bool] = mapped_column(default=True, index=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class CarePlanOutcome(Base):
    """Append-only progress or outcome evidence for a goal/intervention."""

    __tablename__ = "care_plan_outcomes"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    care_plan_id: Mapped[int] = mapped_column(ForeignKey("care_plans.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(20), index=True)
    plan_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    achievement_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    measure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    measure_system: Mapped[str | None] = mapped_column(String(255), nullable=True)
    measure_display: Mapped[str | None] = mapped_column(String(255), nullable=True)
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    value_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    recorded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="staff")
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CareTeam(Base):
    __tablename__ = "care_teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_care_team_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    inactivated_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class CareTeamMember(Base):
    __tablename__ = "care_team_members"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_member_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    care_team_id: Mapped[int] = mapped_column(ForeignKey("care_teams.id"), index=True)
    practitioner_id: Mapped[int | None] = mapped_column(ForeignKey("practitioners.id"), nullable=True, index=True)
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("facilities.id"), nullable=True, index=True)
    legacy_user_id: Mapped[int | None] = mapped_column(nullable=True)
    legacy_facility_id: Mapped[int | None] = mapped_column(nullable=True)
    legacy_contact_id: Mapped[int | None] = mapped_column(nullable=True)
    member_type: Mapped[str] = mapped_column(String(20), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), index=True)
    provider_since: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    inactivated_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PreferenceValueSet(Base):
    __tablename__ = "preference_value_sets"
    __table_args__ = (UniqueConstraint("observation_code", "answer_code", "answer_system", name="uq_preference_value_answer"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    legacy_value_set_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    observation_code: Mapped[str] = mapped_column(String(50), index=True)
    answer_code: Mapped[str] = mapped_column(String(100))
    answer_system: Mapped[str] = mapped_column(String(255))
    answer_display: Mapped[str] = mapped_column(String(255))
    answer_definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool] = mapped_column(default=True, index=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PatientPreference(Base):
    __tablename__ = "patient_preferences"
    __table_args__ = (UniqueConstraint("category", "legacy_preference_id", name="uq_patient_preference_legacy"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    legacy_preference_id: Mapped[int | None] = mapped_column(nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("patient_preferences.id"), nullable=True, index=True)
    observation_code: Mapped[str] = mapped_column(String(50), index=True)
    observation_code_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    value_type: Mapped[str] = mapped_column(String(16), index=True)
    value_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    value_code_system: Mapped[str | None] = mapped_column(String(255), nullable=True)
    value_display: Mapped[str | None] = mapped_column(String(255), nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(nullable=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default="final", index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    amendment_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(default=True, index=True)
    inactivated_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recorded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ClinicalSignature(Base):
    """Append-only evidence for a form signature or amendment."""

    __tablename__ = "clinical_signatures"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_signature_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    target_type: Mapped[str] = mapped_column(String(20), default="form", index=True)
    form_id: Mapped[int | None] = mapped_column(ForeignKey("clinical_forms.id"), nullable=True, index=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters.id"), index=True)
    signer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    signer_name: Mapped[str] = mapped_column(String(255))
    signer_role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    auth_method: Mapped[str] = mapped_column(String(30), default="password")
    is_lock: Mapped[bool] = mapped_column(default=True, index=True)
    attestation: Mapped[str] = mapped_column(Text)
    amendment: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    previous_signature_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signature_hash: Mapped[str] = mapped_column(String(64), unique=True)
    legacy_content_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    legacy_signature_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    legacy_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class QuestionnaireDefinition(Base):
    __tablename__ = "questionnaire_definitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    code: Mapped[str] = mapped_column(String(50), index=True)
    version: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(255))
    questions: Mapped[list] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(default=True)


class QuestionnaireResponse(Base):
    __tablename__ = "questionnaire_responses"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[int | None] = mapped_column(ForeignKey("encounters.id"), nullable=True)
    questionnaire_id: Mapped[int] = mapped_column(ForeignKey("questionnaire_definitions.id"), index=True)
    answers: Mapped[dict] = mapped_column(JSON)
    score: Mapped[int] = mapped_column()
    interpretation: Mapped[str] = mapped_column(String(100))
    authored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
