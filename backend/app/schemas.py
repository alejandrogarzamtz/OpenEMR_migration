from datetime import date, datetime
from decimal import Decimal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginResult(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"
    mfa_required: bool = False
    challenge_token: str | None = None


class MfaChallengeComplete(BaseModel):
    challenge_token: str = Field(min_length=32, max_length=255)
    code: str = Field(min_length=6, max_length=32)


class MfaEnrollmentStart(BaseModel):
    password: str = Field(min_length=1, max_length=255)


class MfaEnrollmentOut(BaseModel):
    secret: str
    provisioning_uri: str


class MfaCode(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class MfaRecoveryCodesOut(BaseModel):
    recovery_codes: list[str]


class MfaDisable(BaseModel):
    password: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=6, max_length=32)


class MfaStatusOut(BaseModel):
    enabled: bool
    method: str | None = None
    confirmed_at: datetime | None = None
    recovery_codes_remaining: int = 0


class Login(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=255)
    new_password: str = Field(min_length=12, max_length=255)


class PatientBase(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    preferred_name: str | None = Field(default=None, max_length=100)
    suffix: str | None = Field(default=None, max_length=50)
    date_of_birth: date
    sex: str = Field(min_length=1, max_length=30)
    gender_identity: str | None = Field(default=None, max_length=100)
    sexual_orientation: str | None = Field(default=None, max_length=100)
    pronouns: str | None = Field(default=None, max_length=100)
    language: str | None = Field(default=None, max_length=100)
    race: str | None = Field(default=None, max_length=100)
    ethnicity: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address_line_1: str | None = Field(default=None, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=30)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    portal_allowed: bool = False
    allow_email: bool = False
    allow_sms: bool = False


class PatientCreate(PatientBase):
    duplicate_override_reason: str | None = Field(default=None, min_length=10, max_length=500)

    @model_validator(mode="after")
    def validate_demographics(self):
        if self.date_of_birth > date.today():
            raise ValueError("date_of_birth cannot be in the future")
        if self.allow_email and not self.email:
            raise ValueError("email is required when allow_email is enabled")
        if self.allow_sms and not self.phone:
            raise ValueError("phone is required when allow_sms is enabled")
        if self.country_code:
            self.country_code = self.country_code.upper()
        return self


class PatientUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    preferred_name: str | None = Field(default=None, max_length=100)
    suffix: str | None = Field(default=None, max_length=50)
    sex: str | None = Field(default=None, min_length=1, max_length=30)
    gender_identity: str | None = Field(default=None, max_length=100)
    sexual_orientation: str | None = Field(default=None, max_length=100)
    pronouns: str | None = Field(default=None, max_length=100)
    language: str | None = Field(default=None, max_length=100)
    race: str | None = Field(default=None, max_length=100)
    ethnicity: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address_line_1: str | None = Field(default=None, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=30)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    portal_allowed: bool | None = None
    allow_email: bool | None = None
    allow_sms: bool | None = None


class PatientOut(PatientBase):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    legacy_pid: int | None
    created_at: datetime


class PatientPage(BaseModel):
    items: list[PatientOut]
    total: int
    limit: int
    offset: int


class ChartLocationEventCreate(BaseModel):
    destination_type: str = Field(pattern="^(location|user|returned)$")
    location: str | None = Field(default=None, max_length=255)
    custodian_user_uuid: str | None = Field(default=None, min_length=36, max_length=36)
    custodian_name: str | None = Field(default=None, max_length=255)
    occurred_at: datetime | None = None
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_destination(self):
        if self.occurred_at and self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        if self.destination_type == "location" and not self.location:
            raise ValueError("location is required for a location destination")
        if self.destination_type == "user" and not (self.custodian_user_uuid or self.custodian_name):
            raise ValueError("custodian_user_uuid or custodian_name is required for a user destination")
        if self.destination_type == "returned" and (self.location or self.custodian_user_uuid or self.custodian_name):
            raise ValueError("returned destinations cannot specify a location or custodian")
        return self


class ChartLocationEventOut(BaseModel):
    uuid: str
    patient_uuid: str
    destination_type: str
    location: str | None
    custodian_user_uuid: str | None
    custodian_name: str | None
    occurred_at: datetime
    note: str | None


class ReferralCreate(BaseModel):
    encounter_uuid: str | None = Field(default=None,min_length=36,max_length=36)
    facility_uuid: str | None = Field(default=None,min_length=36,max_length=36)
    recipient_practitioner_uuid: str | None = Field(default=None,min_length=36,max_length=36)
    recipient_name: str = Field(min_length=1,max_length=255)
    recipient_organization: str | None = Field(default=None,max_length=255)
    referred_at: datetime
    reason: str = Field(min_length=1,max_length=10000)

    @field_validator("referred_at")
    @classmethod
    def referral_timezone(cls,value):
        if value.tzinfo is None:raise ValueError("referred_at must include a timezone")
        return value


class ReferralReply(BaseModel):
    replied_at: datetime
    reply: str = Field(min_length=1,max_length=20000)

    @field_validator("replied_at")
    @classmethod
    def reply_timezone(cls,value):
        if value.tzinfo is None:raise ValueError("replied_at must include a timezone")
        return value


class ReferralOut(BaseModel):
    uuid: str;patient_uuid: str
    encounter_uuid: str | None;facility_uuid: str | None
    recipient_practitioner_uuid: str | None
    recipient_name: str;recipient_organization: str | None
    referred_at: datetime;reason: str;status: str
    replied_at: datetime | None;reply: str | None


class ExternalEncounterOut(BaseModel):
    uuid: str
    occurred_on: date
    diagnosis: str | None
    provider_name: str | None
    facility_name: str | None
    external_id: str | None


class ExternalProcedureOut(BaseModel):
    uuid: str
    occurred_on: date
    code_system: str | None
    code: str | None
    code_text: str | None
    facility_name: str | None
    external_id: str | None


class ExternalClinicalDataOut(BaseModel):
    encounters: list[ExternalEncounterOut]
    procedures: list[ExternalProcedureOut]


class PatientDuplicateCandidate(BaseModel):
    patient: PatientOut
    score: int = Field(ge=0, le=100)
    matched_fields: list[str]


class PatientMergeRequest(BaseModel):
    target_patient_uuid: str = Field(min_length=36, max_length=36)
    confirmation: str = Field(min_length=36, max_length=36)
    reason: str = Field(min_length=10, max_length=500)

    @model_validator(mode="after")
    def target_is_confirmed(self):
        if self.confirmation != self.target_patient_uuid:
            raise ValueError("confirmation must exactly match target_patient_uuid")
        return self


class PatientMergePreview(BaseModel):
    source: PatientOut
    target: PatientOut
    duplicate_score: int
    matched_fields: list[str]
    record_counts: dict[str, int]
    conflicts: list[dict]


class PatientMergeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    source_uuid: str
    target_uuid: str
    reason: str
    duplicate_score: int
    matched_fields: list[str]
    moved_counts: dict[str, int]
    resolved_conflicts: list[dict]
    created_at: datetime


class PatientAddressCreate(BaseModel):
    use: str = Field(default="home", pattern="^(home|work|temp|old|billing)$")
    type: str = Field(default="both", pattern="^(postal|physical|both)$")
    line1: str = Field(min_length=1, max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=30)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    district: str | None = Field(default=None, max_length=255)
    priority: int = Field(default=1, ge=1)
    is_primary: bool = False
    period_start: datetime | None = None
    period_end: datetime | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def valid_period(self):
        if self.period_start and self.period_end and self.period_end <= self.period_start:
            raise ValueError("period_end must be after period_start")
        if self.country_code:
            self.country_code = self.country_code.upper()
        return self


class PatientAddressOut(PatientAddressCreate):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    active: bool
    inactivated_reason: str | None


class PatientTelecomCreate(BaseModel):
    system: str = Field(pattern="^(phone|fax|email|pager|url|sms|other)$")
    use: str = Field(default="home", pattern="^(home|work|temp|old|mobile)$")
    value: str = Field(min_length=1, max_length=255)
    rank: int = Field(default=1, ge=1)
    is_primary: bool = False
    period_start: datetime | None = None
    period_end: datetime | None = None
    notes: str | None = None


class PatientTelecomOut(PatientTelecomCreate):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    active: bool
    inactivated_reason: str | None


class PatientRelatedPersonCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    relationship_code: str = Field(min_length=1, max_length=63)
    role_code: str = Field(min_length=1, max_length=63)
    phone: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    sex: str | None = Field(default=None, max_length=100)
    address_line1: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=30)
    country: str | None = Field(default=None, max_length=100)
    priority: int = Field(default=1, ge=1)
    is_primary_contact: bool = False
    is_emergency_contact: bool = False
    can_make_medical_decisions: bool = False
    can_receive_medical_info: bool = False
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    notes: str | None = None


class PatientRelatedPersonOut(PatientRelatedPersonCreate):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    active: bool
    legacy_source: str | None


class InactivationRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


class PatientNameHistoryCreate(BaseModel):
    prefix: str | None = Field(default=None, max_length=50)
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    suffix: str | None = Field(default=None, max_length=50)
    use: str = Field(default="old", pattern="^(old|maiden|official|usual)$")
    period_start: date | None = None
    period_end: date | None = None
    reason: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def valid_period(self):
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError("period_end must not precede period_start")
        return self


class PatientNameHistoryOut(PatientNameHistoryCreate):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    created_at: datetime


class PatientEmploymentCreate(BaseModel):
    employer_name: str = Field(min_length=1, max_length=255)
    occupation_code: str | None = Field(default=None, max_length=255)
    industry_code: str | None = Field(default=None, max_length=255)
    line1: str | None = Field(default=None, max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=30)
    country: str | None = Field(default=None, max_length=100)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def valid_employment(self):
        if self.starts_at and self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("ends_at must not precede starts_at")
        return self


class PatientEmploymentOut(PatientEmploymentCreate):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    legacy_employer_id: int | None
    active: bool
    inactivated_reason: str | None
    created_at: datetime


class PatientConsentCreate(BaseModel):
    purpose: str = Field(pattern="^(email|sms|voice|postal-mail|privacy-notice|message-delegate|immunization-registry|immunization-sharing|health-information-exchange|patient-portal|advance-directive)$")
    decision: str = Field(pattern="^(permit|deny|acknowledged|completed|not-completed|unknown)$")
    effective_at: datetime | None = None
    expires_at: datetime | None = None
    details: str | None = None
    evidence_reference: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def valid_consent_period(self):
        if self.effective_at and self.expires_at and self.expires_at < self.effective_at:
            raise ValueError("expires_at must not precede effective_at")
        allowed = {"privacy-notice": {"acknowledged", "unknown"}, "advance-directive": {"completed", "not-completed", "unknown"}}
        if self.purpose in allowed and self.decision not in allowed[self.purpose]:
            raise ValueError(f"invalid decision for {self.purpose}")
        if self.purpose not in allowed and self.decision not in {"permit", "deny", "unknown"}:
            raise ValueError(f"invalid decision for {self.purpose}")
        if self.purpose == "message-delegate" and self.decision == "permit" and not self.details:
            raise ValueError("details are required for a message delegate")
        return self


class PatientConsentOut(PatientConsentCreate):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    status: str
    revoked_at: datetime | None
    revocation_reason: str | None
    source: str
    legacy_field: str | None
    legacy_value: str | None
    created_at: datetime


class PatientCustomFieldValueUpdate(BaseModel):
    value: str | None = None


class PatientCustomFieldOut(BaseModel):
    uuid: str
    field_key: str
    group_key: str | None
    title: str
    sequence: int
    data_type: int
    list_id: str | None
    options: list[dict]
    default_value: str | None
    max_length: int | None
    required: bool
    description: str | None
    validation: str | None
    typed_mapping: bool
    value: str | None
    value_source: str | None
    updated_at: datetime | None


class AppointmentBase(BaseModel):
    patient_uuid: str
    facility_uuid: str | None = None
    starts_at: datetime
    ends_at: datetime
    category_id: int | None = None
    title: str | None = Field(default=None, max_length=150)
    reason: str | None = Field(default=None, max_length=255)
    provider_name: str | None = Field(default=None, max_length=150)
    legacy_provider_id: int | None = None
    facility_name: str | None = Field(default=None, max_length=150)
    legacy_facility_id: int | None = None
    room: str | None = Field(default=None, max_length=20)
    location: str | None = Field(default=None, max_length=255)
    contact_name: str | None = Field(default=None, max_length=100)
    contact_phone: str | None = Field(default=None, max_length=50)
    contact_email: EmailStr | None = None
    language: str | None = Field(default=None, max_length=30)
    all_day: bool = False
    recurrence_rule: str | None = Field(default=None, max_length=500)
    send_sms: bool = False
    send_email: bool = False


class AppointmentCreate(AppointmentBase):
    @model_validator(mode="after")
    def validate_appointment(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        if self.send_sms and not self.contact_phone:
            raise ValueError("contact_phone is required when send_sms is enabled")
        if self.send_email and not self.contact_email:
            raise ValueError("contact_email is required when send_email is enabled")
        return self


class AppointmentUpdate(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: str | None = Field(default=None, pattern="^(scheduled|confirmed|arrived|checked-in|in-progress|fulfilled|cancelled|no-show|entered-in-error|pending)$")
    category_id: int | None = None
    title: str | None = Field(default=None, max_length=150)
    reason: str | None = Field(default=None, max_length=255)
    provider_name: str | None = Field(default=None, max_length=150)
    legacy_provider_id: int | None = None
    facility_name: str | None = Field(default=None, max_length=150)
    legacy_facility_id: int | None = None
    facility_uuid: str | None = None
    room: str | None = Field(default=None, max_length=20)
    location: str | None = Field(default=None, max_length=255)
    recurrence_rule: str | None = Field(default=None, max_length=500)
    send_sms: bool | None = None
    send_email: bool | None = None


class AppointmentOut(AppointmentBase):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    status: str
    recurrence_group: str | None


class AppointmentFacilityOut(BaseModel):
    uuid: str
    name: str


class FacilityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    fax: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    website: str | None = Field(default=None, max_length=255)
    street: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=255)
    state: str | None = Field(default=None, max_length=50)
    postal_code: str | None = Field(default=None, max_length=20)
    country_code: str | None = Field(default=None, max_length=30)
    npi: str | None = Field(default=None, max_length=15)
    taxonomy: str | None = Field(default=None, max_length=15)
    service_location: bool = True
    billing_location: bool = True
    accepts_assignment: bool = True


class FacilityOut(FacilityCreate):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    active: bool


class WarehouseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=31)
    name: str = Field(min_length=1, max_length=255)
    facility_uuid: str | None = None
    sequence: int = 0


class WarehouseOut(BaseModel):
    uuid: str
    code: str
    name: str
    facility_uuid: str | None
    sequence: int
    active: bool


class PractitionerCreate(BaseModel):
    username: str | None = Field(default=None, max_length=255)
    first_name: str = Field(min_length=1, max_length=255)
    middle_name: str | None = Field(default=None, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    title: str | None = Field(default=None, max_length=30)
    specialty: str | None = Field(default=None, max_length=255)
    npi: str | None = Field(default=None, max_length=15)
    taxonomy: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    primary_facility_uuid: str | None = None
    calendar_enabled: bool = False


class PractitionerOut(PractitionerCreate):
    uuid: str
    username: str | None
    first_name: str
    middle_name: str | None
    last_name: str
    title: str | None
    specialty: str | None
    npi: str | None
    taxonomy: str | None
    email: str | None
    phone: str | None
    primary_facility_uuid: str | None
    calendar_enabled: bool
    active: bool


class PatientProviderAssignmentCreate(BaseModel):
    practitioner_uuid: str
    facility_uuid: str | None = None
    role: str = Field(pattern="^(primary|referring|consulting|covering)$")
    assigned_at: datetime | None = None


class PatientProviderAssignmentOut(BaseModel):
    uuid: str
    practitioner_uuid: str | None
    facility_uuid: str | None
    role: str
    status: str
    assigned_at: datetime | None
    ended_at: datetime | None
    practitioner_name: str | None
    facility_name: str | None
    source: str
    legacy_practitioner_id: int | None = None
    legacy_facility_id: int | None = None


class UserFacilityAccessCreate(BaseModel):
    facility_uuid: str
    warehouse_uuid: str | None = None


class UserFacilityAccessOut(UserFacilityAccessCreate):
    uuid: str
    facility_name: str
    warehouse_name: str | None


class ReportCatalogItem(BaseModel):
    key: str
    title: str
    category: str
    permission: str
    legacy_path: str
    migrated: bool


class ReportRunCreate(BaseModel):
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    date_from: date | None = None
    date_to: date | None = None
    facility_uuid: str | None = None
    warehouse_code: str | None = Field(default=None, max_length=31)
    status: str | None = Field(default=None, max_length=31)
    patient_uuid: str | None = Field(default=None, min_length=36, max_length=36)
    only_with_failures: bool = False
    only_manually_blocked: bool = False
    only_auto_blocked: bool = False
    code_type_id: int | None = Field(default=None, ge=1)
    include_uncategorized: bool = False
    clinical_type: str | None = Field(default=None, pattern="^(Procedure|Medical History|Service Codes)$")
    age_from: int | None = Field(default=None, ge=0, le=150)
    age_to: int | None = Field(default=None, ge=0, le=150)
    gender: str | None = Field(default=None, max_length=100)
    race: str | None = Field(default=None, max_length=100)
    ethnicity: str | None = Field(default=None, max_length=100)
    diagnosis: str | None = Field(default=None, max_length=250)
    include_allergies: bool = False
    include_problems: bool = False
    drug_name: str | None = Field(default=None, max_length=250)
    include_prescriptions: bool = False
    include_ndc: bool = False
    lab_result: str | None = Field(default=None, max_length=250)
    include_lab_results: bool = False
    service_code: str | None = Field(default=None, max_length=250)
    immunization: str | None = Field(default=None, max_length=250)
    communication: str | None = Field(default=None, pattern="^(allow_sms|allow_voice|allow_mail|allow_email)$")
    include_communication: bool = False
    sort_patient_name: bool = False
    sort_patient_age: bool = False
    include_details: bool = True
    collection_category: str | None = Field(default=None, pattern="^(Due Ins|Ins Summary|Due Pt|All|Credits)$")
    age_by: str = Field(default="service_date", pattern="^(service_date|last_activity)$")
    age_columns: int = Field(default=3, ge=0, le=49)
    age_increment_days: int = Field(default=30, ge=1, le=3650)
    as_of_date: date | None = None
    payer_legacy_id: int | None = Field(default=None, ge=1)
    provider_legacy_id: int | None = Field(default=None, ge=1)
    with_debt_only: bool = False
    include_zero_balances: bool = False
    receipt_report_by: str = Field(default="payer", pattern="^(payer|payment_method|check_number)$")
    use_invoice_date: bool = False
    procedure_code: str | None = Field(default=None, max_length=64)
    payment_service: str | None = Field(default=None, max_length=50)
    payment_ticket: str | None = Field(default=None, max_length=100)
    payment_transaction_id: str | None = Field(default=None, max_length=100)
    payment_action: str | None = Field(default=None, pattern="^(Sale|credit|void)$")
    parked_only: bool = False
    financial_reporting_only: bool = False
    reportable_code_ids: list[int] = Field(default_factory=list, max_length=500)
    patient_list_option: str | None = Field(default=None, pattern="^(demos|allergs|probs|meds|prescripts|comms|insurers|encounts|observs|procs|results)$")
    insurance_legacy_id: int | None = Field(default=None, ge=1)
    encounter_type: str | None = Field(default=None, max_length=100)
    observation_description: str | None = Field(default=None, max_length=250)
    procedure_diagnosis: str | None = Field(default=None, max_length=250)
    patient_list_sort: str | None = Field(default=None, max_length=64)
    patient_list_sort_order: str = Field(default="asc", pattern="^(asc|desc)$")
    ippf_report_type: str = Field(default="i", pattern="^(i|m|g)$")
    ippf_group_by: str | None = Field(default=None, pattern="^(1|2|3|4|5|6|7|8|9|10|11|12|13|17|20|101|102|103|104)$")
    ippf_content: str = Field(default="1", pattern="^(1|2|3|4|5)$")
    ippf_sex: str = Field(default="all", pattern="^(female|male|all)$")
    ippf_columns: list[str] = Field(default_factory=lambda:["total"], max_length=12)
    amc_rule: str = Field(default="send_sum_amc",pattern="^(send_sum_amc|provide_rec_pat_amc|provide_sum_pat_amc)$")
    include_completed: bool = False
    quality_report_uuid: str | None = Field(default=None,min_length=36,max_length=36)
    quality_report_type: str | None = Field(default=None,max_length=31)

    @model_validator(mode="after")
    def validate_range(self):
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("date_to must be on or after date_from")
        if self.age_from is not None and self.age_to is not None and self.age_to < self.age_from:
            raise ValueError("age_to must be on or after age_from")
        if self.occurred_from and self.occurred_to and self.occurred_to < self.occurred_from:
            raise ValueError("occurred_to must be on or after occurred_from")
        allowed_ippf_columns={"total","sex","age2","age9","race","ethnicity","state","language","country_code","city","postal_code","gender_identity","sexual_orientation","referral_source"}
        if any(item not in allowed_ippf_columns for item in self.ippf_columns):
            raise ValueError("ippf_columns contains an unsupported demographic dimension")
        return self


class ReportRunOut(BaseModel):
    uuid: str
    report_key: str
    parameters: dict
    columns: list[str]
    rows: list[dict]
    totals: dict
    row_count: int
    checksum: str
    created_at: datetime


class AmcTrackingUpdate(BaseModel):
    completed: bool
    electronically: bool = False


class AmcTrackingEventOut(BaseModel):
    uuid: str
    rule_id: str
    completed_at: datetime | None
    electronically: bool = False


class PatientEducationResourceCreate(BaseModel):
    name: str = Field(min_length=1,max_length=255)
    url_template: str = Field(min_length=6,max_length=4000)
    sequence: int = Field(default=0,ge=0)
    active: bool = True

    @field_validator("url_template")
    @classmethod
    def valid_search_template(cls,value):
        parsed=urlsplit(value)
        if parsed.scheme not in {"http","https"} or not parsed.netloc:raise ValueError("url_template must be an absolute HTTP(S) URL")
        if value.count("[%]")!=1:raise ValueError("url_template must contain exactly one [%] placeholder")
        return value


class PatientEducationResourceOut(PatientEducationResourceCreate):
    model_config=ConfigDict(from_attributes=True)
    uuid: str


class PatientEducationSearchOut(BaseModel):
    resource_uuid: str
    resource_name: str
    url: str


class IpTrackerUpdate(BaseModel):
    force_block: bool | None = None
    skip_timing_protection: bool | None = None
    reset_applicable_failures: bool = False


class PortalLogin(BaseModel):
    username: str = Field(min_length=1,max_length=255)
    password: str = Field(min_length=8,max_length=255)


class PortalToken(Token):
    force_password_reset: bool


class PortalLoginResult(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"
    force_password_reset: bool = False
    mfa_required: bool = False
    challenge_token: str | None = None


class PortalPasswordChange(BaseModel):
    new_password: str = Field(min_length=12, max_length=255)
    current_password: str | None = Field(default=None, min_length=8, max_length=255)


class PortalAccountCreate(BaseModel):
    username: str = Field(min_length=3,max_length=255)
    temporary_password: str = Field(min_length=12,max_length=255)


class PortalAccountOut(BaseModel):
    uuid: str
    patient_uuid: str | None
    username: str
    email: str | None
    display_name: str | None
    identity_type: str
    active: bool
    force_password_reset: bool
    last_login_at: datetime | None


class PortalRepresentativeCreate(BaseModel):
    username: str = Field(min_length=3, max_length=255)
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=255)
    temporary_password: str = Field(min_length=12, max_length=255)


class PortalAccessGrantCreate(BaseModel):
    representative_username: str = Field(min_length=3, max_length=255)
    relationship_code: str = Field(min_length=2, max_length=50)
    scopes: list[str] = Field(min_length=1)
    consent_basis: str = Field(pattern="^(patient-consent|legal-guardian|parental-authority|court-order|power-of-attorney)$")
    evidence_reference: str | None = Field(default=None, max_length=255)
    starts_at: datetime | None = None
    expires_at: datetime | None = None


class PortalAccessGrantRevoke(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


class PortalAccessGrantOut(BaseModel):
    uuid: str
    patient_uuid: str
    representative_username: str
    representative_name: str
    relationship_code: str
    scopes: list[str]
    consent_basis: str
    evidence_reference: str | None
    starts_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


class PortalContextOut(BaseModel):
    patient_uuid: str
    patient_name: str
    relationship_code: str
    scopes: list[str]
    is_self: bool


class MessageCreate(BaseModel):
    subject: str = Field(min_length=2,max_length=255)
    body: str = Field(min_length=2,max_length=65535)


class MessageReply(BaseModel):
    body: str = Field(min_length=2,max_length=65535)


class SecureMessageOut(BaseModel):
    uuid: str
    sender_kind: str
    sender_name: str | None
    body: str
    created_at: datetime
    read_by_patient_at: datetime | None
    read_by_staff_at: datetime | None


class MessageThreadOut(BaseModel):
    uuid: str
    patient_uuid: str
    patient_name: str
    subject: str
    status: str
    created_at: datetime
    updated_at: datetime
    messages: list[SecureMessageOut]=Field(default_factory=list)


class ClinicalTaskCreate(BaseModel):
    patient_uuid: str
    encounter_uuid: str | None = None
    assigned_user_uuid: str | None = None
    method: str = Field(min_length=1,max_length=30)
    comment: str | None = Field(default=None,max_length=255)
    due_at: datetime | None = None


class ClinicalTaskOut(BaseModel):
    uuid: str
    patient_uuid: str
    encounter_uuid: str | None
    assigned_user_uuid: str | None
    method: str
    comment: str | None
    status: str
    due_at: datetime | None
    completed_at: datetime | None


class CommunicationDeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    channel: str
    recipient: str
    subject: str
    body: str
    template_name: str | None
    status: str
    queued_at: datetime
    sent_at: datetime | None
    failed_at: datetime | None
    error_message: str | None
    attempts: int


class PatientFlowEventCreate(BaseModel):
    status: str = Field(pattern="^(scheduled|confirmed|arrived|checked-in|in-progress|fulfilled|cancelled|no-show|entered-in-error|pending)$")
    room: str | None = Field(default=None, max_length=20)
    encounter_uuid: str | None = None


class PatientFlowEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    sequence: int
    started_at: datetime
    status: str
    legacy_status: str | None
    room: str | None
    actor_name: str | None


class PatientFlowEpisodeOut(BaseModel):
    uuid: str
    patient_uuid: str
    patient_name: str
    appointment_uuid: str | None
    encounter_uuid: str | None
    started_at: datetime
    current_status: str | None
    current_room: str | None
    current_since: datetime | None
    random_drug_test: bool | None
    drug_screen_completed: bool
    events: list[PatientFlowEventOut] = Field(default_factory=list)


class InventoryProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    ndc_number: str | None = Field(default=None, max_length=20)
    drug_code: str | None = Field(default=None, max_length=25)
    form: str | None = Field(default=None, max_length=31)
    size: str | None = Field(default=None, max_length=25)
    unit: str | None = Field(default=None, max_length=31)
    route: str | None = Field(default=None, max_length=31)
    cyp_factor: Decimal = Field(default=Decimal("0"), ge=0)
    reorder_point: Decimal = Field(default=Decimal("0"), ge=0)
    max_level: Decimal = Field(default=Decimal("0"), ge=0)
    allow_combining: bool = False
    allow_multiple: bool = True
    consumable: bool = False
    dispensable: bool = True


class InventoryProductOut(InventoryProductCreate):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    active: bool
    on_hand: int = 0


class InventoryLotCreate(BaseModel):
    lot_number: str | None = Field(default=None, max_length=20)
    expiration: date | None = None
    manufacturer: str | None = Field(default=None, max_length=255)
    warehouse_id: str = Field(default="", max_length=31)
    vendor_id: int | None = None
    opening_quantity: int = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=255)


class InventoryLotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    lot_number: str | None
    expiration: date | None
    manufacturer: str | None
    warehouse_id: str
    vendor_id: int | None
    on_hand: int
    destroyed_at: date | None


class InventoryLotDestroy(BaseModel):
    destroyed_at: date = Field(default_factory=date.today)
    method: str = Field(min_length=1, max_length=255)
    witness: str = Field(min_length=1, max_length=255)
    notes: str | None = Field(default=None, max_length=255)


class InventoryMovementCreate(BaseModel):
    transaction_type: str = Field(pattern="^(purchase|return|transfer|adjustment|consumption)$")
    lot_uuid: str
    destination_lot_uuid: str | None = None
    quantity: int
    occurred_on: date = Field(default_factory=date.today)
    notes: str = Field(min_length=1, max_length=255)


class InventoryDispenseCreate(BaseModel):
    patient_uuid: str
    encounter_uuid: str
    prescription_uuid: str | None = None
    quantity: int = Field(gt=0)
    fee: Decimal = Field(default=Decimal("0"), ge=0)
    warehouse_id: str | None = Field(default=None, max_length=31)
    occurred_on: date = Field(default_factory=date.today)
    notes: str | None = Field(default=None, max_length=255)


class InventoryTransactionOut(BaseModel):
    uuid: str
    product_uuid: str
    lot_uuid: str | None
    destination_lot_uuid: str | None
    patient_uuid: str | None
    encounter_uuid: str | None
    transaction_type: str
    occurred_on: date
    quantity: int
    fee: Decimal
    billed: bool
    actor_name: str | None
    notes: str | None


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
    locked: bool = False
    signature_count: int = 0


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


class SocialHistoryCreate(BaseModel):
    recorded_at: datetime | None = None
    coffee: str | None = Field(default=None,max_length=10000)
    tobacco: str | None = Field(default=None,max_length=10000)
    alcohol: str | None = Field(default=None,max_length=10000)
    sleep_patterns: str | None = Field(default=None,max_length=10000)
    exercise_patterns: str | None = Field(default=None,max_length=10000)
    seatbelt_use: str | None = Field(default=None,max_length=10000)
    counseling: str | None = Field(default=None,max_length=10000)
    hazardous_activities: str | None = Field(default=None,max_length=10000)
    recreational_drugs: str | None = Field(default=None,max_length=10000)
    additional_history: str | None = Field(default=None,max_length=50000)

    @model_validator(mode="after")
    def require_content(self):
        fields=self.model_dump(exclude={"recorded_at"})
        if not any(value and value.strip() for value in fields.values()):
            raise ValueError("At least one social-history field is required")
        return self


class SocialHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    legacy_history_id: int | None = None
    legacy_patient_id: int
    recorded_at: datetime | None = None
    coffee: str | None = None
    tobacco: str | None = None
    alcohol: str | None = None
    sleep_patterns: str | None = None
    exercise_patterns: str | None = None
    seatbelt_use: str | None = None
    counseling: str | None = None
    hazardous_activities: str | None = None
    recreational_drugs: str | None = None
    additional_history: str | None = None
    source_payload: dict | None = None


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
    ordered_at: datetime | None
    status: str
    collected_at: datetime | None = None
    transmitted_at: datetime | None = None
    control_id: str | None = None
    activity: bool = True
    specimen_type: str | None = None
    specimen_location: str | None = None
    specimen_volume: str | None = None
    clinical_history: str | None = None
    external_id: str | None = None
    order_diagnosis: str | None = None
    procedure_order_type: str | None = None


class ProcedureOrderLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    sequence: int
    code: str
    name: str
    source: str | None = None
    diagnoses: str | None = None
    do_not_send: bool
    title: str | None = None
    procedure_type: str | None = None
    standard_code: str | None = None
    transport: str | None = None
    date_end: datetime | None = None
    reason_code: str | None = None
    reason_description: str | None = None
    reason_date_low: datetime | None = None
    reason_date_high: datetime | None = None
    reason_status: str | None = None


class ProcedureReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    order_sequence: int
    collected_at: datetime | None = None
    collected_timezone: str | None = None
    reported_at: datetime | None = None
    reported_timezone: str | None = None
    specimen_number: str | None = None
    status: str | None = None
    review_status: str | None = None
    notes: str | None = None


class LabResultCreate(BaseModel):
    observed_at: datetime
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    value: str = Field(min_length=1, max_length=255)
    unit: str | None = Field(default=None, max_length=31)
    reference_range: str | None = Field(default=None, max_length=255)
    interpretation: str | None = Field(default=None, max_length=31)
    status: str = Field(default="final", pattern="^(preliminary|final|corrected|cancelled)$")
    facility: str | None = Field(default=None, max_length=255)
    comments: str | None = None
    ended_at: datetime | None = None


class LabResultOut(LabResultCreate):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    released_to_patient_at: datetime | None = None
    data_type: str | None = None
    legacy_document_id: int | None = None
    report: ProcedureReportOut | None = None


class LabOrderDetail(LabOrderOut):
    lines: list[ProcedureOrderLineOut]
    reports: list[ProcedureReportOut]
    results: list[LabResultOut]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    name: str
    mime_type: str
    sha256: str
    uploaded_at: datetime
    released_to_patient_at: datetime | None = None


class PatientPhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    original_name: str
    mime_type: str
    sha256: str
    size_bytes: int
    is_primary: bool
    active: bool
    created_at: datetime
    inactivated_at: datetime | None = None
    inactivated_reason: str | None = None


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
    unit_price: Decimal = Field(ge=0, decimal_places=2)
    billed_at: datetime | None = None
    modifier: str | None = Field(default=None, max_length=12)
    authorized: bool = True
    billed: bool = False
    justification: str | None = Field(default=None, max_length=255)
    active: bool = True


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
    released_to_patient_at: datetime | None = None


class PortalStatementOut(BaseModel):
    currency: str
    payments_available: bool
    total_charges: Decimal
    total_paid: Decimal
    balance: Decimal
    claims: list[ClaimOut]


class PortalPaymentIntentCreate(BaseModel):
    claim_uuid: str = Field(min_length=36, max_length=36)
    amount: Decimal = Field(gt=0, decimal_places=2)
    payment_method_token: str = Field(min_length=8, max_length=2048)


class PortalPaymentIntentOut(BaseModel):
    uuid: str
    claim_uuid: str
    amount: Decimal
    currency: str
    provider: str
    status: str
    processor_reference: str | None
    failure_code: str | None
    created_at: datetime
    completed_at: datetime | None


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
    dose_unit: str | None = Field(default=None, max_length=50)
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
    dosage: str | None = Field(default=None, max_length=100)
    size: str | None = Field(default=None, max_length=25)
    route: str | None = Field(default=None, max_length=100)
    per_refill: int | None = Field(default=None, ge=0)
    filled_date: date | None = None
    note: str | None = None
    prn: str | None = Field(default=None, max_length=30)
    usage_category: str | None = Field(default=None, max_length=100)
    usage_category_title: str | None = Field(default=None, max_length=255)
    request_intent: str | None = Field(default=None, max_length=100)
    request_intent_title: str | None = Field(default=None, max_length=255)
    diagnosis: str | None = None


class PrescriptionOut(PrescriptionCreate):
    uuid: str
    prescribed_at: datetime | None
    status: str
    modified_at: datetime | None = None
    pharmacy_name: str | None = None
    filled_by_legacy_id: int | None = None
    provider_legacy_id: int | None = None
    drug_legacy_id: int | None = None
    form_legacy_id: int | None = None
    unit_legacy_id: int | None = None
    interval_legacy_id: int | None = None
    medication_legacy_id: int | None = None
    legacy_recorded_at: datetime | None = None
    legacy_user: str | None = None
    site: str | None = None
    prescription_guid: str | None = None
    erx_source: int = 0
    erx_uploaded: bool = False
    erx_drug_info: str | None = None
    external_id: str | None = None
    ntx: int | None = None
    rtx: int | None = None
    transaction_date: date | None = None


class CarePlanBase(BaseModel):
    recorded_at: datetime
    code: str | None = Field(default=None, max_length=255)
    code_text: str | None = None
    description: str = Field(min_length=1, max_length=20_000)
    external_id: str | None = Field(default=None, max_length=30)
    plan_type: str | None = Field(default=None, max_length=30)
    note_related_to: str | None = None
    ends_at: datetime | None = None
    reason_code: str | None = Field(default=None, max_length=31)
    reason_description: str | None = None
    reason_recorded_at: datetime | None = None
    reason_ends_at: datetime | None = None
    reason_status: str | None = Field(default=None, max_length=31)
    status: str = Field(default="draft", pattern="^(draft|active|on-hold|revoked|completed|cancelled|entered-in-error|unknown)$")
    target_date: datetime | None = None
    engagement_category: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def valid_care_plan(self):
        if self.ends_at and self.ends_at < self.recorded_at: raise ValueError("ends_at must not precede recorded_at")
        if self.target_date and self.target_date < self.recorded_at: raise ValueError("target_date must not precede recorded_at")
        if self.reason_ends_at and self.reason_recorded_at and self.reason_ends_at < self.reason_recorded_at: raise ValueError("reason_ends_at must not precede reason_recorded_at")
        reason_values=(self.reason_code,self.reason_description,self.reason_recorded_at,self.reason_ends_at,self.reason_status)
        if any(value is not None and value != "" for value in reason_values) and (not self.reason_code or not self.reason_status): raise ValueError("reason_code and reason_status are required together")
        return self


class CarePlanCreate(CarePlanBase):
    encounter_uuid: str

    @field_validator("recorded_at", "ends_at", "reason_recorded_at", "reason_ends_at", "target_date")
    @classmethod
    def timezone_required(cls, value: datetime | None):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("care-plan dates must include a timezone")
        return value


class CarePlanUpdate(CarePlanBase):
    @field_validator("recorded_at", "ends_at", "reason_recorded_at", "reason_ends_at", "target_date")
    @classmethod
    def timezone_required(cls, value: datetime | None):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("care-plan dates must include a timezone")
        return value


class CarePlanOut(CarePlanBase):
    uuid: str
    encounter_uuid: str
    active: bool
    created_at: datetime
    updated_at: datetime


class CarePlanOutcomeCreate(BaseModel):
    event_type: str = Field(pattern="^(status|progress|outcome)$")
    plan_status: str | None = Field(default=None, pattern="^(draft|active|on-hold|revoked|completed|cancelled|entered-in-error|unknown)$")
    achievement_status: str | None = Field(default=None, pattern="^(in-progress|improving|worsening|no-change|achieved|sustaining|not-achieved|no-progress|not-attainable)$")
    measure_code: str | None = Field(default=None, max_length=100)
    measure_system: str | None = Field(default=None, max_length=255)
    measure_display: str | None = Field(default=None, max_length=255)
    value_numeric: Decimal | None = None
    value_unit: str | None = Field(default=None, max_length=50)
    note: str | None = Field(default=None, max_length=20_000)
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def timezone_required(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None: raise ValueError("outcome dates must include a timezone")
        return value

    @model_validator(mode="after")
    def valid_outcome(self):
        if not any((self.plan_status,self.achievement_status,self.value_numeric is not None,(self.note or "").strip())): raise ValueError("an outcome must record status, measurement, or note")
        measurement=(self.measure_code,self.measure_system,self.measure_display,self.value_unit)
        if self.value_numeric is not None and not all(measurement): raise ValueError("numeric outcomes require measure code, system, display, and unit")
        if self.value_numeric is None and any(measurement): raise ValueError("measure metadata requires value_numeric")
        return self


class CarePlanOutcomeOut(CarePlanOutcomeCreate):
    uuid: str
    source: str
    created_at: datetime


CARE_TEAM_STATUS = "^(proposed|active|suspended|inactive|entered-in-error)$"


class CareTeamBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    status: str = Field(default="active", pattern=CARE_TEAM_STATUS)
    note: str | None = Field(default=None, max_length=20_000)


class CareTeamCreate(CareTeamBase):
    pass


class CareTeamUpdate(CareTeamBase):
    pass


class CareTeamMemberCreate(BaseModel):
    member_type: str = Field(pattern="^(practitioner|facility|contact)$")
    practitioner_uuid: str | None = None
    facility_uuid: str | None = None
    contact_name: str | None = Field(default=None, max_length=255)
    role: str = Field(min_length=1, max_length=50)
    provider_since: date | None = None
    status: str = Field(default="active", pattern=CARE_TEAM_STATUS)
    note: str | None = Field(default=None, max_length=20_000)

    @model_validator(mode="after")
    def valid_member_target(self):
        if self.member_type == "practitioner" and not self.practitioner_uuid: raise ValueError("practitioner_uuid is required")
        if self.member_type == "facility" and not self.facility_uuid: raise ValueError("facility_uuid is required")
        if self.member_type == "contact" and not (self.contact_name or "").strip(): raise ValueError("contact_name is required")
        if self.member_type != "practitioner" and self.practitioner_uuid: raise ValueError("practitioner_uuid is only valid for practitioner members")
        return self


class CareTeamMemberOut(CareTeamMemberCreate):
    uuid: str
    display_name: str
    inactivated_reason: str | None
    created_at: datetime
    updated_at: datetime


class CareTeamMemberUpdate(BaseModel):
    role: str = Field(min_length=1, max_length=50)
    provider_since: date | None = None
    status: str = Field(default="active", pattern=CARE_TEAM_STATUS)
    note: str | None = Field(default=None, max_length=20_000)


class CareTeamOut(CareTeamBase):
    uuid: str
    members: list[CareTeamMemberOut] = Field(default_factory=list)
    inactivated_reason: str | None = None
    created_at: datetime
    updated_at: datetime


PREFERENCE_CATEGORY = "^(treatment-intervention|care-experience)$"
PREFERENCE_STATUS = "^(preliminary|final|amended)$"


class PatientPreferenceBase(BaseModel):
    category: str = Field(pattern=PREFERENCE_CATEGORY)
    observation_code: str = Field(min_length=1, max_length=50)
    observation_code_text: str | None = Field(default=None, max_length=255)
    value_type: str = Field(pattern="^(coded|text|boolean)$")
    value_code: str | None = Field(default=None, max_length=100)
    value_code_system: str | None = Field(default=None, max_length=255)
    value_display: str | None = Field(default=None, max_length=255)
    value_text: str | None = Field(default=None, max_length=20_000)
    value_boolean: bool | None = None
    effective_at: datetime
    status: str = Field(default="final", pattern=PREFERENCE_STATUS)
    note: str | None = Field(default=None, max_length=20_000)

    @field_validator("effective_at")
    @classmethod
    def timezone_required(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None: raise ValueError("effective_at must include a timezone")
        return value

    @model_validator(mode="after")
    def exact_value_representation(self):
        coded = any(value not in (None, "") for value in (self.value_code, self.value_code_system, self.value_display))
        text = bool((self.value_text or "").strip())
        boolean = self.value_boolean is not None
        if self.value_type == "coded" and not all((self.value_code, self.value_code_system, self.value_display)): raise ValueError("coded preferences require code, system and display")
        if self.value_type == "text" and not text: raise ValueError("text preferences require value_text")
        if self.value_type == "boolean" and not boolean: raise ValueError("boolean preferences require value_boolean")
        if sum((coded, text, boolean)) != 1: raise ValueError("exactly one preference value representation is allowed")
        return self


class PatientPreferenceCreate(PatientPreferenceBase):
    pass


class PatientPreferenceAmend(PatientPreferenceBase):
    amendment_reason: str = Field(min_length=3, max_length=255)


class PatientPreferenceOut(PatientPreferenceBase):
    uuid: str
    supersedes_uuid: str | None = None
    amendment_reason: str | None = None
    active: bool
    inactivated_reason: str | None = None
    created_at: datetime


class PreferenceValueSetOut(BaseModel):
    observation_code: str
    answer_code: str
    answer_system: str
    answer_display: str
    answer_definition: str | None = None
    sort_order: int


class ClinicalFormCreate(BaseModel):
    encounter_uuid: str
    form_type: str = Field(pattern="^(soap|ros|physical_exam|dictation|note|clinic_note|clinical_instructions|aftercare_plan|treatment_plan|transfer_summary|custom)$")
    title: str = Field(min_length=1, max_length=255)
    content: dict


class ClinicalFormUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: dict


class ClinicalSignatureCreate(BaseModel):
    password: str = Field(min_length=1, max_length=1024)
    lock: bool = True
    attestation: str = Field(default="I attest that this clinical record is accurate and complete.", min_length=10, max_length=1000)
    amendment: str | None = Field(default=None, max_length=4000)


class ClinicalSignatureOut(BaseModel):
    uuid: str
    target_type: str
    signer_name: str
    signer_role: str | None
    signed_at: datetime
    auth_method: str
    is_lock: bool
    attestation: str
    amendment: str | None
    content_hash: str
    previous_signature_hash: str | None
    signature_hash: str
    integrity_valid: bool


class ClinicalFormOut(ClinicalFormCreate):
    uuid: str
    status: str
    authored_at: datetime
    signed_at: datetime | None
    locked: bool = False
    signature_count: int = 0
    released_to_patient_at: datetime | None = None


class ClinicalFormLinkOut(BaseModel):
    uuid: str
    label: str
    linked_at: datetime
    legacy_clinical_note_id: int | None = None


class ClinicalFormLinksOut(BaseModel):
    documents: list[ClinicalFormLinkOut]
    results: list[ClinicalFormLinkOut]


class PortalLabResultOut(BaseModel):
    uuid: str
    order_uuid: str
    order_name: str
    observed_at: datetime
    code: str
    name: str
    value: str
    unit: str | None
    reference_range: str | None
    interpretation: str | None
    status: str
    released_to_patient_at: datetime


class PortalClinicalFormOut(BaseModel):
    uuid: str
    encounter_uuid: str
    form_type: str
    title: str
    content: dict
    authored_at: datetime
    signed_at: datetime
    released_to_patient_at: datetime


class QuestionnaireDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    code: str
    version: str
    title: str
    questions: list[dict]


class QuestionnaireResponseCreate(BaseModel):
    questionnaire_uuid: str
    encounter_uuid: str | None = None
    answers: dict[str, int]


class QuestionnaireResponseOut(QuestionnaireResponseCreate):
    uuid: str
    code: str
    score: int
    interpretation: str
    authored_at: datetime
