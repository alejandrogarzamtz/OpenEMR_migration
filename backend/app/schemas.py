from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


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
    date_from: date | None = None
    date_to: date | None = None
    facility_uuid: str | None = None
    warehouse_code: str | None = Field(default=None, max_length=31)
    status: str | None = Field(default=None, max_length=31)

    @model_validator(mode="after")
    def validate_range(self):
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("date_to must be on or after date_from")
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


class PortalLogin(BaseModel):
    username: str = Field(min_length=1,max_length=255)
    password: str = Field(min_length=8,max_length=255)


class PortalToken(Token):
    force_password_reset: bool


class PortalPasswordChange(BaseModel):
    new_password: str = Field(min_length=12, max_length=255)


class PortalAccountCreate(BaseModel):
    username: str = Field(min_length=3,max_length=255)
    temporary_password: str = Field(min_length=12,max_length=255)


class PortalAccountOut(BaseModel):
    uuid: str
    patient_uuid: str
    username: str
    active: bool
    force_password_reset: bool
    last_login_at: datetime | None


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
    released_to_patient_at: datetime | None = None


class LabOrderDetail(LabOrderOut):
    results: list[LabResultOut]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    name: str
    mime_type: str
    sha256: str
    uploaded_at: datetime
    released_to_patient_at: datetime | None = None


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
    released_to_patient_at: datetime | None = None


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
