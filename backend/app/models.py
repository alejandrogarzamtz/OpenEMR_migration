from datetime import date, datetime, timezone
from uuid import uuid4
from decimal import Decimal
from sqlalchemy import JSON, Date, DateTime, ForeignKey, LargeBinary, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), default="clinician")


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_pid: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), index=True)
    date_of_birth: Mapped[date] = mapped_column(Date)
    sex: Mapped[str] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(50))
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    legacy_event_id: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="scheduled")
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(150), nullable=True)


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
