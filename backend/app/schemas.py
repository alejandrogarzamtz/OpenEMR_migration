from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class Login(BaseModel):
    email: EmailStr
    password: str


class PatientCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    sex: str = Field(min_length=1, max_length=30)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)


class PatientOut(PatientCreate):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    legacy_pid: int | None
    created_at: datetime


class PatientPage(BaseModel):
    items: list[PatientOut]
    total: int
    limit: int
    offset: int


class AppointmentCreate(BaseModel):
    patient_uuid: str
    starts_at: datetime
    ends_at: datetime
    reason: str | None = Field(default=None, max_length=255)
    provider_name: str | None = Field(default=None, max_length=150)


class AppointmentOut(AppointmentCreate):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    status: str


class EncounterCreate(BaseModel):
    patient_uuid: str
    appointment_uuid: str | None = None
    occurred_at: datetime
    type: str = Field(default="ambulatory", max_length=50)
    chief_complaint: str | None = None
    clinical_note: str | None = None


class EncounterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    patient_uuid: str
    appointment_uuid: str | None = None
    occurred_at: datetime
    type: str
    status: str
    chief_complaint: str | None
    clinical_note: str | None


class ClinicalItemCreate(BaseModel):
    category: str = Field(pattern="^(problem|allergy|medication)$")
    title: str = Field(min_length=1, max_length=255)
    code_system: str | None = Field(default=None, max_length=30)
    code: str | None = Field(default=None, max_length=50)
    status: str = Field(default="active", pattern="^(active|inactive|resolved|entered-in-error)$")
    onset_date: date | None = None
    end_date: date | None = None
    severity: str | None = Field(default=None, max_length=30)
    reaction: str | None = Field(default=None, max_length=255)
    dosage: str | None = Field(default=None, max_length=255)
    note: str | None = None


class ClinicalItemOut(ClinicalItemCreate):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    created_at: datetime


class ClinicalSummary(BaseModel):
    patient: PatientOut
    problems: list[ClinicalItemOut]
    allergies: list[ClinicalItemOut]
    medications: list[ClinicalItemOut]
    encounters: list[EncounterOut]


class LabOrderCreate(BaseModel):
    encounter_uuid: str | None = None
    ordered_at: datetime
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    priority: str = Field(default="routine", pattern="^(routine|urgent|stat)$")
    instructions: str | None = None


class LabOrderOut(LabOrderCreate):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    status: str


class LabResultCreate(BaseModel):
    observed_at: datetime
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    value: str = Field(min_length=1, max_length=255)
    unit: str | None = Field(default=None, max_length=31)
    reference_range: str | None = Field(default=None, max_length=255)
    interpretation: str | None = Field(default=None, max_length=31)
    status: str = Field(default="final", pattern="^(preliminary|final|corrected|cancelled)$")


class LabResultOut(LabResultCreate):
    model_config = ConfigDict(from_attributes=True)
    uuid: str


class LabOrderDetail(LabOrderOut):
    results: list[LabResultOut]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    name: str
    mime_type: str
    sha256: str
    uploaded_at: datetime


class CoverageCreate(BaseModel):
    payer_name: str = Field(min_length=1, max_length=255)
    payer_identifier: str | None = Field(default=None, max_length=25)
    priority: str = Field(default="primary", pattern="^(primary|secondary|tertiary)$")
    plan_name: str | None = Field(default=None, max_length=255)
    policy_number: str = Field(min_length=1, max_length=255)
    group_number: str | None = Field(default=None, max_length=255)
    subscriber_name: str = Field(min_length=1, max_length=255)
    relationship: str = Field(default="self", max_length=50)
    starts_on: date | None = None
    ends_on: date | None = None


class CoverageOut(CoverageCreate):
    uuid: str


class ChargeCreate(BaseModel):
    encounter_uuid: str
    code_system: str = Field(max_length=15)
    code: str = Field(max_length=20)
    description: str = Field(max_length=255)
    units: int = Field(default=1, ge=1, le=999)
    unit_price: Decimal = Field(gt=0, decimal_places=2)


class ChargeOut(ChargeCreate):
    uuid: str


class ClaimCreate(BaseModel):
    encounter_uuid: str
    coverage_uuid: str | None = None
    charge_uuids: list[str] = Field(min_length=1)


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, decimal_places=2)
    method: str = Field(min_length=1, max_length=50)
    reference: str | None = Field(default=None, max_length=255)


class PaymentOut(PaymentCreate):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    posted_at: datetime


class ClaimOut(BaseModel):
    uuid: str
    encounter_uuid: str
    coverage_uuid: str | None
    status: str
    total: Decimal
    paid: Decimal
    balance: Decimal
    charges: list[ChargeOut]
    payments: list[PaymentOut]
    created_at: datetime


class ImmunizationCreate(BaseModel):
    encounter_uuid: str | None = None
    administered_at: datetime
    cvx_code: str = Field(min_length=1, max_length=64)
    vaccine_name: str = Field(min_length=1, max_length=255)
    manufacturer: str | None = Field(default=None, max_length=100)
    lot_number: str | None = Field(default=None, max_length=50)
    route: str | None = Field(default=None, max_length=100)
    site: str | None = Field(default=None, max_length=100)
    dose: str | None = Field(default=None, max_length=50)
    status: str = Field(default="completed", pattern="^(completed|not-done|entered-in-error)$")
    refusal_reason: str | None = Field(default=None, max_length=255)
    note: str | None = None


class ImmunizationOut(ImmunizationCreate):
    uuid: str


class VitalSetCreate(BaseModel):
    encounter_uuid: str | None = None
    observed_at: datetime
    systolic: Decimal | None = Field(default=None, gt=0)
    diastolic: Decimal | None = Field(default=None, gt=0)
    weight_kg: Decimal | None = Field(default=None, gt=0)
    height_cm: Decimal | None = Field(default=None, gt=0)
    temperature_c: Decimal | None = Field(default=None, gt=20, lt=50)
    heart_rate: Decimal | None = Field(default=None, gt=0)
    respiratory_rate: Decimal | None = Field(default=None, gt=0)
    oxygen_saturation: Decimal | None = Field(default=None, ge=0, le=100)
    note: str | None = Field(default=None, max_length=255)


class VitalSetOut(VitalSetCreate):
    uuid: str
    bmi: Decimal | None


class PrescriptionCreate(BaseModel):
    encounter_uuid: str | None = None
    pharmacy_uuid: str | None = None
    prescribed_at: datetime
    start_date: date | None = None
    end_date: date | None = None
    drug_name: str = Field(min_length=1, max_length=150)
    rxnorm_code: str | None = Field(default=None, max_length=25)
    dosage_instructions: str = Field(min_length=1)
    quantity: str | None = Field(default=None, max_length=31)
    refills: int = Field(default=0, ge=0, le=99)
    substitutions_allowed: bool = True
    indication: str | None = None


class PrescriptionOut(PrescriptionCreate):
    uuid: str
    status: str


class ClinicalFormCreate(BaseModel):
    encounter_uuid: str
    form_type: str = Field(pattern="^(soap|ros|physical_exam|clinic_note|custom)$")
    title: str = Field(min_length=1, max_length=255)
    content: dict


class ClinicalFormOut(ClinicalFormCreate):
    uuid: str
    status: str
    authored_at: datetime
    signed_at: datetime | None
