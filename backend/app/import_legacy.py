"""Idempotent OpenEMR MySQL importer with dry-run reconciliation.

Usage:
  python -m app.import_legacy --source mysql+pymysql://user:pass@host/openemr
  python -m app.import_legacy --source ... --commit
"""
import argparse
import base64
import binascii
import hashlib
import json
import secrets
from datetime import date, datetime, time, timedelta, timezone
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import Session
from .db import Base, engine as target_engine
from .models import AmcTrackingEvent, Appointment, BackgroundService, BillingCodeType, CarePlan, CarePlanOutcome, CareTeam, CareTeamMember, ChartLocationEvent, Charge, Claim, ClinicalForm, ClinicalFormDocumentLink, ClinicalFormResultLink, ClinicalItem, ClinicalRuleLog, ClinicalSignature, ClinicalTask, CommunicationDelivery, Coverage, Document, Encounter, ExternalEncounter, ExternalProcedure, Facility, FrontOfficePayment, Immunization, InsuranceType, InventoryLot, InventoryProduct, InventoryTransaction, IpLoginTracker, LabOrder, LabResult, MessageThread, Patient, PatientConsent, PatientCustomFieldDefinition, PatientCustomFieldValue, PatientEducationResource, PatientEmployment, PatientFlowEpisode, PatientFlowEvent, PatientPhoto, PatientPreference, PatientProviderAssignment, PatientRelatedPerson, PatientTransaction, Payer, PaymentProcessingAudit, Pharmacy, PortalAccount, Practitioner, PractitionerFacilityAccess, PreferenceValueSet, Prescription, ProcedureOrderLine, ProcedureReport, QualityMeasureItem, QualityMeasureReport, ReceivableActivity, ReceivableSession, ReferenceOption, Referral, RegulatoryMetricEvent, SecureMessage, ServiceCode, SocialHistory, SyndromicSubmission, User, VitalSet, Warehouse
from .security import password_hash
from .services.clinical_signatures import clinical_form_hash, encounter_hash, signature_hash

TYPE_MAP = {"medical_problem": "problem", "allergy": "allergy", "medication": "medication", "contraceptive": "contraceptive"}
APPOINTMENT_STATUS_MAP = {"x": "cancelled", "%": "cancelled", "?": "no-show", "@": "arrived", "~": "arrived", "<": "in-progress", ">": "fulfilled", "$": "fulfilled", "^": "pending", "AVM": "confirmed", "SMS": "confirmed", "EMAIL": "confirmed"}
LEGACY_CONSENT_PURPOSES = {
    "hipaa_allowemail": "email", "hipaa_allowsms": "sms", "hipaa_voice": "voice",
    "hipaa_mail": "postal-mail", "hipaa_notice": "privacy-notice", "hipaa_message": "message-delegate",
    "allow_imm_reg_use": "immunization-registry", "allow_imm_info_share": "immunization-sharing",
    "allow_health_info_ex": "health-information-exchange", "allow_patient_portal": "patient-portal",
    "completed_ad": "advance-directive",
}
TYPED_PATIENT_FIELDS = {
    "fname", "mname", "lname", "preferred_name", "suffix", "DOB", "sex", "gender_identity",
    "sexual_orientation", "pronoun", "language", "race", "ethnicity", "email", "phone_cell",
    "phone_home", "street", "street_line_2", "city", "state", "postal_code", "country_code",
    "allow_patient_portal", "hipaa_allowemail", "hipaa_allowsms", "hipaa_voice", "hipaa_mail",
    "hipaa_notice", "hipaa_message", "allow_imm_reg_use", "allow_imm_info_share",
    "allow_health_info_ex", "completed_ad", "deceased_date", "deceased_reason",
}


def clean(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def legacy_image(value) -> tuple[bytes, str] | None:
    if value is None: return None
    payload = value.encode() if isinstance(value, str) else bytes(value)
    candidates = [payload]
    if isinstance(value, str):
        try: candidates.append(base64.b64decode(value, validate=True))
        except (binascii.Error, ValueError): pass
    for candidate in candidates:
        if candidate.startswith(b"\xff\xd8\xff"): return candidate, "image/jpeg"
        if candidate.startswith(b"\x89PNG\r\n\x1a\n"): return candidate, "image/png"
        if candidate.startswith(b"BM"): return candidate, "image/bmp"
    return None


def legacy_consent_decision(purpose: str, value) -> str:
    raw = clean(value); normalized = (raw or "").upper()
    if purpose == "privacy-notice": return "acknowledged" if normalized == "YES" else "unknown"
    if purpose == "advance-directive": return "completed" if normalized == "YES" else "not-completed" if normalized == "NO" else "unknown"
    if purpose == "message-delegate": return "permit" if raw else "unknown"
    return "permit" if normalized == "YES" else "deny" if normalized == "NO" else "unknown"


def parse_legacy_person_name(value) -> tuple[str, str]:
    raw = clean(value)
    if not raw: return "Unknown", "Unknown"
    if "," in raw:
        last, first = (part.strip() for part in raw.split(",", 1))
        return first or "Unknown", last or "Unknown"
    parts = raw.split()
    return (parts[0], "Unknown") if len(parts) == 1 else (" ".join(parts[:-1]), parts[-1])


def valid_dob(value):
    return value if isinstance(value, date) and value.year > 1800 else date(1900, 1, 1)


def legacy_datetime(value, fallback=None):
    if isinstance(value, datetime): return value
    if isinstance(value, date): return datetime.combine(value, time.min, tzinfo=timezone.utc)
    if value:
        try: return datetime.fromisoformat(str(value))
        except ValueError: pass
    return fallback


def patient_for_legacy(target: Session, legacy_pid) -> Patient | None:
    patient = target.scalar(select(Patient).where(Patient.legacy_pid == legacy_pid))
    seen = set()
    while patient and patient.merged_into_id is not None:
        if patient.id in seen: raise RuntimeError("Invalid patient merge chain")
        seen.add(patient.id); patient = target.get(Patient, patient.merged_into_id)
    return patient


def import_clinical_rule_log(row, target: Session) -> str:
    """Import one CDR evaluation row without discarding unresolved legacy references."""
    if target.scalar(select(ClinicalRuleLog.id).where(ClinicalRuleLog.legacy_log_id == row["id"])):
        return "existing"
    patient = patient_for_legacy(target, row.get("pid")) if row.get("pid") else None
    actor = target.scalar(select(User).where(User.legacy_user_id == row.get("uid"))) if row.get("uid") else None
    facility = target.scalar(select(Facility).where(Facility.legacy_facility_id == row.get("facility_id"))) if row.get("facility_id") else None
    target.add(ClinicalRuleLog(
        legacy_log_id=row["id"], occurred_at=legacy_datetime(row.get("date")),
        patient_id=patient.id if patient else None, actor_id=actor.id if actor else None,
        facility_id=facility.id if facility else None,
        legacy_patient_id=row.get("pid") or 0, legacy_user_id=row.get("uid") or 0,
        legacy_facility_id=row.get("facility_id") or 0, category=str(row.get("category") or ""),
        value=row.get("value"), new_value=row.get("new_value"),
        legacy_payload={key: json_value(value) for key, value in row.items()},
    ))
    return "inserted"


def json_value(value):
    if isinstance(value, (date, datetime)): return value.isoformat()
    if hasattr(value, "as_tuple"): return str(value)
    if isinstance(value, bytes): return value.hex()
    return value


def import_social_history(row, target: Session) -> str:
    if target.scalar(select(SocialHistory.id).where(SocialHistory.legacy_history_id==row["id"])):
        return "existing"
    patient=patient_for_legacy(target,row.get("pid")) if row.get("pid") else None
    fields=("coffee","tobacco","alcohol","sleep_patterns","exercise_patterns","seatbelt_use","counseling","hazardous_activities","recreational_drugs","additional_history")
    target.add(SocialHistory(legacy_history_id=row["id"],patient_id=patient.id if patient else None,legacy_patient_id=row.get("pid") or 0,recorded_at=legacy_datetime(row.get("date")),legacy_payload={key:json_value(value) for key,value in row.items()},**{field:row.get(field) for field in fields}))
    return "inserted"


def stable_legacy_row_keys(rows):
    """Return a deterministic key for every row in a source-table multiset."""
    normalized=[(row,{key:json_value(value) for key,value in row.items()}) for row in rows]
    normalized.sort(key=lambda item:(item[1].get("id"),json.dumps(item[1],sort_keys=True)))
    occurrences={}
    result=[]
    for row,payload in normalized:
        digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest();occurrences[digest]=occurrences.get(digest,0)+1
        result.append((row,payload,f"{digest}:{occurrences[digest]}"))
    return result


def event_datetime(day, clock):
    if isinstance(day, datetime):
        day = day.date()
    if isinstance(clock, timedelta):
        return datetime.combine(day, time.min) + clock
    if isinstance(clock, str):
        clock = time.fromisoformat(clock)
    return datetime.combine(day, clock or time.min)


def reconcile_patient_demographics(patient_rows, target: Session) -> dict:
    direct = {
        "fname": ("first_name", lambda value: clean(value) or "Unknown"),
        "mname": ("middle_name", clean), "lname": ("last_name", lambda value: clean(value) or "Unknown"),
        "preferred_name": ("preferred_name", clean), "suffix": ("suffix", clean),
        "DOB": ("date_of_birth", valid_dob), "sex": ("sex", lambda value: clean(value) or "unknown"),
        "gender_identity": ("gender_identity", clean), "sexual_orientation": ("sexual_orientation", clean),
        "pronoun": ("pronouns", clean), "language": ("language", clean), "race": ("race", clean),
        "ethnicity": ("ethnicity", clean), "email": ("email", clean),
        "street": ("address_line_1", clean), "street_line_2": ("address_line_2", clean),
        "city": ("city", clean), "state": ("state", clean), "postal_code": ("postal_code", clean),
        "country_code": ("country_code", clean),
        "allow_patient_portal": ("portal_allowed", lambda value: clean(value) not in {None, "NO", "0"}),
        "hipaa_allowemail": ("allow_email", lambda value: clean(value) == "YES"),
        "hipaa_allowsms": ("allow_sms", lambda value: clean(value) == "YES"),
        "deceased_date": ("deceased_at", lambda value: value), "deceased_reason": ("deceased_reason", clean),
    }
    typed = {field: {"records": 0, "matches": 0, "mismatch_pids": []} for field in direct}
    typed["phone_cell|phone_home"] = {"records": 0, "matches": 0, "mismatch_pids": []}
    payload: dict[str, dict] = {}
    patients = {patient.legacy_pid: patient for patient in target.scalars(select(Patient).where(Patient.legacy_pid.is_not(None)))}
    missing_patients = []
    for row in patient_rows:
        patient = patients.get(row["pid"])
        if not patient:
            missing_patients.append(row["pid"]); continue
        for field, (attribute, normalize) in direct.items():
            result = typed[field]; result["records"] += 1
            expected, actual = normalize(row[field]), getattr(patient, attribute)
            if json_value(expected) == json_value(actual): result["matches"] += 1
            else: result["mismatch_pids"].append(row["pid"])
        phone_result = typed["phone_cell|phone_home"]; phone_result["records"] += 1
        if (clean(row["phone_cell"]) or clean(row["phone_home"])) == patient.phone: phone_result["matches"] += 1
        else: phone_result["mismatch_pids"].append(row["pid"])
        source_payload = patient.legacy_payload or {}
        for field, raw in row.items():
            result = payload.setdefault(field, {"records": 0, "matches": 0, "mismatch_pids": []}); result["records"] += 1
            if source_payload.get(field) == json_value(raw): result["matches"] += 1
            else: result["mismatch_pids"].append(row["pid"])
    result = {"source_patients": len(patient_rows), "target_patients": len(patients), "missing_patient_pids": missing_patients, "typed_fields": typed, "legacy_payload_fields": payload}
    result["sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True, default=json_value).encode()).hexdigest()
    return result


def run(source_url: str, commit: bool = False) -> dict:
    source = create_engine(source_url)
    Base.metadata.create_all(target_engine)
    names = ("patients", "patient_related_people", "patient_consents", "patient_employments", "patient_custom_field_definitions", "patient_custom_field_values", "patient_photos", "reference_options", "insurance_types", "patient_education_resources", "social_histories", "facilities", "warehouses", "practitioners", "practitioner_facility_access", "patient_provider_assignments", "care_teams", "care_team_members", "preference_value_sets", "treatment_preferences", "care_experience_preferences", "appointments", "clinical_items", "syndromic_submissions", "clinical_rule_logs", "amc_tracking_events", "quality_measure_reports", "quality_measure_items", "encounters", "external_encounters", "external_procedures", "patient_flow_episodes", "patient_flow_events", "chart_location_events", "referrals", "patient_transactions", "lab_orders", "procedure_order_lines", "procedure_reports", "lab_results", "documents", "payers", "coverages", "billing_code_types", "charges", "receivable_sessions", "receivable_activities", "front_office_payments", "payment_processing_audits", "claims", "service_codes", "immunizations", "vitals", "pharmacies", "prescriptions", "inventory_products", "inventory_lots", "inventory_transactions", "care_plans", "care_plan_outcomes", "clinical_forms", "clinical_form_document_links", "clinical_form_result_links", "clinical_signatures", "portal_accounts", "message_threads", "secure_messages", "clinical_tasks", "communication_deliveries", "background_services", "ip_login_trackers", "regulatory_metric_events")
    stats = {name: {"source": 0, "inserted": 0, "existing": 0, "rejected": 0} for name in names}
    with source.connect() as legacy, Session(target_engine) as target:
        legacy_tables = set(inspect(source).get_table_names())
        patient_rows = list(legacy.execute(text("SELECT * FROM patient_data ORDER BY pid")).mappings())
        for row in patient_rows:
            stats["patients"]["source"] += 1
            patient = patient_for_legacy(target, row["pid"])
            if patient: stats["patients"]["existing"] += 1; continue
            target.add(Patient(
                legacy_pid=row["pid"],
                first_name=clean(row["fname"]) or "Unknown",
                middle_name=clean(row["mname"]),
                last_name=clean(row["lname"]) or "Unknown",
                preferred_name=clean(row["preferred_name"]),
                suffix=clean(row["suffix"]),
                date_of_birth=valid_dob(row["DOB"]),
                sex=clean(row["sex"]) or "unknown",
                gender_identity=clean(row["gender_identity"]),
                sexual_orientation=clean(row["sexual_orientation"]),
                pronouns=clean(row["pronoun"]),
                language=clean(row["language"]),
                race=clean(row["race"]),
                ethnicity=clean(row["ethnicity"]),
                email=clean(row["email"]),
                phone=clean(row["phone_cell"]) or clean(row["phone_home"]),
                address_line_1=clean(row["street"]),
                address_line_2=clean(row["street_line_2"]),
                city=clean(row["city"]),
                state=clean(row["state"]),
                postal_code=clean(row["postal_code"]),
                country_code=clean(row["country_code"]),
                portal_allowed=clean(row["allow_patient_portal"]) not in {None, "NO", "0"},
                allow_email=clean(row["hipaa_allowemail"]) == "YES",
                allow_sms=clean(row["hipaa_allowsms"]) == "YES",
                deceased_at=row["deceased_date"],
                deceased_reason=clean(row["deceased_reason"]),
                legacy_payload={key: json_value(value) for key, value in row.items()},
            ))
            stats["patients"]["inserted"] += 1
        target.flush()
        def regulatory_event(source_key,metric_type,occurred_at,*,success=None,actor_kind=None,resource=None,payload=None):
            stats["regulatory_metric_events"]["source"]+=1
            existing=target.scalar(select(RegulatoryMetricEvent).where(RegulatoryMetricEvent.source_key==source_key))
            if existing:stats["regulatory_metric_events"]["existing"]+=1;return
            occurred_at=legacy_datetime(occurred_at)
            if occurred_at is None:stats["regulatory_metric_events"]["rejected"]+=1;return
            target.add(RegulatoryMetricEvent(source_key=source_key,metric_type=metric_type,occurred_at=occurred_at,success=success,actor_kind=actor_kind,resource=clean(resource),legacy_payload=payload));stats["regulatory_metric_events"]["inserted"]+=1
        if "ccda" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM ccda ORDER BY id")).mappings():regulatory_event(f"legacy:ccda:{row['id']}","ccda-generated",row["updated_date"],payload={key:json_value(value) for key,value in row.items()})
        if "direct_message_log" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM direct_message_log WHERE status IN ('S','R') ORDER BY id")).mappings():regulatory_event(f"legacy:direct_message_log:{row['id']}","direct-sent" if row["status"]=="S" else "direct-received",row["create_ts"],success=True,payload={key:json_value(value) for key,value in row.items()})
        if "audit_master" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM audit_master WHERE is_qrda_document = 1 ORDER BY id")).mappings():regulatory_event(f"legacy:audit_master:{row['id']}","qrda-import",row["created_time"],success=True,payload={key:json_value(value) for key,value in row.items()})
        if "log" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM log WHERE event = 'qrda3-export' AND success = 1 ORDER BY id")).mappings():regulatory_event(f"legacy:log:qrda3:{row['id']}","qrda3-export",row["date"],success=True,payload={key:json_value(value) for key,value in row.items()})
        if {"api_log","log"}.issubset(legacy_tables):
            for row in legacy.execute(text("SELECT * FROM api_log ORDER BY id")).mappings():
                log_row=legacy.execute(text("SELECT * FROM log WHERE id=:id"),{"id":row["log_id"]}).mappings().first()
                if not log_row:continue
                actor_kind="user" if row["user_id"] else "patient" if row["patient_id"] else None
                regulatory_event(f"legacy:api_log:{row['id']}","api-request",log_row["date"],success=bool(log_row["success"]),actor_kind=actor_kind,resource=row["request"],payload={"api_log":{key:json_value(value) for key,value in row.items()},"log":{key:json_value(value) for key,value in log_row.items()}})
        if "ehi_export_job_tasks" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM ehi_export_job_tasks WHERE status = 'completed' ORDER BY ehi_task_id")).mappings():regulatory_event(f"legacy:ehi_export_job_tasks:{row['ehi_task_id']}","ehi-export",row["completion_date"],success=True,payload={key:json_value(value) for key,value in row.items()})
        target.flush()
        if "list_options" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM list_options ORDER BY list_id,seq,option_id")).mappings():
                stats["reference_options"]["source"]+=1
                if target.scalar(select(ReferenceOption.id).where(ReferenceOption.list_id==row["list_id"],ReferenceOption.option_id==row["option_id"])):stats["reference_options"]["existing"]+=1;continue
                target.add(ReferenceOption(list_id=row["list_id"],option_id=row["option_id"],title=clean(row["title"]) or row["option_id"],sequence=row.get("seq") or 0,active=bool(row.get("activity")),legacy_payload={key:json_value(value) for key,value in row.items()}));stats["reference_options"]["inserted"]+=1
            education_rows=legacy.execute(text("SELECT * FROM list_options WHERE list_id='external_patient_education' ORDER BY seq,option_id")).mappings()
            for row in education_rows:
                stats["patient_education_resources"]["source"]+=1
                if target.scalar(select(PatientEducationResource.id).where(PatientEducationResource.legacy_option_id==row["option_id"])):
                    stats["patient_education_resources"]["existing"]+=1;continue
                if not clean(row.get("title")) or not clean(row.get("notes")) or "[%]" not in row["notes"]:
                    stats["patient_education_resources"]["rejected"]+=1;continue
                target.add(PatientEducationResource(legacy_option_id=row["option_id"],name=clean(row["title"]),url_template=clean(row["notes"]),sequence=row.get("seq") or 0,active=bool(row.get("activity")),legacy_payload={key:json_value(value) for key,value in row.items()}));stats["patient_education_resources"]["inserted"]+=1
        for row in patient_rows:
            patient = patient_for_legacy(target, row["pid"])
            guardian_fields = ("guardiansname", "guardianrelationship", "guardiansex", "guardianaddress", "guardiancity", "guardianstate", "guardianpostalcode", "guardiancountry", "guardianphone", "guardianworkphone", "guardianemail")
            guardian_payload = {field: json_value(row.get(field)) for field in guardian_fields}
            if any(clean(row.get(field)) for field in guardian_fields):
                stats["patient_related_people"]["source"] += 1
                existing = patient and target.scalar(select(PatientRelatedPerson.id).where(PatientRelatedPerson.patient_id == patient.id, PatientRelatedPerson.legacy_source == "patient_data.guardian"))
                if existing: stats["patient_related_people"]["existing"] += 1
                elif not patient: stats["patient_related_people"]["rejected"] += 1
                else:
                    first, last = parse_legacy_person_name(row.get("guardiansname"))
                    target.add(PatientRelatedPerson(
                        patient_id=patient.id, first_name=first, last_name=last,
                        relationship_code=clean(row.get("guardianrelationship")) or "guardian", role_code="guardian",
                        phone=clean(row.get("guardianphone")) or clean(row.get("guardianworkphone")), email=clean(row.get("guardianemail")),
                        sex=clean(row.get("guardiansex")), address_line1=clean(row.get("guardianaddress")), city=clean(row.get("guardiancity")),
                        state=clean(row.get("guardianstate")), postal_code=clean(row.get("guardianpostalcode")), country=clean(row.get("guardiancountry")),
                        active=True, can_make_medical_decisions=False, can_receive_medical_info=False,
                        notes="Imported guardian demographics; legal authority was not inferred.", legacy_source="patient_data.guardian", legacy_payload=guardian_payload,
                    )); stats["patient_related_people"]["inserted"] += 1
            mother_name = clean(row.get("mothersname"))
            if mother_name:
                stats["patient_related_people"]["source"] += 1
                existing = patient and target.scalar(select(PatientRelatedPerson.id).where(PatientRelatedPerson.patient_id == patient.id, PatientRelatedPerson.legacy_source == "patient_data.mother"))
                if existing: stats["patient_related_people"]["existing"] += 1
                elif not patient: stats["patient_related_people"]["rejected"] += 1
                else:
                    first, last = parse_legacy_person_name(mother_name)
                    target.add(PatientRelatedPerson(patient_id=patient.id, first_name=first, last_name=last, relationship_code="mother", role_code="family", active=True, notes="Imported from patient_data.mothersname; authority was not inferred.", legacy_source="patient_data.mother", legacy_payload={"mothersname": mother_name})); stats["patient_related_people"]["inserted"] += 1
        target.flush()
        for row in patient_rows:
            patient = patient_for_legacy(target, row["pid"])
            for legacy_field, purpose in LEGACY_CONSENT_PURPOSES.items():
                stats["patient_consents"]["source"] += 1
                if not patient:
                    stats["patient_consents"]["rejected"] += 1; continue
                if target.scalar(select(PatientConsent.id).where(PatientConsent.patient_id == patient.id, PatientConsent.legacy_field == legacy_field)):
                    stats["patient_consents"]["existing"] += 1; continue
                raw = clean(row[legacy_field]); decision = legacy_consent_decision(purpose, raw)
                target.add(PatientConsent(
                    patient_id=patient.id, purpose=purpose, decision=decision, status="active", source="legacy",
                    effective_at=row["ad_reviewed"] if purpose == "advance-directive" else None,
                    details=raw if purpose == "message-delegate" else None,
                    legacy_field=legacy_field, legacy_value=raw,
                ))
                stats["patient_consents"]["inserted"] += 1
        target.flush()
        layout_rows = list(legacy.execute(text("SELECT * FROM layout_options WHERE form_id='DEM' ORDER BY group_id,seq,field_id")).mappings()) if "layout_options" in legacy_tables else []
        option_groups: dict[str, list[dict]] = {}
        if layout_rows and "list_options" in legacy_tables:
            wanted_lists = {clean(row["list_id"]) for row in layout_rows if clean(row["list_id"])}
            for option in legacy.execute(text("SELECT list_id,option_id,title,seq,activity FROM list_options ORDER BY list_id,seq,option_id")).mappings():
                if option["list_id"] in wanted_lists:
                    option_groups.setdefault(option["list_id"], []).append({"id": str(option["option_id"]), "title": clean(option["title"]) or str(option["option_id"]), "sequence": option["seq"] or 0, "active": bool(option["activity"])})
        for row in layout_rows:
            stats["patient_custom_field_definitions"]["source"] += 1
            definition = target.scalar(select(PatientCustomFieldDefinition).where(PatientCustomFieldDefinition.legacy_form_id == row["form_id"], PatientCustomFieldDefinition.field_key == row["field_id"], PatientCustomFieldDefinition.sequence == row["seq"]))
            if definition:
                stats["patient_custom_field_definitions"]["existing"] += 1; continue
            list_id = clean(row["list_id"])
            target.add(PatientCustomFieldDefinition(
                legacy_form_id=row["form_id"], field_key=row["field_id"], group_key=clean(row["group_id"]),
                title=clean(row["title"]) or row["field_id"], sequence=row["seq"] or 0,
                data_type=row["data_type"] or 0, list_id=list_id, options=option_groups.get(list_id, []),
                default_value=clean(row["default_value"]), max_length=row["max_length"] or None,
                required=row["uor"] == 2, description=clean(row["description"]), validation=clean(row["validation"]),
                conditions=clean(row["conditions"]), codes=clean(row["codes"]),
                typed_mapping=row["field_id"] in TYPED_PATIENT_FIELDS,
                legacy_payload={key: json_value(value) for key, value in row.items()},
            ))
            stats["patient_custom_field_definitions"]["inserted"] += 1
        target.flush()
        patient_columns = {column["name"] for column in inspect(source).get_columns("patient_data")}
        definitions = list(target.scalars(select(PatientCustomFieldDefinition).where(PatientCustomFieldDefinition.legacy_form_id == "DEM")))
        patients_by_legacy = {patient.legacy_pid: patient_for_legacy(target, patient.legacy_pid) for patient in target.scalars(select(Patient).where(Patient.legacy_pid.is_not(None)))}
        for row in patient_rows:
            patient = patients_by_legacy.get(row["pid"])
            for definition in definitions:
                if definition.field_key not in patient_columns: continue
                stats["patient_custom_field_values"]["source"] += 1
                if not patient:
                    stats["patient_custom_field_values"]["rejected"] += 1; continue
                if target.scalar(select(PatientCustomFieldValue.id).where(PatientCustomFieldValue.patient_id == patient.id, PatientCustomFieldValue.definition_id == definition.id)):
                    stats["patient_custom_field_values"]["existing"] += 1; continue
                raw = json_value(row[definition.field_key]); value_text = None if raw is None else str(raw)
                target.add(PatientCustomFieldValue(patient_id=patient.id, definition_id=definition.id, value_text=value_text, source="legacy", legacy_value=value_text))
                stats["patient_custom_field_values"]["inserted"] += 1
        target.flush()
        if "employer_data" in legacy_tables:
            employments = legacy.execute(text("SELECT * FROM employer_data ORDER BY id"))
            for row in employments.mappings():
                stats["patient_employments"]["source"] += 1
                if target.scalar(select(PatientEmployment.id).where(PatientEmployment.legacy_employer_id == row["id"])):
                    stats["patient_employments"]["existing"] += 1; continue
                patient = patient_for_legacy(target, row["pid"])
                employer_name = clean(row["name"])
                if not patient or not employer_name:
                    stats["patient_employments"]["rejected"] += 1; continue
                target.add(PatientEmployment(
                    legacy_employer_id=row["id"], patient_id=patient.id, employer_name=employer_name,
                    occupation_code=clean(row["occupation"]), industry_code=clean(row["industry"]),
                    line1=clean(row["street"]), line2=clean(row["street_line_2"]), city=clean(row["city"]),
                    state=clean(row["state"]), postal_code=clean(row["postal_code"]), country=clean(row["country"]),
                    starts_at=row["start_date"], ends_at=row["end_date"], active=row["end_date"] is None,
                    legacy_payload={key: json_value(value) for key, value in row.items()},
                ))
                stats["patient_employments"]["inserted"] += 1
            target.flush()
        if "history_data" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM history_data ORDER BY id")).mappings():
                stats["social_histories"]["source"]+=1
                result=import_social_history(row,target);stats["social_histories"][result]+=1
            target.flush()
        facilities = legacy.execute(text("SELECT * FROM facility ORDER BY id"))
        for row in facilities.mappings():
            stats["facilities"]["source"] += 1
            if target.scalar(select(Facility.id).where(Facility.legacy_facility_id == row["id"])): stats["facilities"]["existing"] += 1; continue
            if not clean(row["name"]): stats["facilities"]["rejected"] += 1; continue
            target.add(Facility(legacy_facility_id=row["id"],name=clean(row["name"]),phone=clean(row["phone"]),fax=clean(row["fax"]),email=clean(row["email"]),website=clean(row["website"]),street=clean(row["street"]),city=clean(row["city"]),state=clean(row["state"]),postal_code=clean(row["postal_code"]),country_code=clean(row["country_code"]),npi=clean(row["facility_npi"]),taxonomy=clean(row["facility_taxonomy"]),service_location=bool(row["service_location"]),billing_location=bool(row["billing_location"]),accepts_assignment=bool(row["accepts_assignment"]),active=not bool(row["inactive"]),legacy_payload={key:json_value(value) for key,value in row.items()})); stats["facilities"]["inserted"] += 1
        target.flush()
        warehouses = legacy.execute(text("SELECT option_id,title,option_value,seq,activity FROM list_options WHERE list_id='warehouse' ORDER BY seq,option_id"))
        for row in warehouses.mappings():
            stats["warehouses"]["source"] += 1
            if target.scalar(select(Warehouse.id).where(Warehouse.legacy_option_id == row["option_id"])): stats["warehouses"]["existing"] += 1; continue
            facility=target.scalar(select(Facility).where(Facility.legacy_facility_id==int(row["option_value"]))) if str(row["option_value"] or "").isdigit() else None
            target.add(Warehouse(legacy_option_id=row["option_id"],code=row["option_id"],name=clean(row["title"]) or row["option_id"],facility_id=facility.id if facility else None,sequence=row["seq"] or 0,active=bool(row["activity"]),legacy_payload={key:json_value(value) for key,value in row.items()})); stats["warehouses"]["inserted"] += 1
        target.flush()
        practitioners = legacy.execute(text("SELECT * FROM users ORDER BY id"))
        for row in practitioners.mappings():
            stats["practitioners"]["source"] += 1
            if target.scalar(select(Practitioner.id).where(Practitioner.legacy_user_id==row["id"])): stats["practitioners"]["existing"] += 1; continue
            facility=target.scalar(select(Facility).where(Facility.legacy_facility_id==row["facility_id"])) if row["facility_id"] else None
            target.add(Practitioner(legacy_user_id=row["id"],username=clean(row["username"]),first_name=clean(row["fname"]) or clean(row["username"]) or "Unknown",middle_name=clean(row["mname"]),last_name=clean(row["lname"]) or "User",title=clean(row["title"]),specialty=clean(row["specialty"]),npi=clean(row["npi"]),taxonomy=clean(row["taxonomy"]),email=clean(row["email"]),phone=clean(row["phonew1"]) or clean(row["phone"]),primary_facility_id=facility.id if facility else None,calendar_enabled=bool(row["calendar"]),active=bool(row["active"]),legacy_payload={key:json_value(value) for key,value in row.items()})); stats["practitioners"]["inserted"] += 1
        target.flush()
        legacy_users={row["id"]:row for row in legacy.execute(text("SELECT id,fname,lname,facility_id FROM users ORDER BY id")).mappings()}
        for row in patient_rows:
            for field,role in (("providerID","primary"),("ref_providerID","referring")):
                legacy_practitioner_id=row[field]
                if not legacy_practitioner_id:continue
                stats["patient_provider_assignments"]["source"]+=1
                key=f"patient_data:{row['pid']}:{field}"
                existing=target.scalar(select(PatientProviderAssignment).where(PatientProviderAssignment.legacy_assignment_key==key))
                patient=patient_for_legacy(target,row["pid"]);practitioner=target.scalar(select(Practitioner).where(Practitioner.legacy_user_id==legacy_practitioner_id))
                user_row=legacy_users.get(legacy_practitioner_id);legacy_facility_id=user_row["facility_id"] if user_row else None
                facility=target.scalar(select(Facility).where(Facility.legacy_facility_id==legacy_facility_id)) if legacy_facility_id else None
                practitioner_name=" ".join(filter(None,(clean(user_row["fname"]),clean(user_row["lname"])))) if user_row else None
                values=dict(patient_id=patient.id if patient else None,legacy_patient_id=row["pid"],practitioner_id=practitioner.id if practitioner else None,
                    legacy_practitioner_id=legacy_practitioner_id,facility_id=facility.id if facility else None,legacy_facility_id=legacy_facility_id,
                    role=role,status="active",assigned_at=row["regdate"] or row["date"],practitioner_name=practitioner_name or (f"Legacy provider {legacy_practitioner_id}"),
                    facility_name=facility.name if facility else None,source="patient_data",legacy_payload={"pid":row["pid"],field:legacy_practitioner_id,"provider_facility_id":legacy_facility_id})
                if existing:
                    for name,value in values.items():setattr(existing,name,value)
                    stats["patient_provider_assignments"]["existing"]+=1
                else:target.add(PatientProviderAssignment(legacy_assignment_key=key,**values));stats["patient_provider_assignments"]["inserted"]+=1
        target.flush()
        if "clinical_rules_log" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM clinical_rules_log ORDER BY id")).mappings():
                stats["clinical_rule_logs"]["source"] += 1
                result=import_clinical_rule_log(row,target)
                stats["clinical_rule_logs"][result] += 1
            target.flush()
        if "amc_misc_data" in legacy_tables:
            amc_occurrences={}
            for row in legacy.execute(text("SELECT * FROM amc_misc_data ORDER BY amc_id,pid,map_category,map_id,date_created")).mappings():
                stats["amc_tracking_events"]["source"]+=1;patient=patient_for_legacy(target,row["pid"])
                source_key=(row["amc_id"],row["pid"],row["map_category"] or "",row["map_id"] or 0,json_value(row["date_created"]));amc_occurrences[source_key]=amc_occurrences.get(source_key,0)+1;sequence=amc_occurrences[source_key]
                created=legacy_datetime(row["date_created"],datetime(1970,1,1,tzinfo=timezone.utc));base=(AmcTrackingEvent.rule_id==row["amc_id"],AmcTrackingEvent.patient_id==(patient.id if patient else -1),AmcTrackingEvent.object_category==(row["map_category"] or ""),AmcTrackingEvent.legacy_object_id==(row["map_id"] or 0),AmcTrackingEvent.created_at==created)
                existing=target.scalar(select(AmcTrackingEvent).where(*base,AmcTrackingEvent.legacy_sequence==sequence)) if patient else None
                if not existing and patient:
                    existing=target.scalar(select(AmcTrackingEvent).where(*base,AmcTrackingEvent.legacy_sequence.is_(None)))
                    if existing:existing.legacy_sequence=sequence
                if existing:stats["amc_tracking_events"]["existing"]+=1;continue
                if not patient or not clean(row["amc_id"]):stats["amc_tracking_events"]["rejected"]+=1;continue
                target.add(AmcTrackingEvent(rule_id=clean(row["amc_id"]),patient_id=patient.id,object_category=clean(row["map_category"]) or "",legacy_object_id=row["map_id"] or 0,legacy_sequence=sequence,created_at=created,completed_at=legacy_datetime(row["date_completed"]),summary_provided_at=legacy_datetime(row["soc_provided"]),legacy_payload={key:json_value(value) for key,value in row.items()}));stats["amc_tracking_events"]["inserted"]+=1
            target.flush()
        if "report_results" in legacy_tables:
            grouped={}
            for row in legacy.execute(text("SELECT report_id,field_id,field_value FROM report_results ORDER BY report_id,field_id")).mappings():
                grouped.setdefault(row["report_id"],{})[row["field_id"]]=row["field_value"]
            for legacy_id,fields in grouped.items():
                stats["quality_measure_reports"]["source"]+=1
                if target.scalar(select(QualityMeasureReport.id).where(QualityMeasureReport.legacy_report_id==legacy_id)):stats["quality_measure_reports"]["existing"]+=1;continue
                try:decoded=json.loads(fields.get("data") or "[]")
                except (TypeError,ValueError):decoded=[]
                if not isinstance(decoded,list):decoded=[]
                target.add(QualityMeasureReport(legacy_report_id=legacy_id,report_type=clean(fields.get("type")) or "standard",status=clean(fields.get("status")),provider=clean(fields.get("provider")),plan=clean(fields.get("plan")),organize_mode=clean(fields.get("organize_mode")),patient_provider_relationship=clean(fields.get("pat_prov_rel")),labs_manual=clean(fields.get("labs_manual")),reported_at=legacy_datetime(fields.get("date_report")),period_start=legacy_datetime(fields.get("date_begin")),period_end=legacy_datetime(fields.get("date_target")),data=decoded,legacy_fields={key:json_value(value) for key,value in fields.items()}));stats["quality_measure_reports"]["inserted"]+=1
            target.flush()
        if "report_itemized" in legacy_tables:
            sequences={}
            query="SELECT * FROM report_itemized ORDER BY report_id,itemized_test_id,numerator_label,pass,pid,rule_id,item_details"
            for row in legacy.execute(text(query)).mappings():
                stats["quality_measure_items"]["source"]+=1;report=target.scalar(select(QualityMeasureReport).where(QualityMeasureReport.legacy_report_id==row["report_id"]))
                if not report:stats["quality_measure_items"]["rejected"]+=1;continue
                sequences[row["report_id"]]=sequences.get(row["report_id"],0)+1;sequence=sequences[row["report_id"]]
                if target.scalar(select(QualityMeasureItem.id).where(QualityMeasureItem.report_id==report.id,QualityMeasureItem.sequence==sequence)):stats["quality_measure_items"]["existing"]+=1;continue
                try:details=json.loads(row["item_details"]) if row["item_details"] else None
                except (TypeError,ValueError):details={"raw":json_value(row["item_details"]),"parse_error":True}
                patient=patient_for_legacy(target,row["pid"])
                target.add(QualityMeasureItem(report_id=report.id,sequence=sequence,itemized_test_id=row["itemized_test_id"],numerator_label=row["numerator_label"] or "",pass_status=row["pass"],patient_id=patient.id if patient else None,legacy_patient_id=row["pid"],rule_id=clean(row["rule_id"]),item_details=details,legacy_payload={key:json_value(value) for key,value in row.items()}));stats["quality_measure_items"]["inserted"]+=1
            target.flush()
        assignments = legacy.execute(text("SELECT tablename,table_id,facility_id,warehouse_id FROM users_facility WHERE tablename='users' ORDER BY table_id,facility_id,warehouse_id"))
        for row in assignments.mappings():
            stats["practitioner_facility_access"]["source"] += 1
            practitioner=target.scalar(select(Practitioner).where(Practitioner.legacy_user_id==row["table_id"])); facility=target.scalar(select(Facility).where(Facility.legacy_facility_id==row["facility_id"]))
            if not practitioner or not facility: stats["practitioner_facility_access"]["rejected"] += 1; continue
            if target.scalar(select(PractitionerFacilityAccess.id).where(PractitionerFacilityAccess.practitioner_id==practitioner.id,PractitionerFacilityAccess.facility_id==facility.id,PractitionerFacilityAccess.warehouse_code==(clean(row["warehouse_id"]) or ""))): stats["practitioner_facility_access"]["existing"] += 1; continue
            target.add(PractitionerFacilityAccess(practitioner_id=practitioner.id,facility_id=facility.id,warehouse_code=clean(row["warehouse_id"]) or "")); stats["practitioner_facility_access"]["inserted"] += 1
        target.flush()
        if "care_teams" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM care_teams ORDER BY id")).mappings():
                stats["care_teams"]["source"]+=1
                if target.scalar(select(CareTeam.id).where(CareTeam.legacy_care_team_id==row["id"])):stats["care_teams"]["existing"]+=1;continue
                patient=patient_for_legacy(target,row["pid"])
                if not patient:stats["care_teams"]["rejected"]+=1;continue
                target.add(CareTeam(legacy_care_team_id=row["id"],patient_id=patient.id,name=clean(row["team_name"]) or f"Care team {row['id']}",status=(clean(row["status"]) or "active")[:32],note=clean(row["note"]),created_at=legacy_datetime(row["date_created"],datetime.now(timezone.utc)),updated_at=legacy_datetime(row["date_updated"],datetime.now(timezone.utc)),legacy_payload={key:json_value(value) for key,value in row.items()}));stats["care_teams"]["inserted"]+=1
            target.flush()
        if "care_team_member" in legacy_tables:
            contact_columns="NULL AS contact_first_name,NULL AS contact_last_name"
            contact_join=""
            if {"contact","person"}.issubset(legacy_tables):
                contact_columns="p.first_name AS contact_first_name,p.last_name AS contact_last_name";contact_join="LEFT JOIN contact c ON c.id=m.contact_id LEFT JOIN person p ON c.foreign_table_name='person' AND c.foreign_id=p.id"
            query=f"SELECT m.*,{contact_columns} FROM care_team_member m {contact_join} ORDER BY m.id"
            for row in legacy.execute(text(query)).mappings():
                stats["care_team_members"]["source"]+=1
                if target.scalar(select(CareTeamMember.id).where(CareTeamMember.legacy_member_id==row["id"])):stats["care_team_members"]["existing"]+=1;continue
                team=target.scalar(select(CareTeam).where(CareTeam.legacy_care_team_id==row["care_team_id"]));practitioner=target.scalar(select(Practitioner).where(Practitioner.legacy_user_id==row["user_id"])) if row["user_id"] else None;facility=target.scalar(select(Facility).where(Facility.legacy_facility_id==row["facility_id"])) if row["facility_id"] else None
                if not team:stats["care_team_members"]["rejected"]+=1;continue
                member_type="practitioner" if row["user_id"] else "contact" if row["contact_id"] else "facility";contact_name=" ".join(filter(None,(clean(row["contact_first_name"]),clean(row["contact_last_name"]))))
                display=" ".join(filter(None,(practitioner.first_name,practitioner.last_name))) if practitioner else facility.name if member_type=="facility" and facility else contact_name or f"Legacy {member_type} {row['user_id'] or row['contact_id'] or row['facility_id']}"
                target.add(CareTeamMember(legacy_member_id=row["id"],care_team_id=team.id,practitioner_id=practitioner.id if practitioner else None,facility_id=facility.id if facility else None,legacy_user_id=row["user_id"],legacy_facility_id=row["facility_id"],legacy_contact_id=row["contact_id"],member_type=member_type,display_name=display,role=clean(row["role"]) or "participant",provider_since=row["provider_since"],status=(clean(row["status"]) or "active")[:32],note=clean(row["note"]),created_at=legacy_datetime(row["date_created"],datetime.now(timezone.utc)),updated_at=legacy_datetime(row["date_updated"],datetime.now(timezone.utc)),legacy_payload={key:json_value(value) for key,value in row.items()}));stats["care_team_members"]["inserted"]+=1
            target.flush()
        if "preference_value_sets" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM preference_value_sets ORDER BY id")).mappings():
                stats["preference_value_sets"]["source"]+=1
                if target.scalar(select(PreferenceValueSet.id).where(PreferenceValueSet.legacy_value_set_id==row["id"])):stats["preference_value_sets"]["existing"]+=1;continue
                if not all(clean(row[key]) for key in ("loinc_code","answer_code","answer_system","answer_display")):stats["preference_value_sets"]["rejected"]+=1;continue
                target.add(PreferenceValueSet(legacy_value_set_id=row["id"],observation_code=clean(row["loinc_code"]),answer_code=clean(row["answer_code"]),answer_system=clean(row["answer_system"]),answer_display=clean(row["answer_display"]),answer_definition=clean(row["answer_definition"]),sort_order=row["sort_order"] or 0,active=bool(row["active"]),legacy_payload={key:json_value(value) for key,value in row.items()}));stats["preference_value_sets"]["inserted"]+=1
            target.flush()
        preference_sources=(
            ("patient_treatment_intervention_preferences","treatment-intervention","treatment_preferences"),
            ("patient_care_experience_preferences","care-experience","care_experience_preferences"),
        )
        for table_name,category,stat_name in preference_sources:
            if table_name not in legacy_tables:continue
            for row in legacy.execute(text(f"SELECT * FROM {table_name} ORDER BY id")).mappings():
                stats[stat_name]["source"]+=1
                if target.scalar(select(PatientPreference.id).where(PatientPreference.category==category,PatientPreference.legacy_preference_id==row["id"])):stats[stat_name]["existing"]+=1;continue
                patient=patient_for_legacy(target,row["patient_id"]);value_type=clean(row["value_type"]) or "coded";observation_code=clean(row["observation_code"])
                if not patient or not observation_code or value_type not in {"coded","text","boolean"}:stats[stat_name]["rejected"]+=1;continue
                target.add(PatientPreference(category=category,legacy_preference_id=row["id"],patient_id=patient.id,observation_code=observation_code,observation_code_text=clean(row["observation_code_text"]),value_type=value_type,value_code=clean(row["value_code"]),value_code_system=clean(row["value_code_system"]),value_display=clean(row["value_display"]),value_text=clean(row["value_text"]),value_boolean=bool(row["value_boolean"]) if row["value_boolean"] is not None else None,effective_at=legacy_datetime(row["effective_datetime"],datetime.now(timezone.utc)),status=clean(row["status"]) or "final",note=clean(row["note"]),active=True,legacy_payload={key:json_value(value) for key,value in row.items()}));stats[stat_name]["inserted"]+=1
            target.flush()
        appointments = legacy.execute(text("SELECT e.*,u.fname AS provider_fname,u.lname AS provider_lname,f.name AS facility_name FROM openemr_postcalendar_events e LEFT JOIN users u ON u.id=e.pc_aid LEFT JOIN facility f ON f.id=e.pc_facility ORDER BY e.pc_eid"))
        for row in appointments.mappings():
            stats["appointments"]["source"] += 1
            existing_appointment = target.scalar(select(Appointment).where(Appointment.legacy_event_id == row["pc_eid"]))
            if existing_appointment:
                if not existing_appointment.facility_id and row["pc_facility"]:
                    existing_appointment.facility_id = target.scalar(select(Facility.id).where(Facility.legacy_facility_id == row["pc_facility"]))
                stats["appointments"]["existing"] += 1
                continue
            patient = patient_for_legacy(target, row["pc_pid"])
            if not patient or not row["pc_eventDate"]:
                stats["appointments"]["rejected"] += 1
                continue
            starts_at = event_datetime(row["pc_eventDate"], row["pc_startTime"])
            ends_at = event_datetime(row["pc_endDate"] or row["pc_eventDate"], row["pc_endTime"]) if row["pc_endTime"] else starts_at + timedelta(seconds=int(row["pc_duration"] or 0))
            if ends_at <= starts_at:
                ends_at = starts_at + timedelta(minutes=15)
            provider_name = " ".join(filter(None, (clean(row["provider_fname"]), clean(row["provider_lname"])))) or None
            legacy_status = clean(row["pc_apptstatus"]) or "-"
            recurrence_rule = f"LEGACY:type={row['pc_recurrtype']};frequency={row['pc_recurrfreq']};spec={clean(row['pc_recurrspec']) or ''}" if row["pc_recurrtype"] else None
            facility = target.scalar(select(Facility).where(Facility.legacy_facility_id == row["pc_facility"])) if row["pc_facility"] else None
            target.add(Appointment(
                legacy_event_id=row["pc_eid"], patient_id=patient.id,
                legacy_provider_id=int(row["pc_aid"]) if str(row["pc_aid"] or "").isdigit() else None,
                legacy_facility_id=row["pc_facility"] or None, facility_id=facility.id if facility else None, category_id=row["pc_catid"] or None,
                title=clean(row["pc_title"]), starts_at=starts_at, ends_at=ends_at,
                status=APPOINTMENT_STATUS_MAP.get(legacy_status, "scheduled"), legacy_status=legacy_status,
                reason=clean(row["pc_hometext"]), provider_name=provider_name,
                facility_name=clean(row["facility_name"]), room=clean(row["pc_room"]),
                location=clean(row["pc_location"]), contact_name=clean(row["pc_contname"]),
                contact_phone=clean(row["pc_conttel"]), contact_email=clean(row["pc_contemail"]),
                language=clean(row["pc_language"]), all_day=bool(row["pc_alldayevent"]),
                recurrence_rule=recurrence_rule, send_sms=clean(row["pc_sendalertsms"]) == "YES",
                send_email=clean(row["pc_sendalertemail"]) == "YES",
                legacy_payload={key: json_value(value) for key, value in row.items()},
            ))
            stats["appointments"]["inserted"] += 1
        target.flush()
        if "lists_ippf_con" in legacy_tables and "list_options" in legacy_tables:
            item_query = """SELECT l.*,lc.new_method,lo.title AS method_title
                FROM lists l LEFT JOIN lists_ippf_con lc ON l.type='contraceptive' AND lc.id=l.id
                LEFT JOIN list_options lo ON lo.list_id='contrameth' AND lo.option_id=SUBSTRING_INDEX(lc.new_method,'|',1)
                WHERE l.type IN ('medical_problem','allergy','medication','contraceptive') ORDER BY l.id"""
        else:
            item_query = "SELECT l.*,NULL AS new_method,NULL AS method_title FROM lists l WHERE type IN ('medical_problem','allergy','medication') ORDER BY id"
        items = legacy.execute(text(item_query))
        for row in items.mappings():
            stats["clinical_items"]["source"] += 1
            existing=target.scalar(select(ClinicalItem).where(ClinicalItem.legacy_list_id == row["id"]))
            patient = patient_for_legacy(target, row["pid"]); title = clean(row["method_title"]) or clean(row["title"])
            if not patient or not title: continue
            diagnosis = clean(row["diagnosis"]); system, code = (diagnosis.split(":", 1) if diagnosis and ":" in diagnosis else (None, diagnosis))
            values=dict(patient_id=patient.id,category=TYPE_MAP[row["type"]],title=clean(row["method_title"]) or title,code_system=system,code=clean(row["new_method"]) or code,status="active" if row["activity"] else "inactive",onset_date=row["begdate"].date() if row["begdate"] else None,end_date=row["enddate"].date() if row["enddate"] else None,note=clean(row["comments"]),reaction=clean(row["reaction"]),severity=clean(row["severity_al"]),recorded_at=row["date"],legacy_payload={key:json_value(value) for key,value in row.items()})
            if existing:
                for key,value in values.items():setattr(existing,key,value)
                stats["clinical_items"]["existing"] += 1
            else:target.add(ClinicalItem(legacy_list_id=row["id"],**values));stats["clinical_items"]["inserted"] += 1
        target.flush()
        if "syndromic_surveillance" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM syndromic_surveillance ORDER BY id")).mappings():
                stats["syndromic_submissions"]["source"]+=1
                if target.scalar(select(SyndromicSubmission.id).where(SyndromicSubmission.legacy_submission_id==row["id"])):stats["syndromic_submissions"]["existing"]+=1;continue
                item=target.scalar(select(ClinicalItem).where(ClinicalItem.legacy_list_id==row["lists_id"]))
                if not item:stats["syndromic_submissions"]["rejected"]+=1;continue
                target.add(SyndromicSubmission(legacy_submission_id=row["id"],clinical_item_id=item.id,submitted_at=row["submission_date"],filename=clean(row["filename"]) or f"legacy-syndromic-{row['id']}.hl7",legacy_payload={key:json_value(value) for key,value in row.items()}));stats["syndromic_submissions"]["inserted"]+=1
        encounter_authorizations={}
        for registry in legacy.execute(text("SELECT pid,encounter,authorized FROM forms WHERE formdir='newpatient' AND deleted=0 ORDER BY id")).mappings():
            encounter_authorizations[(registry["pid"],registry["encounter"])]=bool(registry["authorized"])
        encounters = legacy.execute(text("SELECT * FROM form_encounter ORDER BY id"))
        for row in encounters.mappings():
            stats["encounters"]["source"] += 1
            existing=target.scalar(select(Encounter).where(Encounter.legacy_encounter_id == row["encounter"]))
            patient = patient_for_legacy(target, row["pid"])
            if not patient or not row["date"]:stats["encounters"]["rejected"]+=1;continue
            practitioner=target.scalar(select(Practitioner).where(Practitioner.legacy_user_id==row["provider_id"])) if row["provider_id"] else None
            facility=target.scalar(select(Facility).where(Facility.legacy_facility_id==row["facility_id"])) if row["facility_id"] else None
            appointment=target.scalar(select(Appointment).where(Appointment.patient_id==patient.id,func.date(Appointment.starts_at)==row["date"].date()).order_by(Appointment.starts_at,Appointment.id))
            values=dict(patient_id=patient.id,appointment_id=appointment.id if appointment else None,occurred_at=row["date"],type=clean(row["class_code"]) or "AMB",chief_complaint=clean(row["reason"]),practitioner_id=practitioner.id if practitioner else None,legacy_provider_id=row["provider_id"] or None,provider_name=" ".join(filter(None,(practitioner.first_name,practitioner.last_name))) if practitioner else None,facility_id=facility.id if facility else None,legacy_facility_id=row["facility_id"] or None,facility_name=clean(row["facility"]) or (facility.name if facility else None),authorized=encounter_authorizations.get((row["pid"],row["encounter"])),legacy_payload={key:json_value(value) for key,value in row.items()})
            if existing:
                for key,value in values.items():setattr(existing,key,value)
                stats["encounters"]["existing"]+=1
            else:
                target.add(Encounter(legacy_encounter_id=row["encounter"],**values));stats["encounters"]["inserted"] += 1
        target.flush()
        trackers = legacy.execute(text("SELECT * FROM patient_tracker ORDER BY id"))
        for row in trackers.mappings():
            stats["patient_flow_episodes"]["source"] += 1
            if target.scalar(select(PatientFlowEpisode.id).where(PatientFlowEpisode.legacy_tracker_id == row["id"])):
                stats["patient_flow_episodes"]["existing"] += 1
                continue
            patient = patient_for_legacy(target, row["pid"])
            appointment = target.scalar(select(Appointment).where(Appointment.legacy_event_id == row["eid"])) if row["eid"] else None
            encounter = target.scalar(select(Encounter).where(Encounter.legacy_encounter_id == row["encounter"])) if row["encounter"] else None
            if not patient:
                stats["patient_flow_episodes"]["rejected"] += 1
                continue
            if not row["date"] and not row["apptdate"]:
                stats["patient_flow_episodes"]["rejected"] += 1
                continue
            started_at = row["date"] or event_datetime(row["apptdate"], row["appttime"])
            target.add(PatientFlowEpisode(
                legacy_tracker_id=row["id"], patient_id=patient.id,
                appointment_id=appointment.id if appointment else None,
                encounter_id=encounter.id if encounter else None, started_at=started_at,
                random_drug_test=None if row["random_drug_test"] is None else bool(row["random_drug_test"]),
                drug_screen_completed=bool(row["drug_screen_completed"]),
                legacy_payload={key: json_value(value) for key, value in row.items()},
            ))
            stats["patient_flow_episodes"]["inserted"] += 1
        target.flush()
        tracker_events = legacy.execute(text("SELECT * FROM patient_tracker_element ORDER BY pt_tracker_id,LENGTH(seq),seq"))
        for row in tracker_events.mappings():
            stats["patient_flow_events"]["source"] += 1
            episode = target.scalar(select(PatientFlowEpisode).where(PatientFlowEpisode.legacy_tracker_id == row["pt_tracker_id"]))
            sequence = int(row["seq"] or 0)
            if not episode or sequence < 1:
                stats["patient_flow_events"]["rejected"] += 1
                continue
            if target.scalar(select(PatientFlowEvent.id).where(PatientFlowEvent.episode_id == episode.id, PatientFlowEvent.sequence == sequence)):
                stats["patient_flow_events"]["existing"] += 1
                continue
            legacy_status = clean(row["status"]) or "-"
            target.add(PatientFlowEvent(
                episode_id=episode.id, sequence=sequence,
                started_at=row["start_datetime"] or episode.started_at,
                status=APPOINTMENT_STATUS_MAP.get(legacy_status, "scheduled"),
                legacy_status=legacy_status, room=clean(row["room"]), actor_name=clean(row["user"]),
                legacy_payload={key: json_value(value) for key, value in row.items()},
            ))
            stats["patient_flow_events"]["inserted"] += 1
        target.flush()
        order_lines = list(legacy.execute(text("SELECT * FROM procedure_order_code ORDER BY procedure_order_id,procedure_order_seq")).mappings())
        procedure_standards = {}
        if "procedure_type" in legacy_tables:
            for definition in legacy.execute(text("SELECT procedure_code,lab_id,standard_code FROM procedure_type ORDER BY procedure_type_id")).mappings():
                procedure_standards.setdefault((clean(definition["procedure_code"]), definition["lab_id"] or 0), clean(definition["standard_code"]))
        procedure_provider_names={row["ppid"]:clean(row["name"]) for row in legacy.execute(text("SELECT ppid,name FROM procedure_providers ORDER BY ppid")).mappings()} if "procedure_providers" in legacy_tables else {}
        first_lines = {}
        for line in order_lines: first_lines.setdefault(line["procedure_order_id"], line)
        orders = legacy.execute(text("SELECT * FROM procedure_order ORDER BY procedure_order_id"))
        for row in orders.mappings():
            stats["lab_orders"]["source"] += 1
            existing = target.scalar(select(LabOrder).where(LabOrder.legacy_order_id == row["procedure_order_id"]))
            patient = patient_for_legacy(target, row["patient_id"])
            encounter = target.scalar(select(Encounter).where(Encounter.legacy_encounter_id == row["encounter_id"])) if row["encounter_id"] else None
            if not patient: stats["lab_orders"]["rejected"] += 1; continue
            primary = first_lines.get(row["procedure_order_id"], {})
            values = dict(patient_id=patient.id, encounter_id=encounter.id if encounter else None,
                ordered_at=row["date_ordered"], code=clean(primary.get("procedure_code")) or "unknown",
                name=clean(primary.get("procedure_name")) or "Unnamed procedure", priority=clean(row["order_priority"]) or "routine",
                status=clean(row["order_status"]) or "pending", instructions=clean(row["patient_instructions"]),
                collected_at=row["date_collected"], transmitted_at=row["date_transmitted"], control_id=clean(row["control_id"]),
                activity=bool(row["activity"]), provider_legacy_id=row["provider_id"] or None, lab_legacy_id=row["lab_id"] or None,
                specimen_type=clean(row["specimen_type"]), specimen_location=clean(row["specimen_location"]),
                specimen_volume=clean(row["specimen_volume"]), clinical_history=clean(row["clinical_hx"]),
                external_id=clean(row["external_id"]), order_diagnosis=clean(row["order_diagnosis"]),
                procedure_order_type=clean(row["procedure_order_type"]),
                legacy_payload={key: json_value(value) for key,value in row.items()}|{"lab_name":procedure_provider_names.get(row["lab_id"])})
            if existing:
                for key,value in values.items(): setattr(existing,key,value)
                stats["lab_orders"]["existing"] += 1
            else:
                target.add(LabOrder(legacy_order_id=row["procedure_order_id"],**values));stats["lab_orders"]["inserted"] += 1
        target.flush()
        for row in order_lines:
            stats["procedure_order_lines"]["source"] += 1
            order=target.scalar(select(LabOrder).where(LabOrder.legacy_order_id==row["procedure_order_id"]))
            if not order: stats["procedure_order_lines"]["rejected"]+=1;continue
            line=target.scalar(select(ProcedureOrderLine).where(ProcedureOrderLine.order_id==order.id,ProcedureOrderLine.sequence==row["procedure_order_seq"]))
            values=dict(code=clean(row["procedure_code"]) or "",name=clean(row["procedure_name"]) or "",source=clean(row["procedure_source"]),
                diagnoses=clean(row["diagnoses"]),do_not_send=bool(row["do_not_send"]),title=clean(row["procedure_order_title"]),
                procedure_type=clean(row["procedure_type"]),standard_code=procedure_standards.get((clean(row["procedure_code"]), order.lab_legacy_id or 0)),transport=clean(row["transport"]),date_end=row["date_end"],
                reason_code=clean(row["reason_code"]),reason_description=clean(row["reason_description"]),reason_date_low=row["reason_date_low"],
                reason_date_high=row["reason_date_high"],reason_status=clean(row["reason_status"]),legacy_payload={key:json_value(value) for key,value in row.items()})
            if line:
                for key,value in values.items():setattr(line,key,value)
                stats["procedure_order_lines"]["existing"]+=1
            else: target.add(ProcedureOrderLine(order_id=order.id,sequence=row["procedure_order_seq"],**values));stats["procedure_order_lines"]["inserted"]+=1
        target.flush()
        reports=legacy.execute(text("SELECT * FROM procedure_report ORDER BY procedure_report_id"))
        for row in reports.mappings():
            stats["procedure_reports"]["source"]+=1
            order=target.scalar(select(LabOrder).where(LabOrder.legacy_order_id==row["procedure_order_id"])) if row["procedure_order_id"] else None
            report=target.scalar(select(ProcedureReport).where(ProcedureReport.legacy_report_id==row["procedure_report_id"]))
            values=dict(order_id=order.id if order else None,legacy_order_id=row["procedure_order_id"],order_sequence=row["procedure_order_seq"],
                collected_at=row["date_collected"],collected_timezone=clean(row["date_collected_tz"]),reported_at=row["date_report"],
                reported_timezone=clean(row["date_report_tz"]),source_legacy_user_id=row["source"] or None,specimen_number=clean(row["specimen_num"]),
                status=clean(row["report_status"]),review_status=clean(row["review_status"]),notes=clean(row["report_notes"]),
                legacy_payload={key:json_value(value) for key,value in row.items()})
            if report:
                for key,value in values.items():setattr(report,key,value)
                stats["procedure_reports"]["existing"]+=1
            else: target.add(ProcedureReport(legacy_report_id=row["procedure_report_id"],**values));stats["procedure_reports"]["inserted"]+=1
        target.flush()
        results = legacy.execute(text("SELECT * FROM procedure_result ORDER BY procedure_result_id"))
        for row in results.mappings():
            stats["lab_results"]["source"] += 1
            report=target.scalar(select(ProcedureReport).where(ProcedureReport.legacy_report_id==row["procedure_report_id"]))
            existing=target.scalar(select(LabResult).where(LabResult.legacy_result_id==row["procedure_result_id"]))
            values=dict(order_id=report.order_id if report else None,report_id=report.id if report else None,observed_at=row["date"],
                code=clean(row["result_code"]) or "unknown",name=clean(row["result_text"]) or clean(row["result_code"]) or "Result",
                value=clean(row["result"]) or "",unit=clean(row["units"]),reference_range=clean(row["range"]),interpretation=clean(row["abnormal"]),
                status=clean(row["result_status"]) or "final",data_type=clean(row["result_data_type"]),facility=clean(row["facility"]),
                comments=clean(row["comments"]),legacy_document_id=row["document_id"] or None,ended_at=row["date_end"],
                legacy_payload={key:json_value(value) for key,value in row.items()})
            if existing:
                for key,value in values.items():setattr(existing,key,value)
                stats["lab_results"]["existing"]+=1
            else: target.add(LabResult(legacy_result_id=row["procedure_result_id"],**values));stats["lab_results"]["inserted"]+=1
        documents = legacy.execute(text("SELECT id,foreign_id,name,mimetype,document_data,date FROM documents WHERE deleted=0 ORDER BY id"))
        for row in documents.mappings():
            stats["documents"]["source"] += 1
            if target.scalar(select(Document.id).where(Document.legacy_document_id == row["id"])): stats["documents"]["existing"] += 1; continue
            patient = patient_for_legacy(target, row["foreign_id"]); content = row["document_data"]
            if not patient or not content: stats["documents"]["rejected"] += 1; continue
            payload = content.encode() if isinstance(content, str) else bytes(content)
            target.add(Document(legacy_document_id=row["id"], patient_id=patient.id, name=clean(row["name"]) or f"document-{row['id']}", mime_type=clean(row["mimetype"]) or "application/octet-stream", content=payload, sha256=hashlib.sha256(payload).hexdigest(), uploaded_at=row["date"] or datetime.now(timezone.utc)))
            stats["documents"]["inserted"] += 1
        photo_documents = legacy.execute(text("""SELECT d.id,d.foreign_id,d.name,d.mimetype,d.document_data,d.date,d.url,d.hash FROM documents d JOIN categories_to_documents cd ON cd.document_id=d.id JOIN categories c ON c.id=cd.category_id WHERE d.deleted=0 AND LOWER(c.name)=LOWER('Patient Photograph') ORDER BY d.foreign_id,d.date,d.id"""))
        for row in photo_documents.mappings():
            stats["patient_photos"]["source"] += 1
            if target.scalar(select(PatientPhoto.id).where(PatientPhoto.legacy_document_id == row["id"])): stats["patient_photos"]["existing"] += 1; continue
            patient = patient_for_legacy(target, row["foreign_id"]); decoded = legacy_image(row["document_data"])
            if not patient or not decoded: stats["patient_photos"]["rejected"] += 1; continue
            payload, mime_type = decoded
            for current in target.scalars(select(PatientPhoto).where(PatientPhoto.patient_id == patient.id, PatientPhoto.is_primary.is_(True))): current.is_primary = False
            target.add(PatientPhoto(legacy_document_id=row["id"], patient_id=patient.id, original_name=clean(row["name"]) or f"patient-photo-{row['id']}", mime_type=mime_type, content=payload, sha256=hashlib.sha256(payload).hexdigest(), size_bytes=len(payload), is_primary=True, created_at=row["date"] or datetime.now(timezone.utc), legacy_payload={"url":clean(row["url"]), "legacy_hash":clean(row["hash"]), "declared_mimetype":clean(row["mimetype"])}))
            stats["patient_photos"]["inserted"] += 1
        if "insurance_type_codes" in legacy_tables:
            for row in legacy.execute(text("SELECT id,type,claim_type FROM insurance_type_codes ORDER BY id")).mappings():
                stats["insurance_types"]["source"]+=1
                if target.scalar(select(InsuranceType.id).where(InsuranceType.legacy_type_id==row["id"])):stats["insurance_types"]["existing"]+=1;continue
                target.add(InsuranceType(legacy_type_id=row["id"],name=clean(row["type"]) or f"Insurance type {row['id']}",claim_type=clean(row["claim_type"])));stats["insurance_types"]["inserted"]+=1
        payers = legacy.execute(text("SELECT * FROM insurance_companies ORDER BY id"))
        for row in payers.mappings():
            stats["payers"]["source"] += 1
            if target.scalar(select(Payer.id).where(Payer.legacy_payer_id == row["id"])): stats["payers"]["existing"] += 1; continue
            if not clean(row["name"]): stats["payers"]["rejected"] += 1; continue
            target.add(Payer(legacy_payer_id=row["id"], name=clean(row["name"]), payer_identifier=clean(row["x12_receiver_id"]) or clean(row["cms_id"]), active=not bool(row["inactive"]),legacy_payload={key:json_value(value) for key,value in row.items()}))
            stats["payers"]["inserted"] += 1
        target.flush()
        coverages = legacy.execute(text("SELECT * FROM insurance_data ORDER BY id"))
        for row in coverages.mappings():
            stats["coverages"]["source"] += 1
            existing=target.scalar(select(Coverage).where(Coverage.legacy_insurance_id == row["id"]))
            patient=patient_for_legacy(target,row["pid"]); payer=target.scalar(select(Payer).where(Payer.legacy_payer_id==int(row["provider"]))) if str(row["provider"] or "").isdigit() else None
            subscriber=" ".join(filter(None,(clean(row["subscriber_fname"]),clean(row.get("subscriber_mname")),clean(row["subscriber_lname"]))))
            payload={key:json_value(value) for key,value in row.items()}
            if existing:
                existing.legacy_payload=payload;stats["coverages"]["existing"] += 1;continue
            if not patient or not payer or not clean(row["policy_number"]) or not subscriber: stats["coverages"]["rejected"] += 1; continue
            target.add(Coverage(legacy_insurance_id=row["id"],patient_id=patient.id,payer_id=payer.id,priority=clean(row["type"]) or "primary",plan_name=clean(row["plan_name"]),policy_number=clean(row["policy_number"]),group_number=clean(row["group_number"]),subscriber_name=subscriber,relationship=clean(row["subscriber_relationship"]) or "self",starts_on=row["date"],ends_on=row["date_end"],legacy_payload=payload))
            stats["coverages"]["inserted"] += 1
        target.flush()
        if "code_types" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM code_types ORDER BY ct_seq,ct_key")).mappings():
                stats["billing_code_types"]["source"]+=1
                existing=target.scalar(select(BillingCodeType).where(BillingCodeType.key==row["ct_key"]))
                values=dict(legacy_type_id=row["ct_id"],sequence=row["ct_seq"] or 0,fee=bool(row["ct_fee"]),justification_type=clean(row["ct_just"]),diagnosis=bool(row["ct_diag"]),procedure=bool(row["ct_proc"]),active=bool(row["ct_active"]),label=clean(row["ct_label"]),legacy_payload={key:json_value(value) for key,value in row.items()})
                if existing:
                    for key,value in values.items():setattr(existing,key,value)
                    stats["billing_code_types"]["existing"]+=1
                else:
                    target.add(BillingCodeType(key=row["ct_key"],**values));stats["billing_code_types"]["inserted"]+=1
            target.flush()
        charges=legacy.execute(text("SELECT * FROM billing ORDER BY id"))
        for row in charges.mappings():
            stats["charges"]["source"] += 1
            existing=target.scalar(select(Charge).where(Charge.legacy_billing_id==row["id"]))
            patient=patient_for_legacy(target,row["pid"]); encounter=target.scalar(select(Encounter).where(Encounter.legacy_encounter_id==row["encounter"]))
            if not patient or not encounter or not clean(row["code"]): stats["charges"]["rejected"] += 1; continue
            values=dict(patient_id=patient.id,encounter_id=encounter.id,code_system=clean(row["code_type"]) or "CPT",code=clean(row["code"]),description=clean(row["code_text"]) or clean(row["code"]),units=row["units"] or 1,unit_price=row["fee"] or 0,billed_at=row["date"],modifier=clean(row["modifier"]),authorized=bool(row["authorized"]),billed=bool(row["billed"]),justification=clean(row["justify"]),active=bool(row["activity"]),legacy_payload={key:json_value(value) for key,value in row.items()})
            if existing:
                for key,value in values.items():setattr(existing,key,value)
                stats["charges"]["existing"] += 1
            else:
                target.add(Charge(legacy_billing_id=row["id"],**values));stats["charges"]["inserted"] += 1
        target.flush()
        if "ar_session" in legacy_tables:
            method_join="LEFT JOIN list_options lo ON lo.list_id='payment_method' AND lo.option_id=s.payment_method" if "list_options" in legacy_tables else ""
            method_column="lo.title AS payment_method_label" if method_join else "NULL AS payment_method_label"
            for row in legacy.execute(text(f"SELECT s.*,{method_column} FROM ar_session s {method_join} ORDER BY s.session_id")).mappings():
                stats["receivable_sessions"]["source"]+=1
                existing=target.scalar(select(ReceivableSession).where(ReceivableSession.legacy_session_id==row["session_id"]))
                patient=patient_for_legacy(target,row["patient_id"]) if row["patient_id"] else None
                payer=target.scalar(select(Payer).where(Payer.legacy_payer_id==row["payer_id"])) if row["payer_id"] else None
                values=dict(patient_id=patient.id if patient else None,legacy_patient_id=row["patient_id"] or 0,payer_id=payer.id if payer else None,legacy_payer_id=row["payer_id"] or None,legacy_user_id=row["user_id"] or None,closed=bool(row["closed"]),reference=clean(row["reference"]),check_date=row["check_date"],deposit_date=row["deposit_date"],pay_total=row["pay_total"] or 0,global_amount=row["global_amount"] or 0,payment_type=clean(row["payment_type"]),description=clean(row["description"]),adjustment_code=clean(row["adjustment_code"]),post_to_date=row["post_to_date"],payment_method=clean(row["payment_method"]),payment_method_label=clean(row["payment_method_label"]),created_at=legacy_datetime(row["created_time"]),modified_at=legacy_datetime(row["modified_time"]),legacy_payload={key:json_value(value) for key,value in row.items()})
                if existing:
                    for key,value in values.items():setattr(existing,key,value)
                    stats["receivable_sessions"]["existing"]+=1
                else:target.add(ReceivableSession(legacy_session_id=row["session_id"],**values));stats["receivable_sessions"]["inserted"]+=1
            target.flush()
        if "ar_activity" in legacy_tables:
            session_columns="NULL AS session_payer_id,NULL AS session_reference,NULL AS session_check_date,NULL AS session_deposit_date,NULL AS session_payment_method,NULL AS session_payment_method_label"
            session_join=""
            if "ar_session" in legacy_tables:
                method_label="lo.title" if "list_options" in legacy_tables else "NULL"
                session_columns=f"s.payer_id AS session_payer_id,s.reference AS session_reference,s.check_date AS session_check_date,s.deposit_date AS session_deposit_date,s.payment_method AS session_payment_method,{method_label} AS session_payment_method_label"
                session_join="LEFT JOIN ar_session s ON s.session_id=a.session_id LEFT JOIN list_options lo ON lo.list_id='payment_method' AND lo.option_id=s.payment_method" if "list_options" in legacy_tables else "LEFT JOIN ar_session s ON s.session_id=a.session_id"
            for row in legacy.execute(text(f"SELECT a.*,{session_columns} FROM ar_activity a {session_join} ORDER BY a.pid,a.encounter,a.sequence_no")).mappings():
                stats["receivable_activities"]["source"]+=1
                existing=target.scalar(select(ReceivableActivity).where(ReceivableActivity.legacy_patient_id==row["pid"],ReceivableActivity.legacy_encounter_id==row["encounter"],ReceivableActivity.legacy_sequence==row["sequence_no"]))
                patient=patient_for_legacy(target,row["pid"]);encounter=target.scalar(select(Encounter).where(Encounter.legacy_encounter_id==row["encounter"]))
                payer=target.scalar(select(Payer).where(Payer.legacy_payer_id==row["session_payer_id"])) if row["session_payer_id"] else None
                values=dict(patient_id=patient.id if patient else None,encounter_id=encounter.id if encounter else None,legacy_session_id=row["session_id"] or None,payer_type=row["payer_type"],payer_id=payer.id if payer else None,legacy_payer_id=row["session_payer_id"] or None,account_code=clean(row["account_code"]) or "",code_system=clean(row["code_type"]),code=clean(row["code"]),modifier=clean(row["modifier"]),pay_amount=row["pay_amount"] or 0,adjustment_amount=row["adj_amount"] or 0,posted_at=row["post_time"],payment_reference=clean(row["session_reference"]),check_date=row["session_check_date"],deposit_date=row["session_deposit_date"],payment_method=clean(row["session_payment_method"]),payment_method_label=clean(row["session_payment_method_label"]),memo=clean(row["memo"]),follow_up_note=clean(row["follow_up_note"]),reason_code=clean(row["reason_code"]),post_date=row["post_date"],payer_claim_number=clean(row["payer_claim_number"]),deleted_at=row["deleted"],legacy_payload={key:json_value(value) for key,value in row.items()})
                if existing:
                    for key,value in values.items():setattr(existing,key,value)
                    stats["receivable_activities"]["existing"]+=1
                else:
                    target.add(ReceivableActivity(legacy_patient_id=row["pid"],legacy_encounter_id=row["encounter"],legacy_sequence=row["sequence_no"],**values));stats["receivable_activities"]["inserted"]+=1
            target.flush()
        if "payments" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM payments ORDER BY id")).mappings():
                stats["front_office_payments"]["source"]+=1
                existing=target.scalar(select(FrontOfficePayment).where(FrontOfficePayment.legacy_payment_id==row["id"]))
                patient=patient_for_legacy(target,row["pid"]);encounter=target.scalar(select(Encounter).where(Encounter.legacy_encounter_id==row["encounter"])) if row["encounter"] else None
                values=dict(patient_id=patient.id if patient else None,encounter_id=encounter.id if encounter else None,legacy_patient_id=row["pid"],legacy_encounter_id=row["encounter"],received_at=row["dtime"],actor_name=clean(row["user"]),method=clean(row["method"]),source=clean(row["source"]),current_amount=row["amount1"] or 0,previous_amount=row["amount2"] or 0,posted_current_amount=row["posted1"] or 0,posted_previous_amount=row["posted2"] or 0,legacy_payload={key:json_value(value) for key,value in row.items()})
                if existing:
                    for key,value in values.items():setattr(existing,key,value)
                    stats["front_office_payments"]["existing"]+=1
                else:target.add(FrontOfficePayment(legacy_payment_id=row["id"],**values));stats["front_office_payments"]["inserted"]+=1
            target.flush()
        if "payment_processing_audit" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM payment_processing_audit ORDER BY date,uuid")).mappings():
                stats["payment_processing_audits"]["source"]+=1;legacy_uuid=json_value(row["uuid"])
                existing=target.scalar(select(PaymentProcessingAudit).where(PaymentProcessingAudit.legacy_uuid_hex==legacy_uuid))
                def readable_payload(raw):
                    if not isinstance(raw,str):return None
                    try:
                        parsed=json.loads(raw);return parsed if isinstance(parsed,dict) else None
                    except (TypeError,ValueError):return None
                audit_payload=readable_payload(row["audit_data"]);revert_payload=readable_payload(row["revert_audit_data"])
                try:amount=Decimal(row["amount"]) if row["amount"] not in (None,"") else None
                except Exception:amount=None
                patient=patient_for_legacy(target,row["pid"])
                values=dict(service=clean(row["service"]),patient_id=patient.id if patient else None,legacy_patient_id=row["pid"],success=bool(row["success"]),action_name=clean(row["action_name"]),amount_text=clean(row["amount"]),amount=amount,ticket=clean(row["ticket"]),transaction_id=clean(row["transaction_id"]),occurred_at=row["date"],map_legacy_uuid_hex=json_value(row["map_uuid"]) if row["map_uuid"] else None,map_transaction_id=clean(row["map_transaction_id"]),reverted=bool(row["reverted"]),revert_action_name=clean(row["revert_action_name"]),revert_transaction_id=clean(row["revert_transaction_id"]),reverted_at=row["revert_date"],audit_ciphertext=json_value(row["audit_data"]),revert_audit_ciphertext=json_value(row["revert_audit_data"]),audit_payload=audit_payload,revert_audit_payload=revert_payload,payload_readable=audit_payload is not None,legacy_payload={key:json_value(value) for key,value in row.items()})
                if existing:
                    for key,value in values.items():setattr(existing,key,value)
                    stats["payment_processing_audits"]["existing"]+=1
                else:target.add(PaymentProcessingAudit(legacy_uuid_hex=legacy_uuid,**values));stats["payment_processing_audits"]["inserted"]+=1
            target.flush()
        claims=legacy.execute(text("SELECT patient_id,encounter_id,version,payer_id,status,bill_time FROM claims ORDER BY patient_id,encounter_id,version"))
        for row in claims.mappings():
            stats["claims"]["source"] += 1; key=f"{row['patient_id']}:{row['encounter_id']}:{row['version']}"
            if target.scalar(select(Claim.id).where(Claim.legacy_claim_key==key)): stats["claims"]["existing"] += 1; continue
            patient=patient_for_legacy(target,row["patient_id"]); encounter=target.scalar(select(Encounter).where(Encounter.legacy_encounter_id==row["encounter_id"])); coverage=target.scalar(select(Coverage).where(Coverage.patient_id==patient.id,Coverage.payer_id==target.scalar(select(Payer.id).where(Payer.legacy_payer_id==row["payer_id"])))) if patient and row["payer_id"] else None
            claim_charges=list(target.scalars(select(Charge).where(Charge.patient_id==patient.id,Charge.encounter_id==encounter.id,Charge.claim_id.is_(None),Charge.active.is_(True)))) if patient and encounter else []
            if not patient or not encounter or not claim_charges: stats["claims"]["rejected"] += 1; continue
            total=sum((x.unit_price*x.units for x in claim_charges),0); claim=Claim(legacy_claim_key=key,patient_id=patient.id,encounter_id=encounter.id,coverage_id=coverage.id if coverage else None,status="submitted" if row["bill_time"] else "draft",total=total,submitted_at=row["bill_time"]); target.add(claim); target.flush()
            for charge in claim_charges: charge.claim_id=claim.id
            stats["claims"]["inserted"] += 1
        if "codes" in legacy_tables:
            category_titles={row["option_id"]:clean(row["title"]) for row in legacy.execute(text("SELECT option_id,title FROM list_options WHERE list_id='superbill' AND activity=1")).mappings()}
            price_levels={row["option_id"]:clean(row["title"]) for row in legacy.execute(text("SELECT option_id,title FROM list_options WHERE list_id='pricelevel' AND activity=1 ORDER BY seq")).mappings()}
            for row in legacy.execute(text("SELECT * FROM codes ORDER BY id")).mappings():
                stats["service_codes"]["source"]+=1
                existing=target.scalar(select(ServiceCode).where(ServiceCode.legacy_code_id==row["id"]))
                if not clean(row["code"]):stats["service_codes"]["rejected"]+=1;continue
                prices=[{"level":price["pr_level"],"title":price_levels.get(price["pr_level"]),"amount":json_value(price["pr_price"])} for price in legacy.execute(text("SELECT pr_level,pr_price FROM prices WHERE pr_id=:id AND pr_selector='' ORDER BY pr_level"),{"id":row["id"]}).mappings()]
                values=dict(code_type_id=row["code_type"],code=clean(row["code"]),modifier=clean(row["modifier"]) or "",units=row["units"] or 0,description=clean(row["code_text"]) or clean(row["code"]),category_code=clean(row["superbill"]),category_title=category_titles.get(row["superbill"]),related_codes=clean(row["related_code"]),financial_reporting=bool(row["financial_reporting"]),cyp_factor=row["cyp_factor"] or 0,prices=prices,active=bool(row["active"]),legacy_payload={field:json_value(value) for field,value in row.items()})
                if existing:
                    for key,value in values.items():setattr(existing,key,value)
                    stats["service_codes"]["existing"]+=1
                else:target.add(ServiceCode(legacy_code_id=row["id"],**values));stats["service_codes"]["inserted"]+=1
        cvx_names={}
        if "codes" in legacy_tables and "code_types" in legacy_tables:
            for row in legacy.execute(text("SELECT c.code,c.code_text,c.code_text_short FROM codes c JOIN code_types ct ON ct.ct_id=c.code_type WHERE ct.ct_key='CVX' ORDER BY c.id")).mappings():
                cvx_names.setdefault(clean(row["code"]),(clean(row["code_text"]),clean(row["code_text_short"])))
        immunizations=legacy.execute(text("SELECT * FROM immunizations ORDER BY id"))
        for row in immunizations.mappings():
            stats["immunizations"]["source"]+=1
            existing=target.scalar(select(Immunization).where(Immunization.legacy_immunization_id==row["id"]))
            patient=patient_for_legacy(target,row["patient_id"]); encounter=target.scalar(select(Encounter).where(Encounter.legacy_encounter_id==row["encounter_id"])) if row["encounter_id"] else None; cvx=clean(row["cvx_code"])
            if not patient or not row["administered_date"] or not cvx: stats["immunizations"]["rejected"]+=1; continue
            amount=str(row["amount_administered"]) if row["amount_administered"] is not None else None;name=cvx_names.get(cvx,(None,None))[0] or f"CVX {cvx}"
            values=dict(patient_id=patient.id,encounter_id=encounter.id if encounter else None,administered_at=row["administered_date"],cvx_code=cvx,vaccine_name=name,manufacturer=clean(row["manufacturer"]),lot_number=clean(row["lot_number"]),route=clean(row["route"]),site=clean(row["administration_site"]),dose=amount,dose_unit=clean(row["amount_administered_unit"]),status=clean(row["completion_status"]) or "completed",refusal_reason=clean(row["refusal_reason"]),note=clean(row["note"]),legacy_payload={key:json_value(value) for key,value in row.items()})
            if existing:
                for key,value in values.items():setattr(existing,key,value)
                stats["immunizations"]["existing"]+=1
            else:
                target.add(Immunization(legacy_immunization_id=row["id"],**values));stats["immunizations"]["inserted"]+=1
        vitals=legacy.execute(text("SELECT id,pid,date,bps,bpd,weight,height,temperature,pulse,respiration,oxygen_saturation,BMI,note FROM form_vitals WHERE activity=1 ORDER BY id"))
        for row in vitals.mappings():
            stats["vitals"]["source"]+=1
            if target.scalar(select(VitalSet.id).where(VitalSet.legacy_vitals_id==row["id"])): stats["vitals"]["existing"]+=1; continue
            patient=patient_for_legacy(target,row["pid"])
            if not patient or not row["date"]: stats["vitals"]["rejected"]+=1; continue
            target.add(VitalSet(legacy_vitals_id=row["id"],patient_id=patient.id,observed_at=row["date"],systolic=row["bps"] or None,diastolic=row["bpd"] or None,weight_kg=row["weight"] or None,height_cm=row["height"] or None,temperature_c=row["temperature"] or None,heart_rate=row["pulse"] or None,respiratory_rate=row["respiration"] or None,oxygen_saturation=row["oxygen_saturation"] or None,bmi=row["BMI"] or None,note=clean(row["note"])))
            stats["vitals"]["inserted"]+=1
        pharmacies=legacy.execute(text("SELECT * FROM pharmacies ORDER BY id"))
        for row in pharmacies.mappings():
            stats["pharmacies"]["source"]+=1
            existing=target.scalar(select(Pharmacy).where(Pharmacy.legacy_pharmacy_id==row["id"]))
            values=dict(name=clean(row["name"]) or f"Pharmacy {row['id']}",email=clean(row["email"]),ncpdp=str(row["ncpdp"]) if row["ncpdp"] else None,npi=str(row["npi"]) if row["npi"] else None,transmit_method=row["transmit_method"],legacy_payload={key:json_value(value) for key,value in row.items()})
            if existing:
                for key,value in values.items():setattr(existing,key,value)
                stats["pharmacies"]["existing"]+=1
            else: target.add(Pharmacy(legacy_pharmacy_id=row["id"],**values));stats["pharmacies"]["inserted"]+=1
        target.flush()
        prescription_option_titles={}
        if "list_options" in legacy_tables:
            for row in legacy.execute(text("SELECT list_id,option_id,title FROM list_options WHERE list_id IN ('drug_units','drug_form','drug_interval') ORDER BY list_id,seq")).mappings():prescription_option_titles[(row["list_id"],str(row["option_id"]))]=clean(row["title"])
        prescriptions=legacy.execute(text("SELECT * FROM prescriptions ORDER BY id"))
        for row in prescriptions.mappings():
            stats["prescriptions"]["source"]+=1
            existing=target.scalar(select(Prescription).where(Prescription.legacy_prescription_id==row["id"]))
            patient=patient_for_legacy(target,row["patient_id"]); encounter=target.scalar(select(Encounter).where(Encounter.legacy_encounter_id==row["encounter"])) if row["encounter"] else None; pharmacy=target.scalar(select(Pharmacy).where(Pharmacy.legacy_pharmacy_id==row["pharmacy_id"])) if row["pharmacy_id"] else None
            values=dict(patient_id=patient.id if patient else None,legacy_patient_id=row["patient_id"],encounter_id=encounter.id if encounter else None,pharmacy_id=pharmacy.id if pharmacy else None,
                prescribed_at=row["date_added"],modified_at=row["date_modified"],start_date=row["start_date"],end_date=row["end_date"],drug_name=clean(row["drug"]) or "Unnamed prescription",
                rxnorm_code=clean(row["rxnorm_drugcode"]),dosage_instructions=clean(row["drug_dosage_instructions"]) or clean(row["dosage"]) or "As directed",quantity=clean(row["quantity"]),
                refills=row["refills"] or 0,substitutions_allowed=bool(row["substitute"]),indication=clean(row["indication"]),status="active" if row["active"] else "stopped",
                filled_by_legacy_id=row["filled_by_id"],provider_legacy_id=row["provider_id"],drug_legacy_id=row["drug_id"] or None,form_legacy_id=row["form"],dosage=clean(row["dosage"]),
                size=clean(row["size"]),unit_legacy_id=row["unit"],route=clean(row["route"]),interval_legacy_id=row["interval"],per_refill=row["per_refill"],filled_date=row["filled_date"],
                medication_legacy_id=row["medication"],note=clean(row["note"]),legacy_recorded_at=row["datetime"],legacy_user=clean(row["user"]),site=clean(row["site"]),
                prescription_guid=clean(row["prescriptionguid"]),erx_source=row["erx_source"] or 0,erx_uploaded=bool(row["erx_uploaded"]),erx_drug_info=clean(row["drug_info_erx"]),
                external_id=clean(row["external_id"]),prn=clean(row["prn"]),ntx=row["ntx"],rtx=row["rtx"],transaction_date=row["txDate"],usage_category=clean(row["usage_category"]),
                usage_category_title=clean(row["usage_category_title"]),request_intent=clean(row["request_intent"]),request_intent_title=clean(row["request_intent_title"]),
                diagnosis=clean(row["diagnosis"]),created_by_legacy_id=row["created_by"],updated_by_legacy_id=row["updated_by"],legacy_payload={key:json_value(value) for key,value in row.items()}|{"unit_title":prescription_option_titles.get(("drug_units",str(row["unit"]))),"form_title":prescription_option_titles.get(("drug_form",str(row["form"]))),"interval_title":prescription_option_titles.get(("drug_interval",str(row["interval"])))})
            if existing:
                for key,value in values.items():setattr(existing,key,value)
                stats["prescriptions"]["existing"]+=1
            else: target.add(Prescription(legacy_prescription_id=row["id"],**values));stats["prescriptions"]["inserted"]+=1
        products = legacy.execute(text("SELECT * FROM drugs ORDER BY drug_id"))
        for row in products.mappings():
            stats["inventory_products"]["source"] += 1
            if not clean(row["name"]): stats["inventory_products"]["rejected"] += 1; continue
            existing=target.scalar(select(InventoryProduct).where(InventoryProduct.legacy_drug_id == row["drug_id"]))
            values=dict(name=clean(row["name"]),ndc_number=clean(row["ndc_number"]),drug_code=clean(row["drug_code"]),form=clean(row["form"]),size=clean(row["size"]),unit=clean(row["unit"]),route=clean(row["route"]),cyp_factor=row["cyp_factor"] or 0,reorder_point=row["reorder_point"] or 0,max_level=row["max_level"] or 0,allow_combining=bool(row["allow_combining"]),allow_multiple=bool(row["allow_multiple"]),consumable=bool(row["consumable"]),dispensable=bool(row["dispensable"]),active=bool(row["active"]),legacy_payload={key:json_value(value) for key,value in row.items()})
            if existing:
                for key,value in values.items():setattr(existing,key,value)
                stats["inventory_products"]["existing"]+=1
            else:target.add(InventoryProduct(legacy_drug_id=row["drug_id"],**values));stats["inventory_products"]["inserted"]+=1
        target.flush()
        lots = legacy.execute(text("SELECT * FROM drug_inventory ORDER BY inventory_id"))
        for row in lots.mappings():
            stats["inventory_lots"]["source"] += 1
            if target.scalar(select(InventoryLot.id).where(InventoryLot.legacy_inventory_id == row["inventory_id"])): stats["inventory_lots"]["existing"] += 1; continue
            product = target.scalar(select(InventoryProduct).where(InventoryProduct.legacy_drug_id == row["drug_id"]))
            if not product: stats["inventory_lots"]["rejected"] += 1; continue
            target.add(InventoryLot(legacy_inventory_id=row["inventory_id"], product_id=product.id, lot_number=clean(row["lot_number"]), expiration=row["expiration"], manufacturer=clean(row["manufacturer"]), warehouse_id=clean(row["warehouse_id"]) or "", vendor_id=row["vendor_id"] or None, on_hand=row["on_hand"] or 0, destroyed_at=row["destroy_date"], destruction_method=clean(row["destroy_method"]), destruction_witness=clean(row["destroy_witness"]), destruction_notes=clean(row["destroy_notes"]), legacy_payload={key: json_value(value) for key, value in row.items()})); stats["inventory_lots"]["inserted"] += 1
        target.flush()
        transaction_types = {1: "dispense", 2: "purchase", 3: "return", 4: "transfer", 5: "adjustment", 7: "consumption"}
        transactions = legacy.execute(text("SELECT * FROM drug_sales ORDER BY sale_id"))
        for row in transactions.mappings():
            stats["inventory_transactions"]["source"] += 1
            if target.scalar(select(InventoryTransaction.id).where(InventoryTransaction.legacy_sale_id == row["sale_id"])): stats["inventory_transactions"]["existing"] += 1; continue
            product=target.scalar(select(InventoryProduct).where(InventoryProduct.legacy_drug_id==row["drug_id"])); lot=target.scalar(select(InventoryLot).where(InventoryLot.legacy_inventory_id==row["inventory_id"])) if row["inventory_id"] else None; destination=target.scalar(select(InventoryLot).where(InventoryLot.legacy_inventory_id==row["xfer_inventory_id"])) if row["xfer_inventory_id"] else None; patient=patient_for_legacy(target,row["pid"]) if row["pid"] else None; encounter=target.scalar(select(Encounter).where(Encounter.legacy_encounter_id==row["encounter"])) if row["encounter"] else None; prescription=target.scalar(select(Prescription).where(Prescription.legacy_prescription_id==row["prescription_id"])) if row["prescription_id"] else None
            if not product: stats["inventory_transactions"]["rejected"] += 1; continue
            target.add(InventoryTransaction(legacy_sale_id=row["sale_id"], product_id=product.id, lot_id=lot.id if lot else None, destination_lot_id=destination.id if destination else None, patient_id=patient.id if patient else None, encounter_id=encounter.id if encounter else None, prescription_id=prescription.id if prescription else None, transaction_type=transaction_types.get(row["trans_type"], f"legacy-{row['trans_type']}"), occurred_on=row["sale_date"], quantity=row["quantity"], fee=row["fee"], billed=bool(row["billed"]), actor_name=clean(row["user"]), notes=clean(row["notes"]), legacy_payload={key: json_value(value) for key, value in row.items()})); stats["inventory_transactions"]["inserted"] += 1
        if "form_care_plan" in legacy_tables:
            source_rows=list(legacy.execute(text("SELECT * FROM form_care_plan")).mappings())
            for row,payload,row_key in stable_legacy_row_keys(source_rows):
                stats["care_plans"]["source"]+=1;stats["care_plan_outcomes"]["source"]+=1
                plan=target.scalar(select(CarePlan).where(CarePlan.legacy_form_id==row["id"],CarePlan.legacy_row_key==row_key))
                if plan:stats["care_plans"]["existing"]+=1
                patient=patient_for_legacy(target,row["pid"]);encounter=target.scalar(select(Encounter).where(Encounter.legacy_encounter_id==row["encounter"]))
                if not plan and (not patient or not encounter):stats["care_plans"]["rejected"]+=1;stats["care_plan_outcomes"]["rejected"]+=1;continue
                recorded=plan.recorded_at if plan else legacy_datetime(row["date"],encounter.occurred_at);raw_status=clean(row["plan_status"]) or "draft"
                if not plan:
                    plan=CarePlan(legacy_form_id=row["id"],legacy_row_key=row_key,patient_id=patient.id,encounter_id=encounter.id,recorded_at=recorded,code=clean(row["code"]),code_text=clean(row["codetext"]),description=clean(row["description"]) or "",external_id=clean(row["external_id"]),plan_type=clean(row["care_plan_type"]),note_related_to=clean(row["note_related_to"]),ends_at=legacy_datetime(row["date_end"]),reason_code=clean(row["reason_code"]),reason_description=clean(row["reason_description"]),reason_recorded_at=legacy_datetime(row["reason_date_low"]),reason_ends_at=legacy_datetime(row["reason_date_high"]),reason_status=clean(row["reason_status"]),status=raw_status[:32],target_date=legacy_datetime(row["proposed_date"]),engagement_category=clean(row["plan_engagement_category"]),active=bool(row["activity"]),legacy_payload=payload);target.add(plan);target.flush();stats["care_plans"]["inserted"]+=1
                outcome=target.scalar(select(CarePlanOutcome.id).where(CarePlanOutcome.care_plan_id==plan.id,CarePlanOutcome.source=="legacy"))
                if outcome:stats["care_plan_outcomes"]["existing"]+=1;continue
                achievement={"active":"in-progress","on-hold":"sustaining","completed":"achieved","cancelled":"not-achieved","canceled":"not-achieved"}.get(raw_status.lower())
                target.add(CarePlanOutcome(care_plan_id=plan.id,event_type="status",plan_status=raw_status[:32],achievement_status=achievement,note="Initial status preserved from form_care_plan; no separate legacy outcome was asserted.",recorded_at=recorded,source="legacy",legacy_payload=payload));stats["care_plan_outcomes"]["inserted"]+=1
            target.flush()
        # OpenEMR's `forms` registry points to both core and installed/custom form tables.
        # Reflecting only tables that actually exist preserves every registered form payload.
        forms = legacy.execute(text("SELECT * FROM forms ORDER BY id"))
        known_types = {"soap": "soap", "ros": "ros", "physical_exam": "physical_exam", "clinic_note": "clinic_note"}
        for row in forms.mappings():
            stats["clinical_forms"]["source"] += 1; legacy_key = f"forms:{row['id']}"
            existing=target.scalar(select(ClinicalForm).where(ClinicalForm.legacy_form_key == legacy_key))
            if existing:
                existing.source_formdir=clean(row["formdir"]);existing.registry_payload={key:json_value(value) for key,value in row.items()};stats["clinical_forms"]["existing"] += 1;continue
            patient = patient_for_legacy(target, row["pid"]); encounter = target.scalar(select(Encounter).where(Encounter.legacy_encounter_id == row["encounter"]))
            formdir = clean(row["formdir"]) or "custom"; table_name = f"form_{formdir}"
            if not patient or not encounter or row["deleted"] or table_name not in legacy_tables: stats["clinical_forms"]["rejected"] += 1; continue
            columns = {item["name"] for item in inspect(source).get_columns(table_name)}
            key_column = "forms_id" if "forms_id" in columns else "id"
            payload_rows = legacy.execute(text(f"SELECT * FROM `{table_name}` WHERE `{key_column}`=:form_id"), {"form_id": row["form_id"] if key_column == "id" else row["id"]}).mappings().all()
            if not payload_rows: stats["clinical_forms"]["rejected"] += 1; continue
            content = {"rows": [{key: json_value(value) for key, value in payload.items()} for payload in payload_rows]}
            if formdir == "soap": content = {key: json_value(payload_rows[0].get(key)) for key in ("subjective", "objective", "assessment", "plan")}
            target.add(ClinicalForm(legacy_form_key=legacy_key, patient_id=patient.id, encounter_id=encounter.id, form_type=known_types.get(formdir, "custom"), title=clean(row["form_name"]) or formdir.replace("_", " ").title(), content=content, status="signed" if row["authorized"] else "draft", authored_at=row["date"] or encounter.occurred_at,source_formdir=formdir,registry_payload={key:json_value(value) for key,value in row.items()}))
            stats["clinical_forms"]["inserted"] += 1
        target.flush()
        if "clinical_notes_documents" in legacy_tables and "form_clinical_notes" in legacy_tables:
            rows=legacy.execute(text("""SELECT l.id,l.clinical_note_id,l.document_id,l.created_at,l.created_by,f.id AS registry_id FROM clinical_notes_documents l JOIN form_clinical_notes n ON n.id=l.clinical_note_id JOIN forms f ON f.form_id=n.form_id AND f.formdir='clinical_notes' AND f.pid=n.pid AND f.encounter=n.encounter AND f.deleted=0 ORDER BY l.id"""))
            for row in rows.mappings():
                stats["clinical_form_document_links"]["source"]+=1
                if target.scalar(select(ClinicalFormDocumentLink.id).where(ClinicalFormDocumentLink.legacy_link_id==row["id"])):stats["clinical_form_document_links"]["existing"]+=1;continue
                form=target.scalar(select(ClinicalForm).where(ClinicalForm.legacy_form_key==f"forms:{row['registry_id']}"));document=target.scalar(select(Document).where(Document.legacy_document_id==row["document_id"]))
                if not form or not document or form.patient_id!=document.patient_id:stats["clinical_form_document_links"]["rejected"]+=1;continue
                target.add(ClinicalFormDocumentLink(legacy_link_id=row["id"],legacy_clinical_note_id=row["clinical_note_id"],clinical_form_id=form.id,document_id=document.id,created_at=legacy_datetime(row["created_at"],datetime.now(timezone.utc)),created_by_name=clean(row["created_by"])));stats["clinical_form_document_links"]["inserted"]+=1
            target.flush()
        if "clinical_notes_procedure_results" in legacy_tables and "form_clinical_notes" in legacy_tables:
            rows=legacy.execute(text("""SELECT l.id,l.clinical_note_id,l.procedure_result_id,l.created_at,l.created_by,f.id AS registry_id FROM clinical_notes_procedure_results l JOIN form_clinical_notes n ON n.id=l.clinical_note_id JOIN forms f ON f.form_id=n.form_id AND f.formdir='clinical_notes' AND f.pid=n.pid AND f.encounter=n.encounter AND f.deleted=0 ORDER BY l.id"""))
            for row in rows.mappings():
                stats["clinical_form_result_links"]["source"]+=1
                if target.scalar(select(ClinicalFormResultLink.id).where(ClinicalFormResultLink.legacy_link_id==row["id"])):stats["clinical_form_result_links"]["existing"]+=1;continue
                form=target.scalar(select(ClinicalForm).where(ClinicalForm.legacy_form_key==f"forms:{row['registry_id']}"));result=target.scalar(select(LabResult).where(LabResult.legacy_result_id==row["procedure_result_id"]));order=target.get(LabOrder,result.order_id) if result else None
                if not form or not result or not order or form.patient_id!=order.patient_id:stats["clinical_form_result_links"]["rejected"]+=1;continue
                target.add(ClinicalFormResultLink(legacy_link_id=row["id"],legacy_clinical_note_id=row["clinical_note_id"],clinical_form_id=form.id,lab_result_id=result.id,created_at=legacy_datetime(row["created_at"],datetime.now(timezone.utc)),created_by_name=clean(row["created_by"])));stats["clinical_form_result_links"]["inserted"]+=1
            target.flush()
        if "esign_signatures" in legacy_tables:
            legacy_signatures = legacy.execute(text("""SELECT e.id,e.tid,e.`table`,e.uid,e.datetime,e.is_lock,e.amendment,e.hash,e.signature_hash,u.fname,u.lname,u.title FROM esign_signatures e LEFT JOIN users u ON u.id=e.uid ORDER BY e.tid,e.datetime,e.id"""))
            for row in legacy_signatures.mappings():
                stats["clinical_signatures"]["source"] += 1
                if target.scalar(select(ClinicalSignature.id).where(ClinicalSignature.legacy_signature_id == row["id"])): stats["clinical_signatures"]["existing"] += 1; continue
                signer_name = " ".join(filter(None,(clean(row["fname"]),clean(row["lname"])))) or f"Legacy user {row['uid']}"
                attestation = "Imported OpenEMR electronic signature evidence."
                form = target.scalar(select(ClinicalForm).where(ClinicalForm.legacy_form_key == f"forms:{row['tid']}")) if row["table"] == "forms" else None
                encounter = target.scalar(select(Encounter).where(Encounter.legacy_encounter_id == row["tid"])) if row["table"] == "form_encounter" else None
                if not form and not encounter: stats["clinical_signatures"]["rejected"] += 1; continue
                target_type="form" if form else "encounter"; encounter=encounter or target.get(Encounter,form.encounter_id); form_id=form.id if form else None
                previous = target.scalar(select(ClinicalSignature.signature_hash).where(ClinicalSignature.target_type==target_type,ClinicalSignature.form_id==form_id if form else ClinicalSignature.encounter_id==encounter.id).order_by(ClinicalSignature.signed_at.desc(),ClinicalSignature.id.desc()).limit(1))
                signed_at = row["datetime"] or (form.authored_at if form else encounter.occurred_at); content_digest=clinical_form_hash(form,target) if form else encounter_hash(target,encounter)
                evidence = ({"form_uuid":form.uuid,"encounter_id":encounter.id} if form else {"encounter_uuid":encounter.uuid}) | {"signer_id":None,"signer_name":signer_name,"signer_role":clean(row["title"]),"signed_at":signed_at,"auth_method":"legacy-import","is_lock":bool(row["is_lock"]),"attestation":attestation,"amendment":clean(row["amendment"]),"content_hash":content_digest,"previous_signature_hash":previous}
                target.add(ClinicalSignature(legacy_signature_id=row["id"],target_type=target_type,form_id=form_id,encounter_id=encounter.id,signer_name=signer_name,signer_role=clean(row["title"]),signed_at=signed_at,auth_method="legacy-import",is_lock=bool(row["is_lock"]),attestation=attestation,amendment=clean(row["amendment"]),content_hash=content_digest,previous_signature_hash=previous,signature_hash=signature_hash(evidence),legacy_content_hash=clean(row["hash"]),legacy_signature_hash=clean(row["signature_hash"]),legacy_payload={key:json_value(value) for key,value in row.items()}))
                stats["clinical_signatures"]["inserted"] += 1
                target.flush()

        # Portal password verifiers belong to the legacy authentication system and
        # are deliberately not accepted as modern credentials. Every imported
        # account receives an unguessable placeholder and must reset its password.
        if "patient_access_onsite" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM patient_access_onsite ORDER BY id")).mappings():
                stats["portal_accounts"]["source"] += 1
                if target.scalar(select(PortalAccount.id).where(PortalAccount.legacy_access_id == row["id"])):
                    stats["portal_accounts"]["existing"] += 1; continue
                patient = patient_for_legacy(target, row["pid"])
                username = clean(row.get("portal_username")) or clean(row.get("portal_login_username"))
                if not patient or not username or target.scalar(select(PortalAccount.id).where(PortalAccount.username == username)):
                    stats["portal_accounts"]["rejected"] += 1; continue
                safe_payload = {key: json_value(value) for key, value in row.items() if key not in {"portal_pwd", "portal_onetime"}}
                safe_payload["legacy_credentials_discarded"] = True
                target.add(PortalAccount(legacy_access_id=row["id"], patient_id=patient.id, username=username, email=patient.email, display_name=f"{patient.first_name} {patient.last_name}", identity_type="patient", password_hash=password_hash.hash(secrets.token_urlsafe(32)), active=patient.portal_allowed, force_password_reset=True, legacy_payload=safe_payload))
                stats["portal_accounts"]["inserted"] += 1
            target.flush()

        if "pnotes" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM pnotes ORDER BY id")).mappings():
                stats["message_threads"]["source"] += 1; stats["secure_messages"]["source"] += 1
                legacy_key = f"pnotes:{row['id']}"
                if target.scalar(select(MessageThread.id).where(MessageThread.legacy_thread_key == legacy_key)):
                    stats["message_threads"]["existing"] += 1; stats["secure_messages"]["existing"] += 1; continue
                patient = patient_for_legacy(target, row.get("pid"))
                body = clean(row.get("body"))
                if not patient or not body:
                    stats["message_threads"]["rejected"] += 1; stats["secure_messages"]["rejected"] += 1; continue
                created = row.get("date") or datetime.now(timezone.utc)
                thread = MessageThread(legacy_thread_key=legacy_key, patient_id=patient.id, subject=clean(row.get("title")) or "Legacy patient note", status="closed" if row.get("deleted") else "open", created_at=created, updated_at=created, legacy_payload={key: json_value(value) for key, value in row.items()})
                target.add(thread); target.flush()
                target.add(SecureMessage(legacy_message_key=legacy_key, thread_id=thread.id, sender_kind="legacy-staff", sender_name=clean(row.get("user")), body=body, created_at=created, legacy_payload={key: json_value(value) for key, value in row.items()}))
                stats["message_threads"]["inserted"] += 1; stats["secure_messages"]["inserted"] += 1

        if "onsite_mail" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM onsite_mail ORDER BY id")).mappings():
                stats["message_threads"]["source"] += 1; stats["secure_messages"]["source"] += 1
                legacy_key = f"onsite_mail:{row['id']}"
                if target.scalar(select(MessageThread.id).where(MessageThread.legacy_thread_key == legacy_key)):
                    stats["message_threads"]["existing"] += 1; stats["secure_messages"]["existing"] += 1; continue
                owner = row.get("owner")
                patient = patient_for_legacy(target, int(owner)) if str(owner or "").isdigit() else None
                body = clean(row.get("body"))
                if not patient or not body:
                    stats["message_threads"]["rejected"] += 1; stats["secure_messages"]["rejected"] += 1; continue
                created = row.get("date") or row.get("date_created") or datetime.now(timezone.utc)
                thread = MessageThread(legacy_thread_key=legacy_key, patient_id=patient.id, subject=clean(row.get("subject")) or clean(row.get("title")) or "Legacy portal message", status="closed" if row.get("deleted") else "open", created_at=created, updated_at=created, legacy_payload={key: json_value(value) for key, value in row.items()})
                target.add(thread); target.flush()
                target.add(SecureMessage(legacy_message_key=legacy_key, thread_id=thread.id, sender_kind="legacy", sender_name=clean(row.get("sender_name")) or clean(row.get("sender")), body=body, created_at=created, legacy_payload={key: json_value(value) for key, value in row.items()}))
                stats["message_threads"]["inserted"] += 1; stats["secure_messages"]["inserted"] += 1

        if "onsite_messages" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM onsite_messages ORDER BY id")).mappings():
                stats["message_threads"]["source"] += 1; stats["secure_messages"]["source"] += 1
                legacy_key = f"onsite_messages:{row['id']}"
                if target.scalar(select(MessageThread.id).where(MessageThread.legacy_thread_key == legacy_key)):
                    stats["message_threads"]["existing"] += 1; stats["secure_messages"]["existing"] += 1; continue
                account = target.scalar(select(PortalAccount).where(PortalAccount.username == row.get("username")))
                body = clean(row.get("message"))
                if not account or not body:
                    stats["message_threads"]["rejected"] += 1; stats["secure_messages"]["rejected"] += 1; continue
                created = row.get("date") or datetime.now(timezone.utc)
                thread = MessageThread(legacy_thread_key=legacy_key, patient_id=account.patient_id, subject="Legacy portal notification", created_at=created, updated_at=created, legacy_payload={key: json_value(value) for key, value in row.items()})
                target.add(thread); target.flush()
                target.add(SecureMessage(legacy_message_key=legacy_key, thread_id=thread.id, sender_kind="legacy", sender_name=clean(row.get("sender_id")), body=body, created_at=created, legacy_payload={key: json_value(value) for key, value in row.items()}))
                stats["message_threads"]["inserted"] += 1; stats["secure_messages"]["inserted"] += 1

        if "form_taskman" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM form_taskman ORDER BY ID")).mappings():
                stats["clinical_tasks"]["source"] += 1
                if target.scalar(select(ClinicalTask.id).where(ClinicalTask.legacy_task_id == row["ID"])):
                    stats["clinical_tasks"]["existing"] += 1; continue
                patient = patient_for_legacy(target, row.get("PATIENT_ID"))
                encounter = target.scalar(select(Encounter).where(Encounter.legacy_encounter_id == row.get("ENC_ID"))) if row.get("ENC_ID") else None
                if not patient:
                    stats["clinical_tasks"]["rejected"] += 1; continue
                completed = bool(row.get("COMPLETED"))
                target.add(ClinicalTask(legacy_task_id=row["ID"], patient_id=patient.id, encounter_id=encounter.id if encounter else None, method=clean(row.get("METHOD")) or "legacy", comment=clean(row.get("COMMENT")), status="completed" if completed else "open", due_at=row.get("REQ_DATE"), completed_at=row.get("COMPLETED_DATE") if completed else None, legacy_payload={key: json_value(value) for key, value in row.items()}))
                stats["clinical_tasks"]["inserted"] += 1

        if "email_queue" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM email_queue ORDER BY id")).mappings():
                stats["communication_deliveries"]["source"] += 1
                if target.scalar(select(CommunicationDelivery.id).where(CommunicationDelivery.legacy_email_id == row["id"])):
                    stats["communication_deliveries"]["existing"] += 1; continue
                recipient = clean(row.get("recipient")) or clean(row.get("to"))
                if not recipient:
                    stats["communication_deliveries"]["rejected"] += 1; continue
                sent_at = row.get("datetime_sent") if row.get("sent") else None
                error = clean(row.get("error_message")) if row.get("error") else None
                delivery_status = "sent" if sent_at else "failed" if error else "pending"
                target.add(CommunicationDelivery(legacy_email_id=row["id"], channel="email", recipient=recipient, subject=clean(row.get("subject")) or "Legacy message", body=clean(row.get("body")) or "", template_name=clean(row.get("template_name")), status=delivery_status, queued_at=row.get("datetime_queued") or datetime.now(timezone.utc), sent_at=sent_at, failed_at=row.get("datetime_error") if error else None, error_message=error, legacy_payload={key: json_value(value) for key, value in row.items()}))
                stats["communication_deliveries"]["inserted"] += 1

        if "chart_tracker" in legacy_tables:
            user_names = {}
            if "users" in legacy_tables:
                for legacy_user in legacy.execute(text("SELECT id, username, fname, mname, lname FROM users ORDER BY id")).mappings():
                    display = " ".join(filter(None, (clean(legacy_user.get("fname")), clean(legacy_user.get("mname")), clean(legacy_user.get("lname")))))
                    user_names[legacy_user["id"]] = display or clean(legacy_user.get("username"))
            for row in legacy.execute(text("SELECT ct_pid, ct_when, ct_userid, ct_location FROM chart_tracker ORDER BY ct_pid, ct_when")).mappings():
                stats["chart_location_events"]["source"] += 1
                occurred = row.get("ct_when")
                key = f'{row.get("ct_pid")}:{occurred.isoformat() if occurred else "missing"}'
                if target.scalar(select(ChartLocationEvent.id).where(ChartLocationEvent.legacy_chart_tracker_key == key)):
                    stats["chart_location_events"]["existing"] += 1; continue
                patient = patient_for_legacy(target, row.get("ct_pid"))
                if not patient or not occurred:
                    stats["chart_location_events"]["rejected"] += 1; continue
                location = clean(row.get("ct_location")); legacy_user_id = row.get("ct_userid") or None
                destination = "location" if location else "user" if legacy_user_id else "returned"
                target.add(ChartLocationEvent(
                    legacy_chart_tracker_key=key, patient_id=patient.id, destination_type=destination,
                    location=location, legacy_custodian_user_id=legacy_user_id,
                    custodian_name=user_names.get(legacy_user_id), occurred_at=occurred,
                    legacy_payload={field: json_value(value) for field, value in row.items()},
                ))
                stats["chart_location_events"]["inserted"] += 1

        external_users = {}
        if "users" in legacy_tables and ({"external_encounters", "external_procedures"} & legacy_tables):
            for row in legacy.execute(text("SELECT id, username, fname, mname, lname, organization FROM users ORDER BY id")).mappings():
                display = " ".join(filter(None, (clean(row.get("fname")), clean(row.get("mname")), clean(row.get("lname")))))
                external_users[str(row["id"])] = {"name": display or clean(row.get("username")), "organization": clean(row.get("organization"))}
        if "external_encounters" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM external_encounters ORDER BY ee_id")).mappings():
                stats["external_encounters"]["source"] += 1
                if target.scalar(select(ExternalEncounter.id).where(ExternalEncounter.legacy_external_encounter_id == row["ee_id"])):
                    stats["external_encounters"]["existing"] += 1; continue
                patient = patient_for_legacy(target, row.get("ee_pid")); occurred = row.get("ee_date")
                if not patient or not occurred:
                    stats["external_encounters"]["rejected"] += 1; continue
                provider = external_users.get(str(row.get("ee_provider_id") or ""), {})
                facility = external_users.get(str(row.get("ee_facility_id") or ""), {})
                target.add(ExternalEncounter(legacy_external_encounter_id=row["ee_id"], patient_id=patient.id, occurred_on=occurred, diagnosis=clean(row.get("ee_encounter_diagnosis")), provider_name=provider.get("name"), facility_name=facility.get("organization") or facility.get("name"), legacy_provider_id=clean(row.get("ee_provider_id")), legacy_facility_id=clean(row.get("ee_facility_id")), external_id=clean(row.get("ee_external_id")), legacy_payload={key: json_value(value) for key, value in row.items()}))
                stats["external_encounters"]["inserted"] += 1
        if "external_procedures" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM external_procedures ORDER BY ep_id")).mappings():
                stats["external_procedures"]["source"] += 1
                if target.scalar(select(ExternalProcedure.id).where(ExternalProcedure.legacy_external_procedure_id == row["ep_id"])):
                    stats["external_procedures"]["existing"] += 1; continue
                patient = patient_for_legacy(target, row.get("ep_pid")); occurred = row.get("ep_date")
                if not patient or not occurred:
                    stats["external_procedures"]["rejected"] += 1; continue
                facility = external_users.get(str(row.get("ep_facility_id") or ""), {})
                target.add(ExternalProcedure(legacy_external_procedure_id=row["ep_id"], patient_id=patient.id, occurred_on=occurred, code_system=clean(row.get("ep_code_type")), code=clean(row.get("ep_code")), code_text=clean(row.get("ep_code_text")), legacy_encounter_id=row.get("ep_encounter"), facility_name=facility.get("organization") or facility.get("name"), legacy_facility_id=clean(row.get("ep_facility_id")), external_id=clean(row.get("ep_external_id")), legacy_payload={key: json_value(value) for key, value in row.items()}))
                stats["external_procedures"]["inserted"] += 1

        if "transactions" in legacy_tables:
            for row in legacy.execute(text("SELECT * FROM transactions ORDER BY id")).mappings():
                stats["patient_transactions"]["source"]+=1;patient=patient_for_legacy(target,row["pid"])
                if target.scalar(select(PatientTransaction.id).where(PatientTransaction.legacy_transaction_id==row["id"])):stats["patient_transactions"]["existing"]+=1;continue
                if not patient:stats["patient_transactions"]["rejected"]+=1;continue
                payload={key:json_value(value) for key,value in row.items()};target.add(PatientTransaction(legacy_transaction_id=row["id"],patient_id=patient.id,title=clean(row.get("title")) or f"Transaction {row['id']}",occurred_at=legacy_datetime(row.get("date"),datetime.now(timezone.utc)),body=clean(row.get("body")),legacy_payload=payload));stats["patient_transactions"]["inserted"]+=1
        if "transactions" in legacy_tables and "lbt_data" in legacy_tables:
            referral_users = {}
            if "users" in legacy_tables:
                for legacy_user in legacy.execute(text("SELECT id, username, fname, mname, lname, organization FROM users ORDER BY id")).mappings():
                    display = " ".join(filter(None, (clean(legacy_user.get("fname")), clean(legacy_user.get("mname")), clean(legacy_user.get("lname")))))
                    referral_users[legacy_user["id"]] = {
                        "name": display or clean(legacy_user.get("username")),
                        "organization": clean(legacy_user.get("organization")),
                    }
            referral_sql="""SELECT t.id,t.pid,t.date,MAX(CASE WHEN d.field_id='refer_date' THEN d.field_value END) refer_date,MAX(CASE WHEN d.field_id='reply_date' THEN d.field_value END) reply_date,MAX(CASE WHEN d.field_id='body' THEN d.field_value END) body,MAX(CASE WHEN d.field_id='refer_to' THEN d.field_value END) refer_to,MAX(CASE WHEN d.field_id='refer_from' THEN d.field_value END) refer_from,MAX(CASE WHEN d.field_id='reply_init_diag' THEN d.field_value END) reply_text FROM transactions t JOIN lbt_data d ON d.form_id=t.id WHERE t.title='LBTref' GROUP BY t.id,t.pid,t.date ORDER BY t.id"""
            for row in legacy.execute(text(referral_sql)).mappings():
                stats["referrals"]["source"]+=1
                if target.scalar(select(Referral.id).where(Referral.legacy_transaction_id==row["id"])):stats["referrals"]["existing"]+=1;continue
                patient=patient_for_legacy(target,row["pid"]);referred=legacy_datetime(row["refer_date"]);replied=legacy_datetime(row["reply_date"]);to_id=int(row["refer_to"]) if str(row["refer_to"] or "").isdigit() else None;from_id=int(row["refer_from"]) if str(row["refer_from"] or "").isdigit() else None;recipient=target.scalar(select(Practitioner).where(Practitioner.legacy_user_id==to_id)) if to_id else None;referrer=target.scalar(select(Practitioner).where(Practitioner.legacy_user_id==from_id)) if from_id else None
                if not patient or not referred or not clean(row["body"]):stats["referrals"]["rejected"]+=1;continue
                recipient_details = referral_users.get(to_id, {})
                recipient_name=" ".join(filter(None,(recipient.first_name,recipient.last_name))) if recipient else recipient_details.get("name") or f"Legacy user {to_id}" if to_id else "External referral"
                legacy_fields = {
                    item["field_id"]: json_value(item["field_value"])
                    for item in legacy.execute(text("SELECT field_id, field_value FROM lbt_data WHERE form_id=:form_id ORDER BY field_id"), {"form_id": row["id"]}).mappings()
                }
                target.add(Referral(legacy_transaction_id=row["id"],patient_id=patient.id,facility_id=referrer.primary_facility_id if referrer else None,referring_practitioner_id=referrer.id if referrer else None,recipient_practitioner_id=recipient.id if recipient else None,legacy_referring_user_id=from_id,legacy_recipient_user_id=to_id,recipient_name=recipient_name,recipient_organization=recipient_details.get("organization"),referred_at=referred,reason=clean(row["body"]),status="completed" if replied else "requested",replied_at=replied,reply=clean(row["reply_text"]),legacy_fields=legacy_fields));stats["referrals"]["inserted"]+=1

        if "background_services" in legacy_tables:
            for row in legacy.execute(text("SELECT name, title, active, running, next_run, execute_interval, function, require_once, sort_order, lock_expires_at FROM background_services ORDER BY sort_order, name")).mappings():
                stats["background_services"]["source"] += 1
                if target.scalar(select(BackgroundService.id).where(BackgroundService.name==row["name"])):
                    stats["background_services"]["existing"] += 1; continue
                if not clean(row.get("name")) or not clean(row.get("title")) or not row.get("next_run") or not clean(row.get("function")):
                    stats["background_services"]["rejected"] += 1; continue
                target.add(BackgroundService(name=clean(row["name"]),title=clean(row["title"]),active=bool(row["active"]),running_state=row["running"],next_run=row["next_run"],execute_interval_minutes=row["execute_interval"] or 0,handler=clean(row["function"]),legacy_include=clean(row.get("require_once")),sort_order=row["sort_order"] or 100,lock_expires_at=row.get("lock_expires_at"),legacy_payload={field:json_value(value) for field,value in row.items()}))
                stats["background_services"]["inserted"] += 1
        if "ip_tracking" in legacy_tables:
            for row in legacy.execute(text("SELECT ip_string,total_ip_login_fail_counter,ip_login_fail_counter,ip_last_login_fail,ip_force_block,ip_no_prevent_timing_attack FROM ip_tracking ORDER BY id")).mappings():
                stats["ip_login_trackers"]["source"]+=1
                if target.scalar(select(IpLoginTracker.id).where(IpLoginTracker.ip_string==row["ip_string"])):stats["ip_login_trackers"]["existing"]+=1;continue
                if not clean(row["ip_string"]):stats["ip_login_trackers"]["rejected"]+=1;continue
                target.add(IpLoginTracker(ip_string=clean(row["ip_string"]),total_failed_logins=row["total_ip_login_fail_counter"] or 0,applicable_failed_logins=row["ip_login_fail_counter"] or 0,last_failed_login=row["ip_last_login_fail"],force_block=bool(row["ip_force_block"]),skip_timing_protection=bool(row["ip_no_prevent_timing_attack"])))
                stats["ip_login_trackers"]["inserted"]+=1
        stats["patient_demographic_reconciliation"] = reconcile_patient_demographics(patient_rows, target)
        if commit: target.commit()
        else: target.rollback()
    stats["mode"] = "committed" if commit else "dry-run"
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--source", required=True); parser.add_argument("--commit", action="store_true")
    args = parser.parse_args(); print(json.dumps(run(args.source, args.commit), indent=2))
