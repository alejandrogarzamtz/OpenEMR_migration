from datetime import date, datetime
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
