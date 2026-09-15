from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from itertools import product

from fastapi import HTTPException
from sqlalchemy import func, literal, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AmcTrackingEvent, Appointment, AuditEvent, AuditEventSeal, BackgroundService, BillingCodeType, ChartLocationEvent, Charge, ClinicalForm, ClinicalItem, ClinicalRuleLog, CommunicationDelivery, Coverage, Encounter, ExternalEncounter, ExternalProcedure, Facility, FrontOfficePayment, IdentityAuditEvent, Immunization, InventoryLot, InventoryProduct, InventoryTransaction, IpLoginTracker, LabOrder, LabResult, MessageThread, Patient, PatientEducationResource, PatientFlowEpisode, PatientFlowEvent, PatientProviderAssignment, Payer, PaymentProcessingAudit, Pharmacy, Practitioner, Prescription, ProcedureOrderLine, ReceivableActivity, ReceivableSession, Referral, RegulatoryMetricEvent, ReportRun, SecureMessage, ServiceCode, SocialHistory, SyndromicSubmission, User, audit_event_checksum
from .access import facility_scope, warehouse_scope
from .quality_reports import quality_report

REPORT_PATHS = [
    "amc_full_report", "amc_tracking", "appointments_report", "appt_encounter_report", "audit_log_tamper_report", "background_services", "cdr_log", "chart_location_activity", "charts_checked_out", "clinical_reports", "collections_report", "cqm", "criteria.tab", "custom_report_range", "daily_summary_report", "destroyed_drugs_report", "direct_message_log", "encounters_report", "external_data", "front_receipts_report", "immunization_report", "insurance_allocation_report", "inventory_activity", "inventory_list", "inventory_transactions", "ip_tracker", "ippf_cyp_report", "ippf_daily", "ippf_statistics", "message_list", "non_reported", "pat_ledger", "patient_edu_web_lookup", "patient_flow_board_report", "patient_list", "patient_list_creation", "payment_processing_report", "prepayment_balance_report", "prescriptions_report", "receipts_by_method_report", "referrals_report", "report.script", "report_results", "rwt_2026_report", "sales_by_item", "services_by_category", "svc_code_financial_report", "unique_seen_patients_report",
]
IMPLEMENTED = {"amc_full_report", "amc_tracking", "appointments_report", "appt_encounter_report", "audit_log_tamper_report", "background_services", "cdr_log", "chart_location_activity", "charts_checked_out", "clinical_reports", "collections_report", "cqm", "custom_report_range", "daily_summary_report", "destroyed_drugs_report", "direct_message_log", "encounters_report", "external_data", "front_receipts_report", "immunization_report", "insurance_allocation_report", "inventory_activity", "inventory_list", "inventory_transactions", "ip_tracker", "ippf_cyp_report", "ippf_daily", "ippf_statistics", "message_list", "non_reported", "pat_ledger", "patient_edu_web_lookup", "patient_flow_board_report", "patient_list", "patient_list_creation", "payment_processing_report", "prepayment_balance_report", "prescriptions_report", "receipts_by_method_report", "referrals_report", "report_results", "rwt_2026_report", "sales_by_item", "services_by_category", "svc_code_financial_report", "unique_seen_patients_report"}
PERMISSION_OVERRIDES = {
    "appointments_report":"patients:appt:read", "appt_encounter_report":"acct:rep_a:read",
    "audit_log_tamper_report":"admin:super:read", "background_services":"admin:super:read",
    "cdr_log":"patients:med:read",
    "collections_report":"acct:rep_a:read", "custom_report_range":"encounters:coding_a:read",
    "chart_location_activity":"patients:demo:read", "charts_checked_out":"patients:demo:read",
    "daily_summary_report":"acct:rep_a:read", "direct_message_log":"admin:super:read",
    "external_data":"patients:med:read",
    "encounters_report":"encounters:coding_a:read", "front_receipts_report":"acct:rep_a:read",
    "insurance_allocation_report":"acct:rep_a:read", "inventory_activity":"acct:rep:read",
    "inventory_list":"inventory:reporting:read", "inventory_transactions":"acct:rep:read",
    "ip_tracker":"admin:super:read", "ippf_cyp_report":"acct:rep:read", "ippf_daily":"acct:rep:read",
    "ippf_statistics":"acct:rep:read", "payment_processing_report":"acct:rep_a:read",
    "message_list":"patients:med:read", "prepayment_balance_report":"acct:rep_a:read", "prescriptions_report":"patients:rx:read",
    "receipts_by_method_report":"acct:rep_a:read", "rwt_2026_report":"admin:super:read",
    "sales_by_item":"acct:rep:read", "svc_code_financial_report":"acct:rep_a:read", "pat_ledger":"acct:rep:read",
}


def category_for(key: str) -> str:
    if any(term in key for term in ("inventory", "drug", "sales_by_item")): return "inventory"
    if any(term in key for term in ("collection", "receipt", "payment", "ledger", "financial", "allocation", "prepayment", "services_by")): return "financial"
    if any(term in key for term in ("audit", "background", "ip_tracker", "external_data")): return "operations"
    if any(term in key for term in ("appointment", "flow", "daily_summary")): return "operations"
    return "clinical"


def permission_for(key: str) -> str:
    if key in PERMISSION_OVERRIDES: return PERMISSION_OVERRIDES[key]
    category = category_for(key)
    if key == "appointments_report" or key == "patient_flow_board_report": return "patients:appt:read"
    if category == "inventory": return "inventory:lots:read"
    if category == "financial": return "acct:rep_a:read"
    if category == "operations": return "admin:super:read"
    return "patients:med:read"


def catalog() -> list[dict]:
    embedded={"criteria.tab","report.script"}
    return [{"key":key,"title":key.replace("_"," ").replace("."," ").title(),"category":category_for(key),"permission":permission_for(key),"legacy_path":f"interface/reports/{key}.php","migrated":key in IMPLEMENTED,"migration_status":"migrated" if key in IMPLEMENTED else "embedded" if key in embedded else "pending"} for key in REPORT_PATHS]


def bounds(start: date | None, end: date | None) -> tuple[datetime | None, datetime | None]:
    return (datetime.combine(start,time.min,tzinfo=timezone.utc) if start else None, datetime.combine(end+timedelta(days=1),time.min,tzinfo=timezone.utc) if end else None)


def value(item):
    if isinstance(item,(date,datetime)): return item.isoformat()
    if isinstance(item,Decimal): return str(item)
    return item


def rows_from(result, columns):
    return [{column:value(row[index]) for index,column in enumerate(columns)} for row in result]


def clinical_report(db: Session,user: User,params: dict):
    """Reproduce the legacy clinical cohort report without its unsafe SQL concatenation."""
    today=datetime.now(timezone.utc).date();start=params.get("date_from") or date(today.year,1,1);end=params.get("date_to") or today
    def dated(item):
        if item is None:return False
        day=item.date() if isinstance(item,datetime) else item
        return (start is None or day>=start) and (end is None or day<=end) and day<=today
    def matches(raw,pattern):
        if not pattern:return True
        expression="".join(".*" if part=="%" else "." if part=="_" else __import__("re").escape(part) for part in str(pattern))
        return __import__("re").fullmatch(expression,str(raw or ""),__import__("re").I) is not None
    query=select(Patient).where(Patient.merged_into_id.is_(None))
    if params.get("_patient_id"):query=query.where(Patient.id==params["_patient_id"])
    if params.get("gender"):query=query.where(Patient.sex==params["gender"])
    if params.get("race"):query=query.where(Patient.race==params["race"])
    if params.get("ethnicity"):query=query.where(Patient.ethnicity==params["ethnicity"])
    patients=list(db.scalars(query.order_by(Patient.legacy_pid,Patient.id)));patient_ids=[x.id for x in patients]
    assignments={}
    if patient_ids:
        for item in db.scalars(select(PatientProviderAssignment).where(PatientProviderAssignment.patient_id.in_(patient_ids),PatientProviderAssignment.role=="primary").order_by(PatientProviderAssignment.assigned_at.desc().nullslast(),PatientProviderAssignment.id.desc())):
            current=assignments.get(item.patient_id)
            if current is None or (item.status=="active" and current.status!="active"):assignments[item.patient_id]=item
    requested_facility=params.get("_facility_id");scope=facility_scope(db,user)
    def allowed_patient(patient):
        age=today.year-patient.date_of_birth.year-((today.month,today.day)<(patient.date_of_birth.month,patient.date_of_birth.day))
        if params.get("age_from") is not None and age<params["age_from"]:return False
        if params.get("age_to") is not None and age>params["age_to"]:return False
        assignment=assignments.get(patient.id);facility_id=assignment.facility_id if assignment else None
        if requested_facility is not None and facility_id!=requested_facility:return False
        if scope is not None and facility_id not in scope:return False
        payload=patient.legacy_payload or {};communication=params.get("communication")
        flags={"allow_sms":patient.allow_sms,"allow_email":patient.allow_email,"allow_voice":str(payload.get("hipaa_voice") or "").upper()=="YES","allow_mail":str(payload.get("hipaa_mail") or "").upper()=="YES"}
        if communication and not flags.get(communication,False):return False
        if params.get("include_communication") and not any(flags.values()):return False
        return True
    patients=[x for x in patients if allowed_patient(x)];patient_ids=[x.id for x in patients]
    def grouped(rows,key=lambda x:x.patient_id):
        result={}
        for row in rows:result.setdefault(key(row),[]).append(row)
        return result
    items=grouped(db.scalars(select(ClinicalItem).where(ClinicalItem.patient_id.in_(patient_ids))).all()) if patient_ids else {}
    prescriptions=grouped(db.scalars(select(Prescription).where(Prescription.patient_id.in_(patient_ids))).all()) if patient_ids else {}
    products_by_legacy={x.legacy_drug_id:x for x in db.scalars(select(InventoryProduct).where(InventoryProduct.legacy_drug_id.is_not(None)))}
    labs={}
    if patient_ids:
        for result,order in db.execute(select(LabResult,LabOrder).join(LabOrder,LabResult.order_id==LabOrder.id).where(LabOrder.patient_id.in_(patient_ids))):labs.setdefault(order.patient_id,[]).append((result,order))
    procedures={}
    if patient_ids:
        for order,line in db.execute(select(LabOrder,ProcedureOrderLine).outerjoin(ProcedureOrderLine,ProcedureOrderLine.order_id==LabOrder.id).where(LabOrder.patient_id.in_(patient_ids))):procedures.setdefault(order.patient_id,[]).append((order,line))
    encounter_ids={order.encounter_id for values in procedures.values() for order,_ in values if order.encounter_id};encounter_uuids={x.id:x.uuid for x in db.scalars(select(Encounter).where(Encounter.id.in_(encounter_ids)))} if encounter_ids else {}
    histories=grouped(db.scalars(select(SocialHistory).where(SocialHistory.patient_id.in_(patient_ids))).all()) if patient_ids else {}
    services={}
    if patient_ids:
        for charge,encounter in db.execute(select(Charge,Encounter).join(Encounter,Charge.encounter_id==Encounter.id).where(Charge.patient_id.in_(patient_ids),Charge.active.is_(True))):services.setdefault(charge.patient_id,[]).append((charge,encounter))
    immunizations=grouped(db.scalars(select(Immunization).where(Immunization.patient_id.in_(patient_ids))).all()) if patient_ids else {}
    kind=params.get("clinical_type");use_diagnosis=bool(params.get("diagnosis") or params.get("include_allergies") or params.get("include_problems"));use_rx=bool(params.get("drug_name") or params.get("include_prescriptions"));use_labs=bool(params.get("lab_result") or params.get("include_lab_results"));use_imm=bool(params.get("immunization"))
    columns=["patient_uuid","legacy_patient_id","patient_name","age","sex","race","ethnicity","provider","facility","communications"]
    dimensions=[]
    if use_diagnosis:columns += ["diagnosis_date","diagnosis_category","diagnosis_code","diagnosis_name"];dimensions.append("diagnosis")
    if use_rx:columns += ["prescription_modified","drug","route","dosage","form_id","interval_id","size","unit_id","refills","quantity","ndc","rxnorm"];dimensions.append("prescription")
    if use_labs:columns += ["result_date","result_facility","result_code","result_name","result_unit","result","result_range","abnormal","comments","document_id"];dimensions.append("lab")
    if kind=="Procedure":columns += ["order_date","procedure_code","procedure_standard_code","procedure_name","priority","order_status","encounter_id","instructions","activity","control_id"];dimensions.append("procedure")
    if kind=="Medical History":columns += ["history_date","tobacco","alcohol","recreational_drugs"];dimensions.append("history")
    if kind=="Service Codes":columns += ["service_date","service_code","service_description","encounter_id"];dimensions.append("service")
    if use_imm:columns += ["immunization_date","cvx_code","immunization","dose","dose_unit","site","notes"];dimensions.append("immunization")
    output=[]
    for patient in patients:
        age=today.year-patient.date_of_birth.year-((today.month,today.day)<(patient.date_of_birth.month,patient.date_of_birth.day));assignment=assignments.get(patient.id);payload=patient.legacy_payload or {}
        communication_flags=[label for label,enabled in (("email",patient.allow_email),("sms",patient.allow_sms),("mail",str(payload.get("hipaa_mail") or "").upper()=="YES"),("voice",str(payload.get("hipaa_voice") or "").upper()=="YES")) if enabled]
        base={"patient_uuid":patient.uuid,"legacy_patient_id":patient.legacy_pid,"patient_name":f"{patient.first_name} {patient.last_name}","age":age,"sex":patient.sex,"race":patient.race,"ethnicity":patient.ethnicity,"provider":assignment.practitioner_name if assignment else None,"facility":assignment.facility_name if assignment else None,"communications":", ".join(communication_flags)}
        choices=[]
        for dimension in dimensions:
            values=[]
            if dimension=="diagnosis":
                categories={"allergy"} if params.get("include_allergies") and not params.get("include_problems") else {"problem"} if params.get("include_problems") and not params.get("include_allergies") else {"problem","allergy"}
                values=[{"diagnosis_date":x.created_at,"diagnosis_category":x.category,"diagnosis_code":x.code,"diagnosis_name":x.title} for x in items.get(patient.id,[]) if x.category in categories and dated(x.created_at) and (not params.get("diagnosis") or matches(x.code,params["diagnosis"]) or matches(x.title,f"%{params['diagnosis']}%"))]
            elif dimension=="prescription":
                values=[{"prescription_modified":x.modified_at or x.prescribed_at,"drug":x.drug_name,"route":x.route,"dosage":x.dosage,"form_id":x.form_legacy_id,"interval_id":x.interval_legacy_id,"size":x.size,"unit_id":x.unit_legacy_id,"refills":x.refills,"quantity":x.quantity,"ndc":products_by_legacy[x.drug_legacy_id].ndc_number if x.drug_legacy_id in products_by_legacy else None,"rxnorm":x.rxnorm_code} for x in prescriptions.get(patient.id,[]) if dated(x.modified_at or x.prescribed_at) and matches(x.drug_name,params.get("drug_name") or "%")]
            elif dimension=="lab":
                values=[{"result_date":x.observed_at,"result_facility":x.facility,"result_code":x.code,"result_name":x.name,"result_unit":x.unit,"result":x.value,"result_range":x.reference_range,"abnormal":x.interpretation,"comments":x.comments,"document_id":x.legacy_document_id} for x,_ in labs.get(patient.id,[]) if dated(x.observed_at) and matches(x.value,params.get("lab_result") or "%")]
            elif dimension=="procedure":
                values=[{"order_date":order.ordered_at,"procedure_code":line.code if line else order.code,"procedure_standard_code":line.standard_code if line else None,"procedure_name":line.name if line else order.name,"priority":order.priority,"order_status":order.status,"encounter_id":encounter_uuids.get(order.encounter_id),"instructions":order.instructions,"activity":order.activity,"control_id":order.control_id} for order,line in procedures.get(patient.id,[]) if dated(order.ordered_at)]
            elif dimension=="history":
                candidates=[x for x in histories.get(patient.id,[]) if dated(x.recorded_at) and any((x.tobacco,x.alcohol,x.recreational_drugs))];candidates.sort(key=lambda x:(x.recorded_at or datetime.min.replace(tzinfo=timezone.utc),x.id),reverse=True)
                values=[{"history_date":x.recorded_at,"tobacco":x.tobacco,"alcohol":x.alcohol,"recreational_drugs":x.recreational_drugs} for x in candidates[:1]]
            elif dimension=="service":
                requested=(params.get("service_code") or "").split(":")[-1]
                values=[{"service_date":x.billed_at or encounter.occurred_at,"service_code":x.code,"service_description":x.description,"encounter_id":encounter.uuid} for x,encounter in services.get(patient.id,[]) if dated(x.billed_at or encounter.occurred_at) and (not requested or x.code==requested)]
            else:
                values=[{"immunization_date":x.administered_at,"cvx_code":x.cvx_code,"immunization":x.vaccine_name,"dose":x.dose,"dose_unit":x.dose_unit,"site":x.site,"notes":x.note} for x in immunizations.get(patient.id,[]) if dated(x.administered_at) and (matches(x.vaccine_name,f"%{params['immunization']}%") or matches(x.cvx_code,f"%{params['immunization']}%"))]
            choices.append(values)
        if dimensions and any(not values for values in choices):continue
        combinations=product(*choices) if choices else [()]
        for combination in combinations:
            row=dict(base)
            for detail in combination:row.update({key:value(val) for key,val in detail.items()})
            output.append(row)
    sort_keys=[]
    if params.get("sort_patient_name"):sort_keys.append("patient_name")
    if params.get("sort_patient_age"):sort_keys.append("age")
    sort_keys += ["legacy_patient_id"]
    output.sort(key=lambda row:tuple((row.get(key) is None,str(row.get(key) or "")) for key in sort_keys))
    return columns,output,{"rows":len(output),"patients":len({row["patient_uuid"] for row in output})}


def patient_list_creation_report(db: Session,user: User,params: dict):
    """Build the legacy patient-list modes as deterministic, immutable cohorts."""
    import re
    option=params.get("patient_list_option") or "demos";today=datetime.now(timezone.utc).date()
    start=params.get("date_from") or date(today.year,1,1);end=params.get("date_to") or today
    def dated(raw):
        if raw is None:return False
        day=raw.date() if isinstance(raw,datetime) else raw
        return start<=day<=end and day<=today
    def matches(raw,pattern):
        if not pattern:return True
        expression="".join(".*" if char=="%" else "." if char=="_" else re.escape(char) for char in str(pattern))
        return re.fullmatch(expression,str(raw or ""),re.I) is not None
    def patient_name(patient):return ", ".join(filter(None,(patient.last_name,patient.first_name)))
    def practitioner_name(item):return " ".join(filter(None,(item.first_name,item.last_name))) if item else None
    def patient_age(patient):return today.year-patient.date_of_birth.year-((today.month,today.day)<(patient.date_of_birth.month,patient.date_of_birth.day))

    patients=list(db.scalars(select(Patient).where(Patient.merged_into_id.is_(None)).order_by(Patient.legacy_pid,Patient.id)))
    if params.get("_patient_id"):patients=[item for item in patients if item.id==params["_patient_id"]]
    patient_ids=[item.id for item in patients];assignments={}
    if patient_ids:
        for item in db.scalars(select(PatientProviderAssignment).where(PatientProviderAssignment.patient_id.in_(patient_ids),PatientProviderAssignment.role=="primary").order_by(PatientProviderAssignment.assigned_at.desc().nullslast(),PatientProviderAssignment.id.desc())):
            current=assignments.get(item.patient_id)
            if current is None or (item.status=="active" and current.status!="active"):assignments[item.patient_id]=item
    scope=facility_scope(db,user)
    def allowed(patient):
        assignment=assignments.get(patient.id);age=patient_age(patient)
        if scope is not None and (not assignment or assignment.facility_id not in scope):return False
        if option in {"demos","allergs","probs","meds","comms","insurers"} and params.get("provider_legacy_id") and (not assignment or assignment.legacy_practitioner_id!=params["provider_legacy_id"]):return False
        if params.get("age_from") is not None and age<params["age_from"]:return False
        if params.get("age_to") is not None and age>params["age_to"]:return False
        if params.get("gender") and patient.sex!=params["gender"]:return False
        for field in ("race","ethnicity"):
            expected=params.get(field);actual=getattr(patient,field) or ""
            if expected and expected not in actual.strip("|").split("|"):return False
        return True
    patients=[item for item in patients if allowed(item)]
    practitioners={item.legacy_user_id:item for item in db.scalars(select(Practitioner).where(Practitioner.legacy_user_id.is_not(None)))}
    payers={item.id:item for item in db.scalars(select(Payer))}
    columns_by_option={
        "demos":["patient_date","patient_name","patient_id","patient_uuid","patient_age","patient_sex","patient_ethnic","patient_race","users_provider"],
        "allergs":["other_date","patient_name","patient_id","patient_uuid","patient_age","patient_sex","patient_ethnic","users_provider","allergy","pr_diagnosis"],
        "probs":["other_date","patient_name","patient_id","patient_uuid","patient_age","patient_sex","patient_ethnic","users_provider","problem","pr_diagnosis"],
        "meds":["other_date","patient_name","patient_id","patient_uuid","patient_age","patient_sex","patient_ethnic","users_provider","medication","pr_diagnosis"],
        "prescripts":["other_date","patient_name","patient_id","patient_uuid","patient_age","patient_sex","rx_drug","rx_medicine_units","rx_directions","rx_quantity","rx_refills"],
        "comms":["patient_date","patient_name","patient_id","patient_uuid","patient_age","patient_sex","patient_ethnic","users_provider","communications"],
        "insurers":["patient_date","patient_name","patient_id","patient_uuid","patient_age","patient_sex","patient_ethnic","users_provider","ins_name"],
        "encounts":["other_date","patient_name","patient_id","patient_uuid","patient_age","patient_sex","users_provider","enc_type","enc_reason","enc_facility","enc_discharge"],
        "observs":["other_date","patient_name","patient_id","patient_uuid","patient_age","patient_sex","users_provider","obs_code","obs_description","obs_type","obs_value","obs_units","obs_comments"],
        "procs":["other_date","patient_name","patient_id","patient_uuid","users_provider","pr_lab","pr_status","prc_procedure","pr_diagnosis","prc_diagnoses"],
        "results":["other_date","result_facility","patient_id","patient_uuid","result_description","result_result","result_units","result_range","result_abnormal","result_comments","result_document_id"],
    }
    rows=[]
    for patient in patients:
        assignment=assignments.get(patient.id);payload=patient.legacy_payload or {}
        base={"patient_date":value(patient.created_at),"patient_name":patient_name(patient),"patient_id":patient.legacy_pid,"patient_uuid":patient.uuid,"patient_age":patient_age(patient),"patient_sex":patient.sex,"patient_ethnic":patient.ethnicity,"patient_race":patient.race,"users_provider":assignment.practitioner_name if assignment else None}
        if option=="demos" and dated(patient.created_at):rows.append(base)
        elif option in {"allergs","probs","meds"}:
            category={"allergs":"allergy","probs":"problem","meds":"medication"}[option]
            for item in db.scalars(select(ClinicalItem).where(ClinicalItem.patient_id==patient.id,ClinicalItem.category==category).order_by(ClinicalItem.recorded_at,ClinicalItem.id)):
                when=item.recorded_at or item.created_at
                if dated(when) and matches(item.code,params.get("procedure_diagnosis")):rows.append(base|{"other_date":value(when),category:item.title,"pr_diagnosis":item.code})
        elif option=="prescripts":
            for item in db.scalars(select(Prescription).where(Prescription.patient_id==patient.id).order_by(Prescription.legacy_recorded_at,Prescription.id)):
                when=item.prescribed_at or item.legacy_recorded_at or item.modified_at
                if not dated(when) or not matches(item.drug_name,params.get("drug_name")):continue
                provider=practitioners.get(item.provider_legacy_id);legacy=item.legacy_payload or {};directions=" ".join(filter(None,(item.dosage,"in" if legacy.get("form_title") else None,legacy.get("form_title"),legacy.get("interval_title")))) or item.dosage_instructions
                rows.append(base|{"other_date":value(when),"users_provider":practitioner_name(provider),"rx_drug":item.drug_name,"rx_medicine_units":"".join(filter(None,(item.size,legacy.get("unit_title") or (str(item.unit_legacy_id) if item.unit_legacy_id else None)))),"rx_directions":directions,"rx_quantity":item.quantity,"rx_refills":item.refills})
        elif option=="comms":
            flags=[label for label,enabled in (("Email",patient.allow_email),("SMS",patient.allow_sms),("Mail Message",str(payload.get("hipaa_mail") or "").upper()=="YES"),("Voice Message",str(payload.get("hipaa_voice") or "").upper()=="YES")) if enabled]
            requested=params.get("communication");mapping={"allow_email":"Email","allow_sms":"SMS","allow_mail":"Mail Message","allow_voice":"Voice Message"}
            if dated(patient.created_at) and flags and (not requested or mapping[requested] in flags):rows.append(base|{"communications":", ".join(flags)})
        elif option=="insurers":
            for coverage in db.scalars(select(Coverage).where(Coverage.patient_id==patient.id,Coverage.priority=="primary").order_by(Coverage.id)):
                payer=payers.get(coverage.payer_id)
                if dated(patient.created_at) and (not params.get("insurance_legacy_id") or (payer and payer.legacy_payer_id==params["insurance_legacy_id"])):rows.append(base|{"ins_name":payer.name if payer else None})
        elif option=="encounts":
            for item in db.scalars(select(Encounter).where(Encounter.patient_id==patient.id).order_by(Encounter.occurred_at,Encounter.id)):
                if not dated(item.occurred_at) or (scope is not None and item.facility_id not in scope) or (params.get("provider_legacy_id") and item.legacy_provider_id!=params["provider_legacy_id"]):continue
                legacy=item.legacy_payload or {};enc_type=legacy.get("encounter_type_code") or item.type
                if params.get("encounter_type") and str(enc_type)!=params["encounter_type"]:continue
                rows.append(base|{"other_date":value(item.occurred_at),"users_provider":item.provider_name,"enc_type":legacy.get("encounter_type_description") or item.type,"enc_reason":item.chief_complaint,"enc_facility":item.facility_name,"enc_discharge":legacy.get("discharge_disposition")})
        elif option=="observs":
            for form in db.scalars(select(ClinicalForm).where(ClinicalForm.patient_id==patient.id,ClinicalForm.source_formdir=="observation").order_by(ClinicalForm.authored_at,ClinicalForm.id)):
                for observation in (form.content or {}).get("rows",[]):
                    when=observation.get("date") or form.authored_at
                    if isinstance(when,str):
                        try:when=datetime.fromisoformat(when.replace("Z","+00:00"))
                        except ValueError:when=form.authored_at
                    if not dated(when):continue
                    code=observation.get("code");description=observation.get("description")
                    if params.get("observation_description") and not (matches(code,params["observation_description"]) or matches(description,params["observation_description"])):continue
                    provider=next((item for item in practitioners.values() if item.username==observation.get("user")),None)
                    if params.get("provider_legacy_id") and (not provider or provider.legacy_user_id!=params["provider_legacy_id"]):continue
                    rows.append(base|{"other_date":value(when),"users_provider":practitioner_name(provider) or base["users_provider"],"obs_code":code,"obs_description":description,"obs_type":observation.get("ob_type"),"obs_value":observation.get("ob_value"),"obs_units":observation.get("ob_unit"),"obs_comments":observation.get("observation")})
        elif option=="procs":
            for order,line in db.execute(select(LabOrder,ProcedureOrderLine).outerjoin(ProcedureOrderLine,ProcedureOrderLine.order_id==LabOrder.id).where(LabOrder.patient_id==patient.id).order_by(LabOrder.ordered_at,LabOrder.id,ProcedureOrderLine.sequence)):
                if not dated(order.ordered_at) or (params.get("provider_legacy_id") and order.provider_legacy_id!=params["provider_legacy_id"]):continue
                if params.get("procedure_diagnosis") and not (matches(order.order_diagnosis,params["procedure_diagnosis"]) or (line and matches(line.diagnoses,params["procedure_diagnosis"]))):continue
                provider=practitioners.get(order.provider_legacy_id);legacy=order.legacy_payload or {}
                rows.append(base|{"other_date":value(order.ordered_at),"users_provider":practitioner_name(provider),"pr_lab":legacy.get("lab_name"),"pr_status":order.status,"prc_procedure":line.name if line else order.name,"pr_diagnosis":order.order_diagnosis,"prc_diagnoses":line.diagnoses if line else None})
        elif option=="results":
            for result,order in db.execute(select(LabResult,LabOrder).join(LabOrder,LabResult.order_id==LabOrder.id).where(LabOrder.patient_id==patient.id).order_by(LabResult.observed_at,LabResult.id)):
                diagnosis_pattern=params.get("procedure_diagnosis");line_diagnoses=db.scalars(select(ProcedureOrderLine.diagnoses).where(ProcedureOrderLine.order_id==order.id)).all() if diagnosis_pattern else []
                if not dated(result.observed_at) or not result.value or (params.get("provider_legacy_id") and order.provider_legacy_id!=params["provider_legacy_id"]) or (diagnosis_pattern and not (matches(order.order_diagnosis,diagnosis_pattern) or any(matches(item,diagnosis_pattern) for item in line_diagnoses))):continue
                rows.append(base|{"other_date":value(result.observed_at),"result_facility":result.facility,"result_description":result.name,"result_result":result.value,"result_units":result.unit,"result_range":result.reference_range,"result_abnormal":result.interpretation,"result_comments":result.comments,"result_document_id":result.legacy_document_id})
    columns=columns_by_option[option];sort=params.get("patient_list_sort");sort=sort if sort in columns else ("patient_date" if option in {"demos","comms","insurers"} else "other_date")
    rows.sort(key=lambda row:(row.get(sort) is None,str(row.get(sort) or ""),row.get("patient_id") or 0),reverse=params.get("patient_list_sort_order")=="desc")
    return columns,rows,{"rows":len(rows),"patients":len({row["patient_uuid"] for row in rows}),"option":option}


def ippf_cyp_report(db: Session,user: User,params: dict):
    """Calculate couple-years of protection from MA services and paid drug sales."""
    from decimal import ROUND_HALF_UP
    today=datetime.now(timezone.utc).date();start=params.get("date_from") or today;end=params.get("date_to") or start
    scope=facility_scope(db,user);requested=params.get("_facility_id");requested_legacy=params.get("_legacy_facility_id")
    def allowed(encounter):
        if not start<=encounter.occurred_at.date()<=end:return False
        if requested is not None:return encounter.facility_id==requested or (requested_legacy is not None and encounter.legacy_facility_id==requested_legacy)
        return scope is None or encounter.facility_id in scope
    encounters={item.id:item for item in db.scalars(select(Encounter).order_by(Encounter.occurred_at,Encounter.id)) if allowed(item)}
    service_codes={(item.code,item.modifier or ""):item for item in db.scalars(select(ServiceCode).where(ServiceCode.code_type_id==12,ServiceCode.cyp_factor>0))}
    products={item.id:item for item in db.scalars(select(InventoryProduct).where(InventoryProduct.cyp_factor>0))}
    lines=[];cent=Decimal("0.01")
    def append(source,item,when,invoice,quantity,factor,patient_uuid,encounter_uuid):
        rounded=Decimal(factor).quantize(cent,rounding=ROUND_HALF_UP);result=(rounded*quantity).quantize(cent,rounding=ROUND_HALF_UP)
        lines.append({"source":source,"item":item,"date":value(when),"invoice":invoice,"quantity":quantity,"cyp":value(rounded),"result":value(result),"patient_uuid":patient_uuid,"encounter_uuid":encounter_uuid})
    if encounters:
        encounter_ids=list(encounters);patient_ids={item.patient_id for item in encounters.values()};patients={item.id:item for item in db.scalars(select(Patient).where(Patient.id.in_(patient_ids)))}
        for charge in db.scalars(select(Charge).where(Charge.encounter_id.in_(encounter_ids),Charge.active.is_(True),Charge.code_system=="MA").order_by(Charge.code,Charge.billed_at,Charge.id)):
            definition=service_codes.get((charge.code,charge.modifier or ""))
            if not definition:continue
            encounter=encounters[charge.encounter_id];patient=patients[charge.patient_id];legacy=encounter.legacy_payload or {};invoice=legacy.get("invoice_refno") or (f"{patient.legacy_pid}.{encounter.legacy_encounter_id}" if patient.legacy_pid is not None and encounter.legacy_encounter_id is not None else f"{patient.uuid}.{encounter.uuid}")
            append("service",f"{charge.code} {charge.description}".strip(),encounter.occurred_at.date(),invoice,charge.units,definition.cyp_factor,patient.uuid,encounter.uuid)
        for transaction in db.scalars(select(InventoryTransaction).where(InventoryTransaction.encounter_id.in_(encounter_ids),InventoryTransaction.fee!=0).order_by(InventoryTransaction.product_id,InventoryTransaction.occurred_on,InventoryTransaction.id)):
            product=products.get(transaction.product_id)
            if not product:continue
            encounter=encounters[transaction.encounter_id];patient=patients.get(transaction.patient_id or encounter.patient_id);legacy=encounter.legacy_payload or {};invoice=legacy.get("invoice_refno") or (f"{patient.legacy_pid}.{encounter.legacy_encounter_id}" if patient.legacy_pid is not None and encounter.legacy_encounter_id is not None else f"{patient.uuid}.{encounter.uuid}")
            append("drug",product.name,encounter.occurred_at.date(),invoice,transaction.quantity,product.cyp_factor,patient.uuid,encounter.uuid)
    lines.sort(key=lambda row:(0 if row["source"]=="service" else 1,row["item"],row["date"],row["invoice"]))
    total_quantity=sum(row["quantity"] for row in lines);total_result=sum((Decimal(row["result"]) for row in lines),Decimal("0"))
    if params.get("include_details",True):return ["source","item","date","invoice","quantity","cyp","result","patient_uuid","encounter_uuid"],lines,{"quantity":total_quantity,"cyp_result":value(total_result.quantize(cent)),"items":len({row["item"] for row in lines})}
    grouped={}
    for row in lines:
        key=(row["item"],row["cyp"]);current=grouped.setdefault(key,{"item":row["item"],"quantity":0,"cyp":row["cyp"],"result":Decimal("0")});current["quantity"]+=row["quantity"];current["result"]+=Decimal(row["result"])
    summary=[item|{"result":value(item["result"].quantize(cent))} for item in grouped.values()]
    return ["item","quantity","cyp","result"],summary,{"quantity":total_quantity,"cyp_result":value(total_result.quantize(cent)),"items":len(summary)}


IPPF_DAILY_METHODS = [
    ("con","Condom (Male or Female)"),("dia","Diaphragm"),("ec","Emergency Contraception"),
    ("fab","Fertility Awareness Based"),("fc","Foam & Condom"),("pat","Hormonal Patch"),
    ("imp","Implant"),("inj","Injectable"),("iud","IUCD"),("no","None"),("or","Oral"),
    ("cap","Pessary/Cervicap Cap"),("sp","Spermicides"),("vsc","Voluntary Surgical Contraception"),("zzz","Unknown"),
]


def ippf_daily_report(db: Session,user: User,params: dict):
    """Reproduce the IPPF clinic daily record by current contraceptive method."""
    report_date=params.get("date_from") or datetime.now(timezone.utc).date();scope=facility_scope(db,user)
    requested=params.get("_facility_id");requested_legacy=params.get("_legacy_facility_id")
    def allowed(encounter):
        if encounter.occurred_at.date()!=report_date:return False
        if requested is not None:return encounter.facility_id==requested or (requested_legacy is not None and encounter.legacy_facility_id==requested_legacy)
        return scope is None or encounter.facility_id in scope
    encounters=[item for item in db.scalars(select(Encounter).order_by(Encounter.patient_id,Encounter.legacy_encounter_id,Encounter.id)) if allowed(item)]
    encounter_map={item.id:item for item in encounters};encounter_ids=list(encounter_map)
    charges=list(db.scalars(select(Charge).where(Charge.encounter_id.in_(encounter_ids),Charge.active.is_(True),Charge.code_system=="MA").order_by(Charge.patient_id,Charge.encounter_id,Charge.code,Charge.id))) if encounter_ids else []
    patient_ids={item.patient_id for item in charges};patients={item.id:item for item in db.scalars(select(Patient).where(Patient.id.in_(patient_ids)))} if patient_ids else {}
    current_methods={}
    if patient_ids:
        methods=db.scalars(select(ClinicalItem).where(ClinicalItem.patient_id.in_(patient_ids),ClinicalItem.category=="contraceptive",ClinicalItem.status=="active").order_by(ClinicalItem.patient_id,ClinicalItem.onset_date.desc().nullslast(),ClinicalItem.id.desc()))
        for item in methods:
            if item.patient_id in current_methods or (item.onset_date and item.onset_date>report_date) or (item.end_date and item.end_date<=report_date):continue
            current_methods[item.patient_id]=(item.code or "").split("|")[0] or "zzz"
    metrics=["new_clients","old_clients","total_clients","contra_clients","pap_smear","preg_test","doctor_check","doctor_visit","advice","counseling_by_method","infertility_counseling","std_aids_counseling"]
    data={key:{"method_code":key,"method":title}|{metric:0 for metric in metrics} for key,title in IPPF_DAILY_METHODS}
    encountered={}
    service_metrics={"255004":"pap_smear","256101":"preg_test","375008":"doctor_check","375015":"doctor_visit","375011":"advice","19916":"counseling_by_method","39916":"infertility_counseling","19911":"std_aids_counseling"}
    for charge in charges:
        patient=patients[charge.patient_id];method=current_methods.get(patient.id,"zzz")
        if method not in data:data[method]={"method_code":method,"method":f"Unlisted method '{method}'"}|{metric:0 for metric in metrics}
        row=data[method]
        if patient.id not in encountered:
            registered=(patient.legacy_payload or {}).get("regdate")
            row["total_clients"]+=1;row["new_clients" if str(registered or "")[:10]==report_date.isoformat() else "old_clients"]+=1;encountered[patient.id]=set()
        if charge.encounter_id not in encountered[patient.id]:
            category=str((encounter_map[charge.encounter_id].legacy_payload or {}).get("pc_catid") or "")
            if category=="10" and "contra" not in encountered[patient.id]:row["contra_clients"]+=1;encountered[patient.id].add("contra")
            encountered[patient.id].add(charge.encounter_id)
        metric=service_metrics.get(charge.code)
        if metric:row[metric]+=1
    rows=list(data.values());columns=["method_code","method",*metrics]
    totals={metric:sum(row[metric] for row in rows) for metric in metrics};totals["methods"]=len(rows);totals["date"]=report_date.isoformat()
    return columns,rows,totals


def _ippf_contraceptive_method(code: str) -> str | None:
    import re
    tests=[("Pills",r"^111101"),("Injectables",r"^11111[1-9]"),("Implants",r"^11112[1-9]"),("Patch",r"^111132"),("Vaginal Ring",r"^111133"),("Male Condoms",r"^112141"),("Female Condoms",r"^112142"),("Diaphragms/Caps",r"^11215[1-9]"),("Spermicides",r"^11216[1-9]"),("IUD",r"^11317[1-9]"),("Emergency Contraception",r"^145212"),("Female VSC",r"^121181.13"),("Male VSC",r"^122182.13"),("Awareness-Based",r"^131191.10")]
    return next((title for title,pattern in tests if re.search(pattern,code)),None)


def _ippf_abortion_method(code: str) -> str | None:
    if code.startswith("2522231"):return "D&C"
    if code.startswith("2522232"):return "D&E"
    if code.startswith("2522233"):return "MVA"
    if code.startswith("252224"):return "Medical"
    if code.startswith(("252223","252224")):return "Other Surgical"
    return None


def _coded_values(raw: str | None,system: str) -> list[str]:
    values=[]
    for token in str(raw or "").split(";"):
        kind,separator,code=token.partition(":")
        if separator and kind==system and code:values.append(code)
    return values


def ippf_statistics_report(db: Session,user: User,params: dict):
    """Multidimensional IPPF, Member Association and GCAC statistics engine."""
    family=params.get("ippf_report_type") or "i";group=params.get("ippf_group_by") or {"i":"3","m":"101","g":"13"}[family];content=params.get("ippf_content") or "1"
    allowed={"i":({"3","4","104","6","9","10"},{"1","3","5"}),"m":({"101","102","17","9","10","103","2"},{"1","2","4"}),"g":({"13","1","12","5","8","7","11","10","20"},{"1","2","4"})}
    if group not in allowed[family][0] or content not in allowed[family][1]:raise HTTPException(status_code=422,detail="Invalid row/content combination for the selected IPPF report family")
    today=datetime.now(timezone.utc).date();start=params.get("date_from") or date(1900,1,1);end=params.get("date_to") or today;scope=facility_scope(db,user);requested=params.get("_facility_id");requested_legacy=params.get("_legacy_facility_id")
    def in_facility(encounter):
        if requested is not None:return encounter.facility_id==requested or (requested_legacy is not None and encounter.legacy_facility_id==requested_legacy)
        return scope is None or encounter.facility_id in scope
    encounters=[item for item in db.scalars(select(Encounter).where(func.date(Encounter.occurred_at)>=start,func.date(Encounter.occurred_at)<=end).order_by(Encounter.patient_id,Encounter.occurred_at,Encounter.id)) if in_facility(item)]
    encounter_map={item.id:item for item in encounters};patient_ids={item.patient_id for item in encounters};patients={item.id:item for item in db.scalars(select(Patient).where(Patient.id.in_(patient_ids),Patient.merged_into_id.is_(None)))} if patient_ids else {}
    sex_filter=params.get("ippf_sex") or "all"
    def sex_allowed(patient):return sex_filter=="all" or ("male" if str(patient.sex).lower()=="male" else "female")==sex_filter
    service_codes={(item.code,item.modifier or ""):item for item in db.scalars(select(ServiceCode).where(ServiceCode.code_type_id==12,ServiceCode.active.is_(True)))}
    ippf_descriptions={item.code:item.description for item in db.scalars(select(ServiceCode).where(ServiceCode.code_type_id==11))}
    referral_definitions={item.code:item.related_codes for item in db.scalars(select(ServiceCode).where(ServiceCode.code_type_id==16,ServiceCode.active.is_(True)))}
    forms_by_encounter={}
    if encounter_map:
        for form in db.scalars(select(ClinicalForm).where(ClinicalForm.encounter_id.in_(list(encounter_map)),ClinicalForm.source_formdir=="LBFgcac").order_by(ClinicalForm.authored_at,ClinicalForm.id)):forms_by_encounter.setdefault(form.encounter_id,[]).append(form.content or {})
    def form_value(encounter_id,name,default="Indeterminate"):
        for payload in reversed(forms_by_encounter.get(encounter_id,[])):
            if payload.get(name):return str(payload[name])
            for row in payload.get("rows",[]):
                if row.get("field_id")==name and row.get("field_value"):return str(row["field_value"])
        return default
    display_fields=[item for item in (params.get("ippf_columns") or ["total"]) if item not in {"total","sex","age2","age9"}]
    aggregates={};seen=set();dimension_values={field:set() for field in display_fields}
    def registration(patient,key):
        raw=(patient.legacy_payload or {}).get(key)
        try:return date.fromisoformat(str(raw)[:10]) if raw else None
        except ValueError:return None
    def add(report_key,description,patient,when,quantity=1):
        if not report_key or not patient or not sex_allowed(patient):return
        marker=(report_key,patient.id)
        if content=="2" and marker in seen:return
        if content=="3" and (marker in seen or not (registration(patient,"contrastart") and start<=registration(patient,"contrastart")<=end)):return
        if content=="4" and (marker in seen or not (registration(patient,"regdate") and start<=registration(patient,"regdate")<=end)):return
        if content in {"2","3","4"}:seen.add(marker);quantity=1
        row=aggregates.setdefault(report_key,{"group":report_key,"description":description or "","total":0,"women":0,"men":0,"age_0_24":0,"age_25_plus":0,"age_0_10":0,"age_11_14":0,"age_15_19":0,"age_20_24":0,"age_25_29":0,"age_30_34":0,"age_35_39":0,"age_40_44":0,"age_45_plus":0,"dimensions":{field:{} for field in display_fields}})
        row["total"]+=quantity;row["men" if str(patient.sex).lower()=="male" else "women"]+=quantity
        age=when.year-patient.date_of_birth.year-((when.month,when.day)<(patient.date_of_birth.month,patient.date_of_birth.day));row["age_0_24" if age<25 else "age_25_plus"]+=quantity
        bucket="age_0_10" if age<11 else "age_11_14" if age<15 else "age_15_19" if age<20 else "age_20_24" if age<25 else "age_25_29" if age<30 else "age_30_34" if age<35 else "age_35_39" if age<40 else "age_40_44" if age<45 else "age_45_plus";row[bucket]+=quantity
        payload=patient.legacy_payload or {}
        for field in display_fields:
            raw=getattr(patient,field,None) if hasattr(patient,field) else payload.get(field);label=str(raw or "Unspecified");row["dimensions"][field][label]=row["dimensions"][field].get(label,0)+quantity;dimension_values[field].add(label)
    def code_group(code,definition,patient,encounter):
        if group=="1":return ("SRH - Family Planning" if code.startswith("1") else "SRH Non Family Planning" if code.startswith("2") else None,"")
        if group=="3":return ({"1":"SRH - Family Planning","2":"SRH Non Family Planning","3":"Non-SRH Medical","4":"Non-SRH Non-Medical"}.get(code[:1],"Invalid Service Codes"),"")
        if group=="4":return code,ippf_descriptions.get(code,"")
        if group=="104":return (code,ippf_descriptions.get(code,"")) if _ippf_contraceptive_method(code) else (None,"")
        if group in {"6","7"}:return _ippf_contraceptive_method(code),""
        if group=="13":
            key=next((title for prefix,title in (("252221","Pre-Abortion Counseling"),("252222","Pre-Abortion Consultation"),("252223","Induced Abortion"),("252224","Medical Abortion"),("252225","Incomplete Abortion Treatment"),("252226","Post-Abortion Care"),("252227","Post-Abortion Counseling"),("25222","Other/Generic Abortion-Related")) if code.startswith(prefix)),None);return key,""
        if group=="5":return _ippf_abortion_method(code),""
        if group=="8":return (form_value(encounter.id,"client_status"),"") if code.startswith(("252225","252226","252227")) else (None,"")
        if group=="12":return (form_value(encounter.id,"client_status"),"") if code.startswith("252221") else (None,"")
        return None,""
    referral_groups={"9","10","20"}
    if content!="5" and group not in referral_groups and group!="11":
        for charge in db.scalars(select(Charge).where(Charge.encounter_id.in_(list(encounter_map)),Charge.active.is_(True),Charge.code_system=="MA").order_by(Charge.patient_id,Charge.encounter_id,Charge.code,Charge.id)) if encounter_map else []:
            encounter=encounter_map[charge.encounter_id];patient=patients.get(charge.patient_id);definition=service_codes.get((charge.code,charge.modifier or ""));codes=_coded_values(definition.related_codes if definition else None,"IPPF")
            if family=="m":
                key=definition.category_title if group=="101" and definition else charge.code if group=="102" else (patient.legacy_payload or {}).get("referral_source") if group=="103" else f"{patient.last_name}, {patient.first_name} {patient.middle_name or ''}".strip() if group=="17" else {"1":"Services","2":"Unique Clients","4":"Unique New Clients"}.get(content) if group=="2" else None
                add(str(key or "Unspecified"),definition.description if group=="102" and definition else "",patient,encounter.occurred_at.date())
            else:
                for code in codes:
                    key,description=code_group(code,definition,patient,encounter)
                    if group=="7" and not forms_by_encounter.get(encounter.id):continue
                    add(key,description,patient,encounter.occurred_at.date())
    if group=="11":
        for encounter in encounters:
            patient=patients.get(encounter.patient_id)
            for payload in forms_by_encounter.get(encounter.id,[]):
                complications=payload.get("complications") or []
                if isinstance(complications,str):complications=[item for item in complications.split("|") if item]
                procedure=payload.get("in_ab_proc") or "Indeterminate"
                for complication in complications:add(f"{procedure} / {complication}","",patient,encounter.occurred_at.date())
    if content=="5":
        products={item.id:item for item in db.scalars(select(InventoryProduct))}
        for transaction in db.scalars(select(InventoryTransaction).where(InventoryTransaction.occurred_on>=start,InventoryTransaction.occurred_on<=end,InventoryTransaction.quantity!=0,InventoryTransaction.patient_id.is_not(None)).order_by(InventoryTransaction.patient_id,InventoryTransaction.encounter_id,InventoryTransaction.product_id,InventoryTransaction.id)):
            patient=db.get(Patient,transaction.patient_id);encounter=db.get(Encounter,transaction.encounter_id) if transaction.encounter_id else None;product=products.get(transaction.product_id);raw=(product.legacy_payload or {}).get("related_code") if product else None;codes=_coded_values(raw,"IPPF")
            if encounter:
                for charge in db.scalars(select(Charge).where(Charge.encounter_id==encounter.id,Charge.active.is_(True),Charge.code_system=="MA").order_by(Charge.code)):
                    definition=service_codes.get((charge.code,charge.modifier or ""));candidate=_coded_values(definition.related_codes if definition else None,"IPPF")
                    contraceptive=next((code for code in candidate if _ippf_contraceptive_method(code)),None)
                    if contraceptive:codes=[contraceptive];break
            if not product or not patient or (product.cyp_factor<=0 and not codes) or (requested is not None and not encounter) or (encounter and not in_facility(encounter)):continue
            code=next((item for item in codes if _ippf_contraceptive_method(item)),codes[0] if codes else "")
            key,description=code_group(code,None,patient,encounter) if code else ("Unspecified","");add(key,description,patient,transaction.occurred_on,transaction.quantity)
    if content!="5" and (group in referral_groups or (family=="g" and group=="1")):
        for referral in db.scalars(select(Referral).where(Referral.referred_at<=datetime.combine(end,time.max,tzinfo=timezone.utc)).order_by(Referral.patient_id,Referral.referred_at,Referral.id)):
            when=referral.replied_at if group=="20" else referral.referred_at
            if not when or not start<=when.date()<=end:continue
            fields=referral.legacy_fields or {};external=str(fields.get("refer_external") or ("1" if referral.recipient_practitioner_id is None else "0"))
            if group=="9" and external=="1" or group in {"10","20"} and external!="1":continue
            raw=fields.get("reply_related_code") if group=="20" else fields.get("refer_related_code");codes=_coded_values(raw,"IPPF")
            if not codes:
                for refcode in _coded_values(raw,"REF"):codes.extend(_coded_values(referral_definitions.get(refcode),"IPPF"))
            patient=db.get(Patient,referral.patient_id)
            if group=="1":
                if any(code.startswith(("1","2")) for code in codes):add("SRH Referrals","",patient,when.date())
            else:add(codes[0] if codes else "Unspecified",ippf_descriptions.get(codes[0],"") if codes else "",patient,when.date())
    selected=params.get("ippf_columns") or ["total"];columns=["group"]
    if group in {"4","102","9","10","20","104"}:columns.append("description")
    if "total" in selected:columns.append("total")
    if "sex" in selected:columns.extend(["women","men"])
    if "age2" in selected:columns.extend(["age_0_24","age_25_plus"])
    if "age9" in selected:columns.extend(["age_0_10","age_11_14","age_15_19","age_20_24","age_25_29","age_30_34","age_35_39","age_40_44","age_45_plus"])
    for field in display_fields:
        for label in sorted(dimension_values[field]):columns.append(f"{field}:{label}")
    rows=[]
    for key in sorted(aggregates):
        item=aggregates[key];row={column:item.get(column,0) for column in columns}
        for field in display_fields:
            for label,count in item["dimensions"][field].items():row[f"{field}:{label}"]=count
        rows.append(row)
    return columns,rows,{"total":sum(item["total"] for item in aggregates.values()),"groups":len(rows),"report_family":family,"content":content}


def amc_tracking_report(db: Session,user: User,params: dict):
    """List AMC manual-action candidates and their durable completion evidence."""
    rule=params.get("amc_rule") or "send_sum_amc";start=params.get("date_from");end=params.get("date_to");provider=params.get("provider_legacy_id");include_completed=params.get("include_completed",False)
    patients=list(db.scalars(select(Patient).where(Patient.merged_into_id.is_(None)).order_by(Patient.legacy_pid,Patient.id)))
    if provider:
        assigned=set(db.scalars(select(PatientProviderAssignment.patient_id).where(PatientProviderAssignment.legacy_practitioner_id==provider,PatientProviderAssignment.role=="primary",PatientProviderAssignment.status=="active")));patients=[item for item in patients if item.id in assigned]
    patient_map={item.id:item for item in patients};events=list(db.scalars(select(AmcTrackingEvent).where(AmcTrackingEvent.patient_id.in_(list(patient_map))).order_by(AmcTrackingEvent.created_at,AmcTrackingEvent.id))) if patient_map else []
    event_map={}
    for item in events:event_map[(item.rule_id,item.patient_id,item.object_category,item.legacy_object_id)]=item
    def dated(raw):
        day=raw.date() if isinstance(raw,datetime) else raw
        return (start is None or day>=start) and (end is None or day<=end)
    def row(patient,when,source_type,source_uuid,legacy_id,event):
        completed=bool(event and event.completed_at);electronic=bool(event_map.get(("send_sum_elec_amc",patient.id,source_type,legacy_id)) and event_map[("send_sum_elec_amc",patient.id,source_type,legacy_id)].completed_at)
        return {"patient_name":f"{patient.last_name}, {patient.first_name}","patient_uuid":patient.uuid,"legacy_patient_id":patient.legacy_pid,"date":value(when),"source_type":source_type,"source_uuid":source_uuid,"legacy_source_id":legacy_id,"completed":completed,"completed_at":value(event.completed_at) if event else None,"electronically":electronic}
    rows=[]
    if rule=="send_sum_amc":
        for source in db.scalars(select(Referral).where(Referral.patient_id.in_(list(patient_map))).order_by(Referral.referred_at.desc(),Referral.id.desc())) if patient_map else []:
            patient=patient_map[source.patient_id];legacy_id=source.legacy_transaction_id or source.id;event=event_map.get((rule,patient.id,"transactions",legacy_id))
            if dated(source.referred_at) and (include_completed or not (event and event.completed_at)):rows.append(row(patient,source.referred_at,"transactions",source.uuid,legacy_id,event))
    elif rule=="provide_sum_pat_amc":
        for source in db.scalars(select(Encounter).where(Encounter.patient_id.in_(list(patient_map))).order_by(Encounter.occurred_at.desc(),Encounter.id.desc())) if patient_map else []:
            patient=patient_map[source.patient_id];legacy_id=source.legacy_encounter_id or source.id;event=event_map.get((rule,patient.id,"form_encounter",legacy_id))
            if dated(source.occurred_at) and (include_completed or not (event and event.completed_at)):rows.append(row(patient,source.occurred_at,"form_encounter",source.uuid,legacy_id,event))
    else:
        for event in reversed(events):
            if event.rule_id!=rule or not dated(event.created_at) or (event.completed_at and not include_completed):continue
            rows.append(row(patient_map[event.patient_id],event.created_at,event.object_category,event.uuid,event.legacy_object_id,event))
    rows.sort(key=lambda item:(item["date"],item["legacy_patient_id"] or 0,item["legacy_source_id"]),reverse=True)
    columns=["patient_name","patient_uuid","legacy_patient_id","date","source_type","source_uuid","legacy_source_id","completed","completed_at"]
    if rule=="send_sum_amc":columns.append("electronically")
    return columns,rows,{"candidates":len(rows),"completed":sum(bool(item["completed"]) for item in rows),"rule":rule}


def appointment_encounter_report(db: Session,user: User,params: dict):
    """Full-outer appointment/encounter reconciliation with legacy billing diagnostics."""
    today=datetime.now(timezone.utc).date();start=params.get("date_from") or today;end=params.get("date_to") or start
    scope=facility_scope(db,user);requested=params.get("_facility_id");requested_legacy=params.get("_legacy_facility_id")
    allowed_legacy=set(db.scalars(select(Facility.legacy_facility_id).where(Facility.id.in_(scope),Facility.legacy_facility_id.is_not(None)))) if scope is not None else None
    def in_facility(normalized,legacy):
        if requested is not None:return normalized==requested or (requested_legacy is not None and legacy==requested_legacy)
        if scope is None:return True
        return normalized in scope or (allowed_legacy is not None and legacy in allowed_legacy)
    appointments=[item for item in db.scalars(select(Appointment).where(func.date(Appointment.starts_at)>=start,func.date(Appointment.starts_at)<=end).order_by(Appointment.starts_at,Appointment.id)) if item.status!="no-show" and item.legacy_status!="?" and in_facility(item.facility_id,item.legacy_facility_id)]
    encounters=[item for item in db.scalars(select(Encounter).where(func.date(Encounter.occurred_at)>=start,func.date(Encounter.occurred_at)<=end).order_by(Encounter.occurred_at,Encounter.id)) if in_facility(item.facility_id,item.legacy_facility_id)]
    encounters_by_patient={}
    for item in encounters:encounters_by_patient.setdefault(item.patient_id,[]).append(item)
    pairs=[];matched=set()
    for appointment in appointments:
        candidates=[item for item in encounters_by_patient.get(appointment.patient_id,[]) if item.appointment_id==appointment.id or item.occurred_at.date()==appointment.starts_at.date()]
        if candidates:
            for encounter in candidates:pairs.append((appointment,encounter));matched.add(encounter.id)
        else:pairs.append((appointment,None))
    pairs.extend((None,item) for item in encounters if item.id not in matched)
    patient_ids={item.patient_id for pair in pairs for item in pair if item};patients={item.id:item for item in db.scalars(select(Patient).where(Patient.id.in_(patient_ids)))} if patient_ids else {}
    encounter_ids={item.id for _,item in pairs if item};charges={};copays={}
    if encounter_ids:
        for item in db.scalars(select(Charge).where(Charge.encounter_id.in_(encounter_ids),Charge.active.is_(True))):charges.setdefault(item.encounter_id,[]).append(item)
        for item in db.scalars(select(ReceivableActivity).where(ReceivableActivity.encounter_id.in_(encounter_ids),ReceivableActivity.deleted_at.is_(None),ReceivableActivity.payer_type==0,ReceivableActivity.account_code=="PCP")):copays[item.encounter_id]=copays.get(item.encounter_id,Decimal("0"))+item.pay_amount
    code_types={item.key:item for item in db.scalars(select(BillingCodeType))}
    service_codes={(item.code_type_id,item.code,item.modifier or ""):item for item in db.scalars(select(ServiceCode))} if settings.ippf_specific else {}
    gcac_forms=set(db.scalars(select(ClinicalForm.encounter_id).where(ClinicalForm.encounter_id.in_(encounter_ids),ClinicalForm.source_formdir=="LBFgcac"))) if settings.ippf_specific and encounter_ids else set()
    columns=["provider","date","appointment_uuid","encounter_uuid","patient","public_id","patient_uuid","legacy_patient_id","legacy_encounter_id","charges","copays","billed","errors"]
    rows=[];provider_totals={}
    for appointment,encounter in pairs:
        patient=patients[(encounter or appointment).patient_id];errors=[];amount=Decimal("0");is_billed=True;saw_unbilled=False;gcac_related=False
        for charge in charges.get(encounter.id if encounter else None,[]):
            definition=code_types.get(charge.code_system);fee_type=definition.fee if definition else not charge.code_system.upper().startswith(("ICD","DSM"))
            justification_type=definition.justification_type if definition else ("diagnosis" if charge.code_system.upper() in {"CPT4","HCPCS"} else None)
            if fee_type:
                amount+=charge.unit_price
                if not charge.billed:is_billed=False;saw_unbilled=True
                if charge.unit_price==0 and not settings.ippf_specific:errors.append("Missing Fee")
            elif charge.unit_price!=0:errors.append("Fee is not allowed")
            if not settings.simplified_demographics and not charge.authorized:errors.append("Needs Auth")
            if justification_type and not charge.justification:errors.append("Needs Justify")
            if settings.ippf_specific and fee_type and definition:
                catalog=service_codes.get((definition.legacy_type_id,charge.code,charge.modifier or ""))
                if catalog:gcac_related=gcac_related or any(token.startswith("IPPF:25222") for token in (catalog.related_codes or "").split(";"))
        if encounter is None:errors.append("No visit")
        if gcac_related and encounter and encounter.id not in gcac_forms:errors.append("GCAC visit form is missing")
        if saw_unbilled:errors.append("Not billed")
        if amount==0:is_billed=False
        provider=(encounter.provider_name if encounter else None) or "Unknown"
        copay=copays.get(encounter.id if encounter else None,Decimal("0"));when=appointment.starts_at if appointment else encounter.occurred_at
        row={"provider":provider,"date":value(when),"appointment_uuid":appointment.uuid if appointment else None,"encounter_uuid":encounter.uuid if encounter else None,"patient":f"{patient.first_name} {patient.last_name}","public_id":(patient.legacy_payload or {}).get("pubpid") or patient.uuid,"patient_uuid":patient.uuid,"legacy_patient_id":patient.legacy_pid,"legacy_encounter_id":encounter.legacy_encounter_id if encounter else None,"charges":value(amount),"copays":value(copay),"billed":"Y" if is_billed else "","errors":"; ".join(errors)}
        rows.append(row);totals=provider_totals.setdefault(provider,{"encounters":0,"charges":Decimal("0"),"copays":Decimal("0")});totals["encounters"]+=int(encounter is not None);totals["charges"]+=amount;totals["copays"]+=copay
    rows.sort(key=lambda row:(row["provider"],row["date"],row["patient_uuid"],row["encounter_uuid"] or ""))
    provider_summary=[{"provider":provider,"encounters":totals["encounters"],"charges":value(totals["charges"]),"copays":value(totals["copays"])} for provider,totals in sorted(provider_totals.items())]
    totals={"encounters":sum(item["encounters"] for item in provider_totals.values()),"charges":value(sum((item["charges"] for item in provider_totals.values()),Decimal("0"))),"copays":value(sum((item["copays"] for item in provider_totals.values()),Decimal("0"))),"errors":sum(bool(row["errors"]) for row in rows),"providers":provider_summary}
    if not params.get("include_details",True):return ["provider","encounters","charges","copays"],provider_summary,totals
    return columns,rows,totals


def collections_report(db: Session,user: User,params: dict):
    """Integrated A/R collections and aging, preserving legacy responsibility rules."""
    category=params.get("collection_category") or "Due Pt";as_of=params.get("as_of_date") or datetime.now(timezone.utc).date()
    age_columns=params.get("age_columns",3);age_increment=params.get("age_increment_days",30)
    query=select(Encounter).order_by(Encounter.patient_id,Encounter.legacy_encounter_id,Encounter.id)
    if params.get("date_from"):query=query.where(func.date(Encounter.occurred_at)>=params["date_from"])
    if params.get("date_to"):query=query.where(func.date(Encounter.occurred_at)<=params["date_to"])
    if params.get("provider_legacy_id"):query=query.where(Encounter.legacy_provider_id==params["provider_legacy_id"])
    scope=facility_scope(db,user)
    if params.get("_facility_id"):
        query=query.where(or_(Encounter.facility_id==params["_facility_id"],Encounter.legacy_facility_id==params.get("_legacy_facility_id")))
    elif scope is not None:
        legacy=list(db.scalars(select(Facility.legacy_facility_id).where(Facility.id.in_(scope),Facility.legacy_facility_id.is_not(None))))
        query=query.where(or_(Encounter.facility_id.in_(scope),Encounter.legacy_facility_id.in_(legacy)))
    encounters=list(db.scalars(query));encounter_ids=[item.id for item in encounters];patient_ids={item.patient_id for item in encounters}
    patients={item.id:item for item in db.scalars(select(Patient).where(Patient.id.in_(patient_ids)))} if patient_ids else {}
    charges={};sales={};activities={};coverages={}
    if encounter_ids:
        for item in db.scalars(select(Charge).where(Charge.encounter_id.in_(encounter_ids),Charge.active.is_(True))):charges.setdefault(item.encounter_id,[]).append(item)
        for item in db.scalars(select(InventoryTransaction).where(InventoryTransaction.encounter_id.in_(encounter_ids))):
            if (item.legacy_payload or {}).get("fee") not in (None,0,"0","0.00"):sales.setdefault(item.encounter_id,[]).append(item)
        for item in db.scalars(select(ReceivableActivity).where(ReceivableActivity.encounter_id.in_(encounter_ids),ReceivableActivity.deleted_at.is_(None))):activities.setdefault(item.encounter_id,[]).append(item)
    if patient_ids:
        for coverage,payer in db.execute(select(Coverage,Payer).join(Payer,Payer.id==Coverage.payer_id).where(Coverage.patient_id.in_(patient_ids))):coverages.setdefault(coverage.patient_id,[]).append((coverage,payer))
    practitioners={item.legacy_user_id:item for item in db.scalars(select(Practitioner).where(Practitioner.legacy_user_id.is_not(None)))}
    priority={"primary":1,"secondary":2,"tertiary":3};rows=[]
    age_names=[]
    for index in range(age_columns):age_names.append(f"age_{index*age_increment}_{'plus' if index==age_columns-1 else (index+1)*age_increment-1}")
    for encounter in encounters:
        patient=patients.get(encounter.patient_id)
        if not patient:continue
        day=encounter.occurred_at.date();payload=encounter.legacy_payload or {}
        applicable=[(coverage,payer) for coverage,payer in coverages.get(patient.id,[]) if (coverage.starts_on is None or coverage.starts_on<=day) and (coverage.ends_on is None or coverage.ends_on>=day)]
        applicable.sort(key=lambda pair:(priority.get(pair[0].priority,99),pair[0].starts_on or date.min,pair[0].id))
        last_closed=int(payload.get("last_level_closed") or 0);statement_count=int(payload.get("stmt_count") or 0)
        dunning=statement_count if statement_count else last_closed-len(applicable)
        if category in {"Due Ins","Ins Summary"} and dunning>=0:continue
        if category=="Due Pt" and dunning<0:continue
        waiting_index=last_closed if dunning<0 else 0
        waiting=applicable[waiting_index] if waiting_index<len(applicable) else None
        primary=applicable[0] if applicable else None
        if params.get("payer_legacy_id") and (not primary or primary[1].legacy_payer_id!=params["payer_legacy_id"]):continue
        invoice_charges=sum((item.unit_price for item in charges.get(encounter.id,[]) if item.code_system!="COPAY"),Decimal("0"))
        invoice_charges+=sum((item.unit_price for item in charges.get(encounter.id,[]) if item.code_system=="COPAY"),Decimal("0"))
        invoice_charges+=sum((item.fee for item in sales.get(encounter.id,[])),Decimal("0"))
        payment=sum((item.pay_amount for item in activities.get(encounter.id,[])),Decimal("0"))
        adjustment=sum((item.adjustment_amount for item in activities.get(encounter.id,[])),Decimal("0"))
        balance=(invoice_charges-payment-adjustment).quantize(Decimal("0.01"))
        if params.get("with_debt_only") and balance<=0:continue
        if category!="All" and balance==0 and not params.get("include_zero_balances"):continue
        if category=="Credits" and balance>0:continue
        activity_dates=[item.deposit_date or item.check_date or item.posted_at.date() for item in activities.get(encounter.id,[])]
        activity_dates += [item.billed_at.date() for item in charges.get(encounter.id,[]) if item.billed_at]
        aging_date=max([day,*activity_dates]);bucket_date=aging_date if params.get("age_by")=="last_activity" else day;age_days=max(0,(as_of-aging_date).days);bucket_days=max(0,(as_of-bucket_date).days)
        age_values={name:"0.00" for name in age_names}
        if age_names:
            bucket=min(len(age_names)-1,bucket_days//age_increment);age_values[age_names[bucket]]=value(balance)
        patient_payload=patient.legacy_payload or {};referrer=practitioners.get(patient_payload.get("ref_providerID"))
        provider=practitioners.get(encounter.legacy_provider_id)
        coverage=waiting[0] if waiting else primary[0] if primary else None;payer=waiting[1] if waiting else primary[1] if primary else None
        detail_counts={}
        for item in activities.get(encounter.id,[]):
            key=(item.code or ("Copay" if item.account_code=="PCP" else "Claim level"),item.modifier or "");detail_counts[key]=detail_counts.get(key,0)+1
        charge_keys={(item.code,item.modifier or "") for item in charges.get(encounter.id,[]) if item.unit_price}
        insurance_done=bool(charge_keys) and all(detail_counts.get(key,0)>=1 for key in charge_keys)
        error="Ins1 seems done" if category in {"Due Ins","Ins Summary"} and last_closed<1 and insurance_done else "Ins1 seems not done" if last_closed>=1 and not insurance_done else ""
        row={"insurance":payer.name if payer and category in {"Due Ins","Ins Summary"} else "","patient":f"{patient.last_name}, {patient.first_name}"+(f" {patient.middle_name[0]}" if patient.middle_name else ""),"patient_uuid":patient.uuid,"legacy_patient_id":patient.legacy_pid,"public_id":patient_payload.get("pubpid") or patient.uuid,"dob":value(patient.date_of_birth),"policy_number":coverage.policy_number if coverage else "","group_number":coverage.group_number if coverage else "","phone":patient.phone,"city":patient.city,"primary_insurance":primary[1].name if primary else "","provider":f"{provider.last_name}, {provider.first_name}" if provider else encounter.provider_name,"referrer":f"{referrer.last_name}, {referrer.first_name}" if referrer else "","invoice":payload.get("invoice_refno") or f"{patient.legacy_pid}.{encounter.legacy_encounter_id}","encounter_uuid":encounter.uuid,"service_date":value(day),"activity_date":value(aging_date),"charges":value(invoice_charges),"adjustments":value(-adjustment),"paid":value(payment),"balance":value(balance),"aging_days":age_days,"responsibility_level":dunning,"in_collections":bool(payload.get("in_collection")) or "IN COLLECTIONS" in str(patient_payload.get("billing_note") or "").upper(),"billing_error":error,**age_values}
        rows.append(row)
    rows.sort(key=lambda row:(row["insurance"],row["legacy_patient_id"] or 0,row["patient"],row["invoice"]))
    if category=="Ins Summary":
        grouped={}
        for row in rows:
            item=grouped.setdefault(row["insurance"],{"insurance":row["insurance"],"invoices":0,"charges":Decimal("0"),"adjustments":Decimal("0"),"paid":Decimal("0"),"balance":Decimal("0"),**{name:Decimal("0") for name in age_names}});item["invoices"]+=1
            for key in ("charges","adjustments","paid","balance",*age_names):item[key]+=Decimal(row[key])
        columns=["insurance","invoices","charges","adjustments","paid",*age_names,"balance"]
        rows=[{key:value(entry[key]) for key in columns} for entry in grouped.values()]
    else:columns=["insurance","patient","patient_uuid","legacy_patient_id","public_id","dob","policy_number","group_number","phone","city","primary_insurance","provider","referrer","invoice","encounter_uuid","service_date","activity_date","charges","adjustments","paid",*age_names,"balance","aging_days","responsibility_level","in_collections","billing_error"]
    totals={"invoices":sum(row.get("invoices",1) for row in rows),"charges":value(sum((Decimal(row["charges"]) for row in rows),Decimal("0"))),"adjustments":value(sum((Decimal(row["adjustments"]) for row in rows),Decimal("0"))),"paid":value(sum((Decimal(row["paid"]) for row in rows),Decimal("0"))),"balance":value(sum((Decimal(row["balance"]) for row in rows),Decimal("0"))),"as_of_date":value(as_of)}
    for name in age_names:totals[name]=value(sum((Decimal(row[name]) for row in rows),Decimal("0")))
    return columns,rows,totals


def front_receipts_report(db: Session,user: User,params: dict):
    """Front-desk receipts grouped by the legacy patient/timestamp receipt key."""
    today=datetime.now(timezone.utc).date();date_from=params.get("date_from") or today;date_to=params.get("date_to") or today
    start=datetime.combine(date_from,time.min,tzinfo=timezone.utc);end=datetime.combine(date_to+timedelta(days=1),time.min,tzinfo=timezone.utc)
    query=select(FrontOfficePayment,Encounter).join(Encounter,Encounter.id==FrontOfficePayment.encounter_id).where(FrontOfficePayment.received_at>=start,FrontOfficePayment.received_at<end)
    if params.get("provider_legacy_id"):query=query.where(Encounter.legacy_provider_id==params["provider_legacy_id"])
    scope=facility_scope(db,user)
    if params.get("_facility_id"):
        query=query.where(or_(Encounter.facility_id==params["_facility_id"],Encounter.legacy_facility_id==params.get("_legacy_facility_id")))
    elif scope is not None:
        legacy=list(db.scalars(select(Facility.legacy_facility_id).where(Facility.id.in_(scope),Facility.legacy_facility_id.is_not(None))))
        query=query.where(or_(Encounter.facility_id.in_(scope),Encounter.legacy_facility_id.in_(legacy)))
    grouped={}
    for payment,encounter in db.execute(query.order_by(FrontOfficePayment.received_at,FrontOfficePayment.legacy_patient_id,FrontOfficePayment.legacy_payment_id)):
        key=(payment.patient_id,payment.legacy_patient_id,payment.received_at);entry=grouped.setdefault(key,{"payments":[],"encounters":[]});entry["payments"].append(payment);entry["encounters"].append(encounter)
    patient_ids={key[0] for key in grouped if key[0] is not None};patients={item.id:item for item in db.scalars(select(Patient).where(Patient.id.in_(patient_ids)))} if patient_ids else {}
    columns=["received_at","receipt_key","patient","patient_uuid","legacy_patient_id","public_id","method","source","actor","current_amount","previous_amount","total","payment_line_count","encounter_uuids"]
    rows=[];by_method={};current_total=Decimal("0");previous_total=Decimal("0")
    for (patient_id,legacy_pid,received_at),entry in grouped.items():
        payments=entry["payments"];patient=patients.get(patient_id);current=sum((item.current_amount for item in payments),Decimal("0"));previous=sum((item.previous_amount for item in payments),Decimal("0"));method=max((item.method or "" for item in payments),default="");source=max((item.source or "" for item in payments),default="");actor=max((item.actor_name or "" for item in payments),default="")
        total=current+previous;current_total+=current;previous_total+=previous;method_totals=by_method.setdefault(method,{"current_amount":Decimal("0"),"previous_amount":Decimal("0"),"total":Decimal("0"),"receipts":0});method_totals["current_amount"]+=current;method_totals["previous_amount"]+=previous;method_totals["total"]+=total;method_totals["receipts"]+=1
        patient_payload=patient.legacy_payload if patient and patient.legacy_payload else {};stamp=received_at.strftime("%Y%m%d%H%M%S")
        rows.append({"received_at":value(received_at),"receipt_key":f"{legacy_pid}.{stamp}","patient":f"{patient.last_name}, {patient.first_name}"+(f" {patient.middle_name}" if patient and patient.middle_name else "") if patient else f"Legacy patient {legacy_pid}","patient_uuid":patient.uuid if patient else None,"legacy_patient_id":legacy_pid,"public_id":patient_payload.get("pubpid") or (patient.uuid if patient else None),"method":method,"source":source,"actor":actor,"current_amount":value(current),"previous_amount":value(previous),"total":value(total),"payment_line_count":len(payments),"encounter_uuids":sorted({item.uuid for item in entry["encounters"]})})
    rows.sort(key=lambda row:(row["received_at"],row["legacy_patient_id"]))
    method_summary=[{"method":method,**{key:value(val) for key,val in totals.items()}} for method,totals in sorted(by_method.items())]
    return columns,rows,{"receipts":len(rows),"payment_lines":sum(row["payment_line_count"] for row in rows),"current_amount":value(current_total),"previous_amount":value(previous_total),"total":value(current_total+previous_total),"by_method":method_summary}


def receipts_by_method_report(db: Session,user: User,params: dict):
    """Payments and adjustments grouped by payer, method, or check reference."""
    today=datetime.now(timezone.utc).date();date_from=params.get("date_from") or today;date_to=params.get("date_to") or today
    report_by=params.get("receipt_report_by") or "payer";details=params.get("include_details",True);use_invoice=params.get("use_invoice_date",False)
    requested=params.get("procedure_code");requested_type,requested_code=(requested.split(":",1) if requested and ":" in requested else (None,None))
    scope=facility_scope(db,user);allowed_legacy=set(db.scalars(select(Facility.legacy_facility_id).where(Facility.id.in_(scope),Facility.legacy_facility_id.is_not(None)))) if scope is not None else None
    def allowed(encounter):
        if params.get("_facility_id"):return encounter.facility_id==params["_facility_id"] or encounter.legacy_facility_id==params.get("_legacy_facility_id")
        return scope is None or encounter.facility_id in scope or encounter.legacy_facility_id in allowed_legacy
    encounters=list(db.scalars(select(Encounter)));encounters={item.id:item for item in encounters if allowed(item)};encounter_ids=set(encounters)
    patients={item.id:item for item in db.scalars(select(Patient).where(Patient.id.in_({item.patient_id for item in encounters.values()})))} if encounters else {}
    charges={}
    if encounter_ids:
        for item in db.scalars(select(Charge).where(Charge.encounter_id.in_(encounter_ids),Charge.active.is_(True))):charges.setdefault(item.encounter_id,[]).append(item)
    coverages={}
    if patients:
        for coverage,payer in db.execute(select(Coverage,Payer).join(Payer,Payer.id==Coverage.payer_id).where(Coverage.patient_id.in_(patients))):coverages.setdefault(coverage.patient_id,[]).append((coverage,payer))
    valid_form_encounters=set(db.scalars(select(ClinicalForm.encounter_id).where(ClinicalForm.encounter_id.in_(encounter_ids),ClinicalForm.source_formdir=="newpatient"))) if encounter_ids else set()
    rows=[]
    def coverage_for(patient_id,service_date,payer_type):
        priorities={1:"primary",2:"secondary",3:"tertiary"};wanted=priorities.get(payer_type)
        candidates=[pair for pair in coverages.get(patient_id,[]) if pair[0].priority==wanted and (pair[0].starts_on is None or pair[0].starts_on<=service_date) and (pair[0].ends_on is None or pair[0].ends_on>=service_date)]
        return max(candidates,key=lambda pair:(pair[0].starts_on or date.min,pair[0].id)) if candidates else None
    def append_row(encounter,method,reference,transaction_date,payment,adjustment,payer_type,procedure,activity_uuid=None):
        patient=patients.get(encounter.patient_id);coverage=coverage_for(encounter.patient_id,encounter.occurred_at.date(),payer_type);payload=encounter.legacy_payload or {}
        rows.append({"method":method or "Unknown","reference":reference or "","date":value(transaction_date),"invoice":payload.get("invoice_refno") or f"{patient.legacy_pid if patient else encounter.patient_id}-{encounter.legacy_encounter_id}","patient":f"{patient.last_name}, {patient.first_name}"+(f" {patient.middle_name}" if patient and patient.middle_name else "") if patient else None,"patient_uuid":patient.uuid if patient else None,"legacy_patient_id":patient.legacy_pid if patient else None,"policy_number":coverage[0].policy_number if coverage else "","service_date":value(encounter.occurred_at.date()),"procedure":procedure or "","adjustments":value(adjustment),"payments":value(payment),"payer_type":payer_type,"encounter_uuid":encounter.uuid,"activity_uuid":activity_uuid})
    if not requested:
        for encounter in encounters.values():
            if params.get("provider_legacy_id") and encounter.legacy_provider_id!=params["provider_legacy_id"]:continue
            day=encounter.occurred_at.date()
            if day<date_from or day>date_to:continue
            for charge in charges.get(encounter.id,[]):
                if charge.code_system=="COPAY" and charge.unit_price:
                    append_row(encounter,"Patient" if report_by=="payer" else "Co-Pay",charge.description,day,-charge.unit_price,Decimal("0"),0,charge.description)
    if encounter_ids:
        for activity in db.scalars(select(ReceivableActivity).where(ReceivableActivity.encounter_id.in_(encounter_ids),ReceivableActivity.deleted_at.is_(None),or_(ReceivableActivity.pay_amount!=0,ReceivableActivity.adjustment_amount!=0))):
            encounter=encounters[activity.encounter_id]
            if encounter.id not in valid_form_encounters:continue
            matching=[charge for charge in charges.get(encounter.id,[]) if charge.code==activity.code and (charge.modifier or "")== (activity.modifier or "") and charge.code_system not in {"COPAY","TAX"}]
            if params.get("provider_legacy_id"):
                provider=params["provider_legacy_id"]
                if matching:
                    if not any(int((charge.legacy_payload or {}).get("provider_id") or encounter.legacy_provider_id or 0)==provider for charge in matching):continue
                elif encounter.legacy_provider_id!=provider:continue
            if requested_code and not ((activity.code_system in {requested_type,"",None}) and (activity.code or "").startswith(requested_code)):continue
            transaction_date=encounter.occurred_at.date() if use_invoice else activity.deposit_date or activity.posted_at.date()
            if transaction_date<date_from or transaction_date>date_to:continue
            coverage=coverage_for(encounter.patient_id,encounter.occurred_at.date(),activity.payer_type)
            payer=db.get(Payer,activity.payer_id) if activity.payer_id else coverage[1] if coverage else None
            if report_by=="payer":method=payer.name if payer else "Personal pay" if activity.payer_type==0 else "Unnamed insurance company"
            elif report_by=="check_number":method=activity.payment_reference or activity.memo or "Unknown"
            else:method=activity.memo if not activity.legacy_session_id else activity.payment_method_label or activity.payment_method or "Unknown"
            append_row(encounter,method,activity.payment_reference,transaction_date,activity.pay_amount,activity.adjustment_amount,activity.payer_type,activity.code,activity.uuid)
    if report_by=="payer" and details:
        consolidated={}
        for row in rows:
            key=tuple(row[name] for name in ("method","date","legacy_patient_id","encounter_uuid","reference","payer_type","procedure"));item=consolidated.get(key)
            if item:item["payments"]=value(Decimal(item["payments"])+Decimal(row["payments"]));item["adjustments"]=value(Decimal(item["adjustments"])+Decimal(row["adjustments"]));item["activity_uuid"]=None
            else:consolidated[key]=dict(row)
        rows=list(consolidated.values())
    rows.sort(key=lambda row:(row["method"],row["date"],row["legacy_patient_id"] or 0,row["encounter_uuid"],row["reference"],row["payer_type"]))
    grouped={}
    for row in rows:
        item=grouped.setdefault(row["method"],{"adjustments":Decimal("0"),"payments":Decimal("0"),"items":0});item["adjustments"]+=Decimal(row["adjustments"]);item["payments"]+=Decimal(row["payments"]);item["items"]+=1
    summary=[{"method":method,"adjustments":value(item["adjustments"]),"payments":value(item["payments"]),"items":item["items"]} for method,item in sorted(grouped.items())]
    totals={"adjustments":value(sum((item["adjustments"] for item in grouped.values()),Decimal("0"))),"payments":value(sum((item["payments"] for item in grouped.values()),Decimal("0"))),"items":len(rows),"by_method":summary}
    if not details:return ["method","adjustments","payments","items"],summary,totals
    columns=["method","reference","date","invoice","patient","patient_uuid","legacy_patient_id","policy_number","service_date","procedure","adjustments","payments","payer_type","encounter_uuid","activity_uuid"]
    return columns,rows,totals


def payment_processing_report(db: Session,user: User,params: dict):
    """Gateway audit history with preserved reversal links and safe derived fields."""
    now=datetime.now(timezone.utc);start=params.get("occurred_from") or now-timedelta(days=7);end=params.get("occurred_to") or now
    query=select(PaymentProcessingAudit).where(PaymentProcessingAudit.occurred_at>start,PaymentProcessingAudit.occurred_at<end)
    if params.get("_patient_id"):query=query.where(PaymentProcessingAudit.patient_id==params["_patient_id"])
    if params.get("payment_service"):query=query.where(PaymentProcessingAudit.service==params["payment_service"])
    if params.get("payment_ticket"):query=query.where(PaymentProcessingAudit.ticket==params["payment_ticket"])
    if params.get("payment_transaction_id"):query=query.where(PaymentProcessingAudit.transaction_id==params["payment_transaction_id"])
    if params.get("payment_action"):query=query.where(PaymentProcessingAudit.action_name==params["payment_action"])
    items=list(db.scalars(query.order_by(PaymentProcessingAudit.occurred_at.desc(),PaymentProcessingAudit.id.desc())))
    patient_ids={item.patient_id for item in items if item.patient_id};patients={item.id:item for item in db.scalars(select(Patient).where(Patient.id.in_(patient_ids)))} if patient_ids else {}
    def nested(payload,*path):
        current=payload or {}
        for key in path:
            if not isinstance(current,dict):return None
            current=current.get(key)
        return current
    def error_for(item):
        if item.success:return ""
        payload=item.audit_payload
        if payload is None:return "Encrypted legacy audit detail requires source installation keys"
        if nested(payload,"get","cancel")=="cancel":return "Cancelled"
        if item.action_name=="Sale":return " - ".join(filter(None,(str(nested(payload,"post","status_name") or ""),str(nested(payload,"post","description") or ""))))
        if item.action_name in {"void","credit"}:
            status=nested(payload,"post","status")
            if status in {"baddata","error"}:return f"Aborted since unable to submit transaction: {status} {nested(payload,'post','error') or ''} {nested(payload,'post','offenders') or ''}".strip()
            if payload.get("check_querystring_hash") is False:return "querystring hash was invalid"
            if payload.get("token_request_error"):return f"Aborted since unable to obtain token: {payload['token_request_error']}"
            if payload.get("error_custom"):return str(payload["error_custom"])
            complete=payload.get("complete_transaction")
            if isinstance(complete,dict) and complete.get("status")!="accepted":return "Unable to complete transaction: "+"; ".join(f"{key}:{val}" for key,val in complete.items() if key or val)
        return ""
    front_labels={"patient":"Patient Portal","clinic-phone":"Front Office by Phone","clinic-retail":"Front Office in Person"}
    columns=["date","service","front","ticket","transaction_id","patient","patient_uuid","legacy_patient_id","action","success","amount","amount_text","error_message","reverted","revert_action","revert_date","revert_transaction_id","mapped_transaction_id","reversal_status","legacy_payload_status","audit_uuid"]
    rows=[]
    for item in items:
        patient=patients.get(item.patient_id);front=nested(item.audit_payload,"get","front");reversal=""
        if item.action_name=="Sale" and item.reverted:reversal=f"Reversed via {item.revert_action_name or 'unknown'} by {item.revert_transaction_id or 'unknown transaction'}"
        elif item.action_name in {"void","credit"} and item.success:reversal=f"{item.action_name.title()} of {item.map_transaction_id or 'unknown transaction'}"
        elif item.action_name=="Sale" and item.success:reversal="Gateway action required for void or credit"
        rows.append({"date":value(item.occurred_at),"service":item.service,"front":front_labels.get(front,front or ""),"ticket":item.ticket,"transaction_id":item.transaction_id,"patient":f"{patient.last_name}, {patient.first_name}" if patient else None,"patient_uuid":patient.uuid if patient else None,"legacy_patient_id":item.legacy_patient_id,"action":item.action_name,"success":item.success,"amount":value(item.amount),"amount_text":item.amount_text,"error_message":error_for(item),"reverted":item.reverted,"revert_action":item.revert_action_name,"revert_date":value(item.reverted_at),"revert_transaction_id":item.revert_transaction_id,"mapped_transaction_id":item.map_transaction_id,"reversal_status":reversal,"legacy_payload_status":"readable-json" if item.payload_readable else "preserved-encrypted-source","audit_uuid":item.uuid})
    amounts=[item.amount for item in items if item.amount is not None]
    return columns,rows,{"transactions":len(rows),"successful":sum(item.success for item in items),"failed":sum(not item.success for item in items),"reverted":sum(item.reverted for item in items),"amount":value(sum(amounts,Decimal("0"))),"encrypted_legacy_payloads":sum(not item.payload_readable for item in items)}


def prepayment_balance_report(db: Session,user: User,params: dict):
    """Open legacy prepayments whose received amount is not fully applied."""
    del user
    query=select(ReceivableSession).where(ReceivableSession.adjustment_code=="pre_payment",ReceivableSession.closed.is_(False))
    if params.get("date_from"):query=query.where(ReceivableSession.check_date>=params["date_from"])
    if params.get("date_to"):query=query.where(ReceivableSession.check_date<=params["date_to"])
    if params.get("_patient_id"):query=query.where(ReceivableSession.patient_id==params["_patient_id"])
    if params.get("parked_only"):query=query.where(ReceivableSession.global_amount!=0)
    sessions=list(db.scalars(query));keys={(item.legacy_session_id,item.legacy_patient_id) for item in sessions}
    applied={}
    if keys:
        activities=db.scalars(select(ReceivableActivity).where(ReceivableActivity.deleted_at.is_(None),ReceivableActivity.legacy_session_id.in_({key[0] for key in keys})))
        for activity in activities:
            key=(activity.legacy_session_id,activity.legacy_patient_id)
            if key in keys:applied[key]=applied.get(key,Decimal("0"))+activity.pay_amount
    patient_ids={item.patient_id for item in sessions if item.patient_id is not None}
    patients={item.id:item for item in db.scalars(select(Patient).where(Patient.id.in_(patient_ids)))} if patient_ids else {}
    columns=["patient","patient_uuid","legacy_patient_id","session_uuid","legacy_session_id","reference","check_date","days_open","received","applied","in_global","unapplied"]
    rows=[];today=datetime.now(timezone.utc).date()
    for item in sessions:
        used=applied.get((item.legacy_session_id,item.legacy_patient_id),Decimal("0"));unapplied=item.pay_total-used
        if unapplied<=Decimal("0.005"):continue
        patient=patients.get(item.patient_id);name=""
        if patient:
            given=" ".join(part for part in (patient.first_name,patient.middle_name) if part);name=f"{patient.last_name}, {given}" if patient.last_name and given else patient.last_name or given
        rows.append({"patient":name,"patient_uuid":patient.uuid if patient else None,"legacy_patient_id":item.legacy_patient_id,"session_uuid":item.uuid,"legacy_session_id":item.legacy_session_id,"reference":item.reference or "","check_date":value(item.check_date),"days_open":(today-item.check_date).days if item.check_date else 0,"received":value(item.pay_total),"applied":value(used),"in_global":value(item.global_amount),"unapplied":value(unapplied)})
    rows.sort(key=lambda row:(-Decimal(row["unapplied"]),row["check_date"] is not None,row["check_date"] or "",row["legacy_session_id"]))
    money=lambda field:value(sum((Decimal(row[field]) for row in rows),Decimal("0")))
    return columns,rows,{"sessions":len(rows),"received":money("received"),"applied":money("applied"),"in_global":money("in_global"),"unapplied":money("unapplied")}


def service_code_financial_report(db: Session,user: User,params: dict):
    """Financial charge/payment/adjustment summary using the legacy join semantics."""
    today=datetime.now(timezone.utc).date();date_from=params.get("date_from") or today;date_to=params.get("date_to") or today
    scope=facility_scope(db,user);allowed_legacy=set(db.scalars(select(Facility.legacy_facility_id).where(Facility.id.in_(scope),Facility.legacy_facility_id.is_not(None)))) if scope is not None else None
    encounter_query=select(Encounter).where(Encounter.occurred_at>=datetime.combine(date_from,time.min,tzinfo=timezone.utc),Encounter.occurred_at<datetime.combine(date_to+timedelta(days=1),time.min,tzinfo=timezone.utc))
    if params.get("_facility_id"):encounter_query=encounter_query.where(or_(Encounter.facility_id==params["_facility_id"],Encounter.legacy_facility_id==params.get("_legacy_facility_id")))
    elif scope is not None:encounter_query=encounter_query.where(or_(Encounter.facility_id.in_(scope),Encounter.legacy_facility_id.in_(allowed_legacy)))
    encounters={item.id:item for item in db.scalars(encounter_query)}
    type_rows=list(db.scalars(select(BillingCodeType).where(BillingCodeType.fee.is_(True))));fee_types={item.key:item.legacy_type_id for item in type_rows}
    flags={}
    for item in db.scalars(select(ServiceCode)):
        key=(item.code,item.code_type_id);flags[key]=flags.get(key,False) or item.financial_reporting
    applied={}
    legacy_encounters={item.legacy_encounter_id for item in encounters.values()}
    if legacy_encounters:
        for item in db.scalars(select(ReceivableActivity).where(ReceivableActivity.deleted_at.is_(None),ReceivableActivity.legacy_encounter_id.in_(legacy_encounters))):
            key=(item.legacy_patient_id,item.legacy_encounter_id,item.code or "");entry=applied.setdefault(key,[Decimal("0"),Decimal("0")]);entry[0]+=item.pay_amount;entry[1]+=item.adjustment_amount
    grouped={}
    for charge in db.scalars(select(Charge).where(Charge.encounter_id.in_(encounters),Charge.active.is_(True))) if encounters else []:
        encounter=encounters[charge.encounter_id];payload=charge.legacy_payload or {};code_type=charge.code_system
        if code_type=="COPAY" or code_type not in fee_types:continue
        if params.get("provider_legacy_id") and int(payload.get("provider_id") or 0)!=params["provider_legacy_id"]:continue
        patient_pid=int(payload.get("pid") or 0);legacy_encounter=int(payload.get("encounter") or encounter.legacy_encounter_id or 0);activity=applied.get((patient_pid,legacy_encounter,charge.code))
        if activity is None:continue
        entry=grouped.setdefault(charge.code,{"procedure_code":charge.code,"units":0,"amount_billed":Decimal("0"),"paid_amount":Decimal("0"),"adjustment_amount":Decimal("0"),"financial_reporting":False})
        entry["units"]+=charge.units;entry["amount_billed"]+=charge.unit_price;entry["paid_amount"]+=activity[0];entry["adjustment_amount"]+=activity[1]
        entry["financial_reporting"]=entry["financial_reporting"] or flags.get((charge.code,fee_types[code_type]),False)
    rows=[]
    for code,entry in sorted(grouped.items()):
        if params.get("financial_reporting_only") and not entry["financial_reporting"]:continue
        balance=entry["amount_billed"]-entry["paid_amount"]-entry["adjustment_amount"]
        rows.append({**entry,"amount_billed":value(entry["amount_billed"]),"paid_amount":value(entry["paid_amount"]),"adjustment_amount":value(entry["adjustment_amount"]),"balance_amount":value(balance)})
    money=lambda field:value(sum((Decimal(row[field]) for row in rows),Decimal("0")))
    columns=["procedure_code","units","amount_billed","paid_amount","adjustment_amount","balance_amount","financial_reporting"]
    return columns,rows,{"codes":len(rows),"units":sum(row["units"] for row in rows),"amount_billed":money("amount_billed"),"paid_amount":money("paid_amount"),"adjustment_amount":money("adjustment_amount"),"balance_amount":money("balance_amount")}


def real_world_testing_2026_report(db: Session,user: User,params: dict):
    """ONC real-world-testing evidence for the mandated 2026 measurement period."""
    del user,params
    start=datetime(2026,4,1,tzinfo=timezone.utc);end=datetime(2026,10,1,tzinfo=timezone.utc)
    events=list(db.scalars(select(RegulatoryMetricEvent).where(RegulatoryMetricEvent.occurred_at>=start,RegulatoryMetricEvent.occurred_at<end).order_by(RegulatoryMetricEvent.occurred_at,RegulatoryMetricEvent.id)))
    counts={kind:sum(item.metric_type==kind for item in events) for kind in ("ccda-generated","direct-sent","direct-received","qrda-import","qrda3-export","ehi-export")}
    api=[item for item in events if item.metric_type=="api-request"]
    rows=[
        {"metric":1,"measure":"generated_ccda_documents","resource":None,"count":counts["ccda-generated"]},
        {"metric":2,"measure":"sent_direct_messages","resource":None,"count":counts["direct-sent"]},
        {"metric":2,"measure":"received_direct_messages","resource":None,"count":counts["direct-received"]},
        {"metric":3,"measure":"qrda_imports","resource":None,"count":counts["qrda-import"]},
        {"metric":4,"measure":"generated_cqm_qrda3_reports","resource":None,"count":counts["qrda3-export"]},
        {"metric":5,"measure":"successful_api_requests","resource":None,"count":sum(item.success is True for item in api)},
        {"metric":5,"measure":"unsuccessful_api_requests","resource":None,"count":sum(item.success is not True for item in api)},
        {"metric":5,"measure":"api_requests_by_users","resource":None,"count":sum(item.success is True and item.actor_kind=="user" for item in api)},
        {"metric":5,"measure":"api_requests_by_patients","resource":None,"count":sum(item.success is True and item.actor_kind=="patient" for item in api)},
    ]
    resources={}
    for item in api:
        if item.success is True and item.resource:resources[item.resource]=resources.get(item.resource,0)+1
    rows.extend({"metric":5,"measure":"api_requests_for_resource","resource":resource,"count":count} for resource,count in sorted(resources.items()))
    rows.append({"metric":6,"measure":"ehi_exports","resource":None,"count":counts["ehi-export"]})
    return ["metric","measure","resource","count"],rows,{"measurement_period_start":"2026-04-01","measurement_period_end":"2026-09-30","evidence_events":len(events),"metrics":6}


def appointment_scope(query, db: Session, user: User):
    scope=facility_scope(db,user)
    if scope is None: return query
    legacy=list(db.scalars(select(Facility.legacy_facility_id).where(Facility.id.in_(scope),Facility.legacy_facility_id.is_not(None))))
    return query.where(or_(Appointment.facility_id.in_(scope),Appointment.legacy_facility_id.in_(legacy)))


def selected_facility(query, params: dict):
    facility_id=params.get("_facility_id"); legacy_id=params.get("_legacy_facility_id")
    if facility_id: return query.where(or_(Appointment.facility_id==facility_id,Appointment.legacy_facility_id==legacy_id))
    return query


def inventory_effects(item: InventoryTransaction) -> list[tuple[int, int]]:
    quantity=abs(item.quantity)
    if item.transaction_type=="transfer":
        effects=[(item.lot_id,-quantity)] if item.lot_id else []
        if item.destination_lot_id: effects.append((item.destination_lot_id,quantity))
        return effects
    if not item.lot_id: return []
    if item.transaction_type=="purchase": return [(item.lot_id,quantity)]
    if item.transaction_type=="adjustment": return [(item.lot_id,item.quantity)]
    return [(item.lot_id,-quantity)]


def inventory_activity(db: Session, user: User, params: dict) -> tuple[list[str],list[dict],dict]:
    date_from=params.get("date_from") or date.min
    date_to=params.get("date_to") or date.max
    lot_query=select(InventoryLot,InventoryProduct).join(InventoryProduct,InventoryProduct.id==InventoryLot.product_id)
    scope=warehouse_scope(db,user)
    if scope is not None: lot_query=lot_query.where(InventoryLot.warehouse_id.in_(scope))
    if params.get("warehouse_code"): lot_query=lot_query.where(InventoryLot.warehouse_id==params["warehouse_code"])
    lot_rows=db.execute(lot_query).all()
    lot_by_id={lot.id:(lot,product) for lot,product in lot_rows}
    if not lot_by_id:
        columns=["product","ndc","warehouse","starting_inventory","sales","distributions","purchases","transfers","adjustments","ending_inventory"]
        return columns,[],{"starting_inventory":0,"sales":0,"distributions":0,"purchases":0,"transfers":0,"adjustments":0,"ending_inventory":0}
    transactions=list(db.scalars(select(InventoryTransaction).where(or_(InventoryTransaction.lot_id.in_(lot_by_id),InventoryTransaction.destination_lot_id.in_(lot_by_id)))))
    effects_by_lot={lot_id:[] for lot_id in lot_by_id}
    for transaction in transactions:
        for lot_id,effect in inventory_effects(transaction):
            if lot_id in effects_by_lot: effects_by_lot[lot_id].append((transaction,effect))
    grouped={}
    for lot_id,(lot,product) in lot_by_id.items():
        effects=effects_by_lot[lot_id]
        baseline=lot.on_hand-sum(effect for _,effect in effects)
        starting=baseline+sum(effect for item,effect in effects if item.occurred_on<date_from)
        if lot.destroyed_at and lot.destroyed_at<date_from: starting=0
        ending=baseline+sum(effect for item,effect in effects if item.occurred_on<=date_to)
        if lot.destroyed_at and lot.destroyed_at<=date_to: ending=0
        key=(product.id,lot.warehouse_id)
        row=grouped.setdefault(key,{"product":product.name,"ndc":product.ndc_number,"warehouse":lot.warehouse_id,"starting_inventory":0,"sales":0,"distributions":0,"purchases":0,"transfers":0,"adjustments":0,"ending_inventory":0})
        row["starting_inventory"]+=starting;row["ending_inventory"]+=ending
        for item,effect in effects:
            if not date_from<=item.occurred_on<=date_to: continue
            category={"dispense":"sales","consumption":"distributions","return":"distributions","purchase":"purchases","transfer":"transfers","adjustment":"adjustments"}.get(item.transaction_type,"adjustments")
            row[category]+=effect
        if lot.destroyed_at and date_from<=lot.destroyed_at<=date_to:
            before_destroy=baseline+sum(effect for item,effect in effects if item.occurred_on<=lot.destroyed_at)
            row["adjustments"]-=before_destroy
    columns=["product","ndc","warehouse","starting_inventory","sales","distributions","purchases","transfers","adjustments","ending_inventory"]
    rows=sorted(grouped.values(),key=lambda row:(row["product"],row["warehouse"]))
    totals={column:sum(row[column] for row in rows) for column in columns[3:]}
    return columns,rows,totals


def insurance_allocation(db: Session, user: User, params: dict) -> tuple[list[str],list[dict],dict]:
    start,end=bounds(params.get("date_from"),params.get("date_to"))
    encounter_query=select(Encounter,Appointment).outerjoin(Appointment,Appointment.id==Encounter.appointment_id)
    scope=facility_scope(db,user)
    if scope is not None:
        legacy_ids=list(db.scalars(select(Facility.legacy_facility_id).where(Facility.id.in_(scope),Facility.legacy_facility_id.is_not(None))))
        encounter_query=encounter_query.where(or_(Appointment.facility_id.in_(scope),Appointment.legacy_facility_id.in_(legacy_ids)))
    if params.get("_facility_id"):
        encounter_query=encounter_query.where(or_(Appointment.facility_id==params["_facility_id"],Appointment.legacy_facility_id==params.get("_legacy_facility_id")))
    if start:encounter_query=encounter_query.where(Encounter.occurred_at>=start)
    if end:encounter_query=encounter_query.where(Encounter.occurred_at<end)
    encounters=[encounter for encounter,_ in db.execute(encounter_query.order_by(Encounter.patient_id,Encounter.id))]
    columns=["insurance","charges","visits","patients","patient_percent"]
    if not encounters:return columns,[],{"charges":"0.00","visits":0,"patients":0}
    encounter_ids=[item.id for item in encounters]
    charge_rows=list(db.scalars(select(Charge).where(Charge.encounter_id.in_(encounter_ids),Charge.active.is_(True),func.upper(Charge.code_system)!="COPAY",Charge.unit_price!=0)))
    charges_by_encounter={item.id:Decimal("0") for item in encounters}
    for charge in charge_rows:charges_by_encounter[charge.encounter_id]+=charge.unit_price*charge.units
    patient_ids={item.patient_id for item in encounters if charges_by_encounter[item.id]}
    coverage_rows=db.execute(select(Coverage,Payer).join(Payer,Payer.id==Coverage.payer_id).where(Coverage.patient_id.in_(patient_ids),Coverage.priority=="primary")).all() if patient_ids else []
    coverages={patient_id:[] for patient_id in patient_ids}
    for coverage,payer in coverage_rows:coverages[coverage.patient_id].append((coverage,payer))
    grouped={};seen_patients=set()
    for encounter in encounters:
        amount=charges_by_encounter[encounter.id]
        if not amount:continue
        on=encounter.occurred_at.date()
        eligible=[pair for pair in coverages.get(encounter.patient_id,[]) if pair[0].starts_on is None or pair[0].starts_on<=on]
        eligible.sort(key=lambda pair:(pair[0].starts_on or date.min,pair[0].id),reverse=True)
        insurance=eligible[0][1].name if eligible else "-- No Insurance --"
        row=grouped.setdefault(insurance,{"insurance":insurance,"charges":Decimal("0"),"visits":0,"patients":0})
        row["charges"]+=amount;row["visits"]+=1
        if encounter.patient_id not in seen_patients:row["patients"]+=1;seen_patients.add(encounter.patient_id)
    patient_count=len(seen_patients)
    rows=[]
    for insurance,row in sorted(grouped.items()):
        rows.append({**row,"charges":f'{row["charges"]:.2f}',"patient_percent":f'{row["patients"]*100/patient_count:.1f}' if patient_count else "0.0"})
    return columns,rows,{"charges":f'{sum((row["charges"] for row in grouped.values()),Decimal("0")):.2f}',"visits":sum(row["visits"] for row in grouped.values()),"patients":patient_count}


def audit_integrity_report(db: Session, params: dict) -> tuple[list[str],list[dict],dict]:
    start,end=bounds(params.get("date_from"),params.get("date_to"))
    staff_query=select(AuditEvent)
    identity_query=select(IdentityAuditEvent)
    if start:
        staff_query=staff_query.where(AuditEvent.occurred_at>=start);identity_query=identity_query.where(IdentityAuditEvent.occurred_at>=start)
    if end:
        staff_query=staff_query.where(AuditEvent.occurred_at<end);identity_query=identity_query.where(IdentityAuditEvent.occurred_at<end)
    events=[("staff",item) for item in db.scalars(staff_query)]+[("identity",item) for item in db.scalars(identity_query)]
    seals={(item.stream,item.event_id):item for item in db.scalars(select(AuditEventSeal))}
    columns=["stream","event_id","occurred_at","actor","action","resource_type","resource_id","integrity","stored_checksum","computed_checksum"]
    rows=[];tampered=0;unsealed=0
    for stream,item in events:
        seal=seals.get((stream,item.id));computed=audit_event_checksum(stream,item)
        if seal and seal.checksum==computed: continue
        integrity="tampered" if seal else "unsealed"
        tampered+=integrity=="tampered";unsealed+=integrity=="unsealed"
        actor=str(item.actor_id) if stream=="staff" else (f"user:{item.user_id}" if item.user_id else f"portal:{item.portal_account_id}")
        rows.append({"stream":stream,"event_id":item.id,"occurred_at":value(item.occurred_at),"actor":actor,"action":item.action,"resource_type":item.resource_type,"resource_id":item.resource_id,"integrity":integrity,"stored_checksum":seal.checksum if seal else None,"computed_checksum":computed})
    staff_ids=set(db.scalars(select(AuditEvent.id)));identity_ids=set(db.scalars(select(IdentityAuditEvent.id)))
    deleted=0
    for seal in seals.values():
        sealed_at=seal.created_at if seal.created_at.tzinfo else seal.created_at.replace(tzinfo=timezone.utc)
        if (start and sealed_at<start) or (end and sealed_at>=end): continue
        existing=seal.event_id in (staff_ids if seal.stream=="staff" else identity_ids)
        if existing: continue
        deleted+=1
        rows.append({"stream":seal.stream,"event_id":seal.event_id,"occurred_at":value(seal.created_at),"actor":None,"action":None,"resource_type":None,"resource_id":None,"integrity":"deleted","stored_checksum":seal.checksum,"computed_checksum":None})
    rows.sort(key=lambda row:(row["occurred_at"],row["stream"],row["event_id"]))
    return columns,rows,{"scanned":len(events),"tampered":tampered,"unsealed":unsealed,"deleted":deleted,"integrity_failures":len(rows)}


def superbill_report(db: Session,user: User,params: dict):
    """Printable legacy Superbill: qualifying encounters, demographics, coverage, charges and copay."""
    start=params.get("date_from");end=params.get("date_to")
    if not start or not end:raise HTTPException(status_code=422,detail="Superbill requires date_from and date_to")
    lower,upper=bounds(start,end);scope=facility_scope(db,user)
    query=(select(ClinicalForm,Encounter,Patient).join(Encounter,Encounter.id==ClinicalForm.encounter_id).join(Patient,Patient.id==ClinicalForm.patient_id)
        .where(ClinicalForm.title=="New Patient Encounter",ClinicalForm.authored_at>=lower,ClinicalForm.authored_at<upper,Patient.merged_into_id.is_(None)))
    if params.get("_patient_id"):query=query.where(Patient.id==params["_patient_id"])
    if scope is not None:query=query.where(Encounter.facility_id.in_(scope))
    selected=list(db.execute(query.order_by(ClinicalForm.authored_at.desc(),ClinicalForm.id.desc())))
    patient_fields=["title","fname","mname","lname","sex","ss","DOB","street","city","state","postal_code","country_code","occupation","phone_home","phone_biz","phone_contact","contact_relationship","hipaa_mail","hipaa_voice","hipaa_notice","hipaa_message"]
    insurance_fields=["provider_name","plan_name","policy_number","group_number","subscriber_fname","subscriber_mname","subscriber_lname","subscriber_relationship","subscriber_ss","subscriber_DOB","subscriber_phone","subscriber_street","subscriber_postal_code","subscriber_city","subscriber_state","subscriber_country","subscriber_employer","subscriber_employer_street","subscriber_employer_city","subscriber_employer_postal_code","subscriber_employer_state","subscriber_employer_country"]
    base_columns=["superbill_uuid","encounter_uuid","legacy_encounter_id","encounter_date","billing_facility","billing_facility_address","patient_uuid","legacy_patient_id"]
    columns=base_columns+[f"patient_{field}" for field in patient_fields]+[f"{priority}_{field}" for priority in ("primary","secondary","tertiary") for field in insurance_fields]+["charge_date","provider","code_type","code","modifier","code_text","fee","encounter_subtotal","copay_paid","encounter_total","physician_signature"]
    patient_ids={patient.id for _,_,patient in selected};encounter_ids={encounter.id for _,encounter,_ in selected}
    coverage_history={}
    if patient_ids:
        for coverage,payer in db.execute(select(Coverage,Payer).join(Payer,Payer.id==Coverage.payer_id).where(Coverage.patient_id.in_(patient_ids)).order_by(Coverage.starts_on.nullsfirst(),Coverage.id)):
            payload=dict(coverage.legacy_payload or {});payload["provider_name"]=payer.name
            payload.setdefault("plan_name",coverage.plan_name);payload.setdefault("policy_number",coverage.policy_number);payload.setdefault("group_number",coverage.group_number);payload.setdefault("subscriber_relationship",coverage.relationship)
            names=coverage.subscriber_name.split();payload.setdefault("subscriber_fname",names[0] if names else None);payload.setdefault("subscriber_lname",names[-1] if len(names)>1 else None)
            current=coverage_history.setdefault((coverage.patient_id,coverage.priority),{})
            for field in insurance_fields:
                candidate=payload.get(field)
                if candidate not in (None,""):current[field]=candidate
    charges={encounter_id:[] for encounter_id in encounter_ids}
    if encounter_ids:
        for charge in db.scalars(select(Charge).where(Charge.encounter_id.in_(encounter_ids),Charge.active.is_(True)).order_by(Charge.billed_at,Charge.id)):charges[charge.encounter_id].append(charge)
    copays={encounter_id:Decimal("0") for encounter_id in encounter_ids}
    if encounter_ids:
        for activity in db.scalars(select(ReceivableActivity).where(ReceivableActivity.encounter_id.in_(encounter_ids),ReceivableActivity.payer_type==0,ReceivableActivity.account_code=="PCP",ReceivableActivity.deleted_at.is_(None))):copays[activity.encounter_id]+=activity.pay_amount
    practitioners={item.legacy_user_id:" ".join(filter(None,(item.first_name,item.last_name))) for item in db.scalars(select(Practitioner).where(Practitioner.legacy_user_id.is_not(None)))}
    facility_query=select(Facility).where(Facility.billing_location.is_(True),Facility.active.is_(True))
    if scope is not None:facility_query=facility_query.where(Facility.id.in_(scope))
    billing_facility=db.scalar(facility_query.order_by(Facility.id).limit(1))
    facility_name=billing_facility.name if billing_facility else None
    facility_address=", ".join(filter(None,((billing_facility.street if billing_facility else None),(billing_facility.city if billing_facility else None),(billing_facility.state if billing_facility else None),(billing_facility.postal_code if billing_facility else None)))) or None
    rows=[];charge_total=Decimal("0");copay_total=Decimal("0")
    normalized_patient={"fname":"first_name","mname":"middle_name","lname":"last_name","sex":"sex","DOB":"date_of_birth","street":"address_line_1","city":"city","state":"state","postal_code":"postal_code","country_code":"country_code","phone_home":"phone"}
    for form,encounter,patient in selected:
        patient_payload=dict(patient.legacy_payload or {})
        for source,target in normalized_patient.items():
            if patient_payload.get(source) in (None,""):patient_payload[source]=value(getattr(patient,target))
        total=sum((charge.unit_price for charge in charges[encounter.id]),Decimal("0"));copay=abs(copays[encounter.id]);charge_total+=total;copay_total+=copay
        base={"superbill_uuid":form.uuid,"encounter_uuid":encounter.uuid,"legacy_encounter_id":encounter.legacy_encounter_id,"encounter_date":value(form.authored_at),"billing_facility":facility_name,"billing_facility_address":facility_address,"patient_uuid":patient.uuid,"legacy_patient_id":patient.legacy_pid}
        base.update({f"patient_{field}":patient_payload.get(field) for field in patient_fields})
        for priority in ("primary","secondary","tertiary"):
            payload=coverage_history.get((patient.id,priority),{})
            base.update({f"{priority}_{field}":payload.get(field) for field in insurance_fields})
        base.update({"encounter_subtotal":f"{total+copay:.2f}","copay_paid":f"{copay:.2f}","encounter_total":f"{total:.2f}","physician_signature":""})
        detail=charges[encounter.id] or [None]
        for charge in detail:
            payload=charge.legacy_payload or {} if charge else {};raw_provider=payload.get("provider_id") if charge else None;provider_id=int(raw_provider) if str(raw_provider or "").isdigit() else 0
            provider=practitioners.get(provider_id) if provider_id else (encounter.provider_name or practitioners.get(encounter.legacy_provider_id))
            rows.append(base|{"charge_date":value(charge.billed_at) if charge else None,"provider":provider,"code_type":charge.code_system if charge else None,"code":charge.code if charge else None,"modifier":charge.modifier if charge else None,"code_text":charge.description if charge else None,"fee":f"{charge.unit_price:.2f}" if charge else None})
    return columns,rows,{"superbills":len(selected),"charge_lines":sum(len(items) for items in charges.values()),"charges":f"{charge_total:.2f}","copay_paid":f"{copay_total:.2f}","subtotals":f"{charge_total+copay_total:.2f}"}


def non_reported_syndromic_report(db: Session,params: dict):
    """Find reportable ICD-9 issues not yet recorded as sent to syndromic surveillance."""
    requested=set(params.get("reportable_code_ids") or [])
    reportable={}
    for service,code_type in db.execute(select(ServiceCode,BillingCodeType).join(BillingCodeType,BillingCodeType.legacy_type_id==ServiceCode.code_type_id)):
        payload=service.legacy_payload or {}
        if not payload.get("reportable") or code_type.key.upper()!="ICD9" or (requested and service.legacy_code_id not in requested):continue
        reportable.setdefault(service.code,(service,code_type))
    submitted=set(db.scalars(select(SyndromicSubmission.clinical_item_id)))
    query=select(ClinicalItem,Patient).join(Patient,Patient.id==ClinicalItem.patient_id).where(ClinicalItem.code_system=="ICD9",ClinicalItem.id.not_in(submitted),Patient.merged_into_id.is_(None))
    start,end=bounds(params.get("date_from"),params.get("date_to"))
    issue_date=func.coalesce(ClinicalItem.recorded_at,ClinicalItem.created_at)
    if start:query=query.where(issue_date>=start)
    if end:query=query.where(issue_date<end)
    if params.get("_patient_id"):query=query.where(Patient.id==params["_patient_id"])
    columns=["issue_uuid","legacy_issue_id","patient_uuid","legacy_patient_id","patient_name","diagnosis","issue_title","issue_date","begin_date","code_text","legacy_code_id","date_of_birth","sex","marital_status","language","address","country_code","phone_home","phone_business"]
    rows=[]
    for item,patient in db.execute(query.order_by(issue_date,ClinicalItem.id)):
        if item.code not in reportable:continue
        service,_=reportable[item.code];payload=patient.legacy_payload or {};recorded=item.recorded_at or item.created_at
        rows.append({"issue_uuid":item.uuid,"legacy_issue_id":item.legacy_list_id,"patient_uuid":patient.uuid,"legacy_patient_id":patient.legacy_pid,"patient_name":" ".join(filter(None,(patient.first_name,patient.middle_name,patient.last_name))),"diagnosis":f"ICD9:{item.code}","issue_title":item.title,"issue_date":value(recorded),"begin_date":value(item.onset_date),"code_text":service.description,"legacy_code_id":service.legacy_code_id,"date_of_birth":value(patient.date_of_birth),"sex":patient.sex,"marital_status":payload.get("status"),"language":patient.language,"address":"^".join(str(part or "") for part in (patient.address_line_1,patient.postal_code,patient.city,patient.state)),"country_code":patient.country_code,"phone_home":patient.phone,"phone_business":payload.get("phone_biz")})
    return columns,rows,{"unreported_issues":len(rows),"patients":len({row["patient_uuid"] for row in rows}),"reportable_codes":len(reportable)}


def patient_ledger_report(db: Session,user: User,params: dict):
    """Patient ledger with encounter charges, applied A/R and standalone unapplied credits."""
    patient_id=params.get("_patient_id")
    if not patient_id:raise HTTPException(status_code=422,detail="Patient ledger requires patient_uuid")
    patient=db.get(Patient,patient_id);today=datetime.now(timezone.utc).date();date_from=params.get("date_from") or today-timedelta(days=365);date_to=params.get("date_to") or today
    start,end=bounds(date_from,date_to);scope=facility_scope(db,user);allowed_legacy=set(db.scalars(select(Facility.legacy_facility_id).where(Facility.id.in_(scope),Facility.legacy_facility_id.is_not(None)))) if scope is not None else None
    query=select(Encounter).where(Encounter.patient_id==patient_id,Encounter.occurred_at>=start,Encounter.occurred_at<end)
    if params.get("_facility_id"):query=query.where(or_(Encounter.facility_id==params["_facility_id"],Encounter.legacy_facility_id==params.get("_legacy_facility_id")))
    elif scope is not None:query=query.where(or_(Encounter.facility_id.in_(scope),Encounter.legacy_facility_id.in_(allowed_legacy)))
    encounters=list(db.scalars(query.order_by(Encounter.occurred_at,Encounter.id)));encounter_ids=[item.id for item in encounters]
    procedure_types={item.key for item in db.scalars(select(BillingCodeType).where(BillingCodeType.procedure.is_(True)))}
    charges={encounter_id:[] for encounter_id in encounter_ids}
    if encounter_ids:
        for charge in db.scalars(select(Charge).where(Charge.encounter_id.in_(encounter_ids),Charge.active.is_(True)).order_by(Charge.billed_at,Charge.id)):
            raw_provider=(charge.legacy_payload or {}).get("provider_id");provider=int(raw_provider) if str(raw_provider or "").isdigit() else 0
            if charge.code_system not in procedure_types or (params.get("provider_legacy_id") and provider!=params["provider_legacy_id"]):continue
            charges[charge.encounter_id].append(charge)
    encounters=[item for item in encounters if charges[item.id]];encounter_ids=[item.id for item in encounters]
    activities={encounter_id:[] for encounter_id in encounter_ids}
    if encounter_ids:
        for activity in db.scalars(select(ReceivableActivity).where(ReceivableActivity.encounter_id.in_(encounter_ids),ReceivableActivity.deleted_at.is_(None)).order_by(ReceivableActivity.legacy_sequence,ReceivableActivity.id)):activities[activity.encounter_id].append(activity)
    payer_rows=list(db.scalars(select(Payer)));payers={item.id:item.name for item in payer_rows};legacy_payers={item.legacy_payer_id for item in payer_rows if item.legacy_payer_id is not None};rows=[];total_units=0;total_charges=Decimal("0");total_payments=Decimal("0");total_adjustments=Decimal("0");total_balance=Decimal("0")
    columns=["line_type","patient_uuid","legacy_patient_id","patient","date_of_birth","encounter_uuid","legacy_encounter_id","encounter_date","encounter_reason","encounter_provider","code","modifier","description","billed_date","payer","payment_type","units","charge","unapplied_applied","payment","adjustment","balance_effect","encounter_balance"]
    for encounter in encounters:
        enc_balance=Decimal("0");enc_units=0;enc_charges=Decimal("0");enc_payments=Decimal("0");enc_adjustments=Decimal("0")
        common={"patient_uuid":patient.uuid,"legacy_patient_id":patient.legacy_pid,"patient":" ".join(filter(None,(patient.first_name,patient.middle_name,patient.last_name))),"date_of_birth":value(patient.date_of_birth),"encounter_uuid":encounter.uuid,"legacy_encounter_id":encounter.legacy_encounter_id,"encounter_date":value(encounter.occurred_at),"encounter_reason":encounter.chief_complaint,"encounter_provider":encounter.provider_name}
        for charge in charges[encounter.id]:
            payload=charge.legacy_payload or {};payer_id=int(payload.get("payer_id") or 0) if str(payload.get("payer_id") or "").isdigit() else 0;amount=charge.unit_price;units=charge.units or 1;enc_units+=units;enc_charges+=amount;enc_balance+=amount
            rows.append(common|{"line_type":"charge","code":charge.code,"modifier":charge.modifier,"description":charge.description,"billed_date":value(charge.billed_at.date()) if charge.billed_at else None,"payer":"Insurance" if payer_id in legacy_payers else "Self","payment_type":None,"units":units,"charge":value(amount),"unapplied_applied":None,"payment":None,"adjustment":None,"balance_effect":value(amount),"encounter_balance":value(enc_balance)})
        for activity in activities[encounter.id]:
            payment=activity.pay_amount;adjustment=activity.adjustment_amount;effect=-(payment+adjustment);enc_payments+=payment;enc_adjustments+=adjustment;enc_balance+=effect
            payer=payers.get(activity.payer_id) or ("Patient" if activity.payer_type==0 else "Unnamed insurance company")
            description=" - ".join(filter(None,(activity.payment_method_label or activity.payment_method,activity.payment_reference)))
            if activity.memo:description+=(" " if description else "")+f"[{activity.memo}]"
            rows.append(common|{"line_type":"payment","code":activity.code,"modifier":activity.modifier,"description":description or activity.follow_up_note,"billed_date":value(activity.posted_at.date()),"payer":payer,"payment_type":activity.account_code,"units":None,"charge":None,"unapplied_applied":None,"payment":value(payment) if payment else None,"adjustment":value(adjustment) if adjustment else None,"balance_effect":value(effect),"encounter_balance":value(enc_balance)})
        total_units+=enc_units;total_charges+=enc_charges;total_payments+=enc_payments;total_adjustments+=enc_adjustments;total_balance+=enc_balance
    applied_by_session={}
    for activity in db.scalars(select(ReceivableActivity).where(ReceivableActivity.patient_id==patient_id,ReceivableActivity.deleted_at.is_(None),ReceivableActivity.legacy_session_id.is_not(None))):applied_by_session[activity.legacy_session_id]=applied_by_session.get(activity.legacy_session_id,Decimal("0"))+activity.pay_amount
    session_query=select(ReceivableSession).where(ReceivableSession.patient_id==patient_id,ReceivableSession.created_at>=start,ReceivableSession.created_at<end)
    for session in db.scalars(session_query.order_by(ReceivableSession.created_at,ReceivableSession.id)):
        applied=applied_by_session.get(session.legacy_session_id,Decimal("0"));residual=session.pay_total-applied
        if applied==0 or residual==0:continue
        effect=-residual;total_payments+=residual;total_balance+=effect;payer=payers.get(session.payer_id) or "Patient"
        description=" - ".join(filter(None,(session.payment_method_label or session.payment_method,session.reference)))
        if session.description:description+=(": " if description else "")+session.description
        if session.adjustment_code:description+=(" " if description else "")+f"[{session.adjustment_code}]"
        rows.append({"line_type":"unapplied_credit","patient_uuid":patient.uuid,"legacy_patient_id":patient.legacy_pid,"patient":" ".join(filter(None,(patient.first_name,patient.middle_name,patient.last_name))),"date_of_birth":value(patient.date_of_birth),"encounter_uuid":None,"legacy_encounter_id":None,"encounter_date":None,"encounter_reason":None,"encounter_provider":None,"code":None,"modifier":None,"description":description,"billed_date":value(session.post_to_date or (session.created_at.date() if session.created_at else None)),"payer":payer,"payment_type":session.payment_type,"units":None,"charge":None,"unapplied_applied":value(applied),"payment":value(session.pay_total),"adjustment":None,"balance_effect":value(effect),"encounter_balance":None})
    return columns,rows,{"lines":len(rows),"encounters":len(encounters),"units":total_units,"charges":value(total_charges),"payments":value(total_payments),"adjustments":value(total_adjustments),"balance":value(total_balance)}


def execute_report(db: Session, user: User, key: str, params: dict) -> tuple[list[str],list[dict],dict]:
    if key not in REPORT_PATHS: raise HTTPException(status_code=404,detail="Report not found")
    if key not in IMPLEMENTED: raise HTTPException(status_code=501,detail="Legacy report is cataloged but not yet migrated")
    start,end=bounds(params.get("date_from"),params.get("date_to")); status=params.get("status");params["_quality_start"]=start;params["_quality_end"]=end
    if key == "amc_full_report": return quality_report(db,params,full_amc=True)
    if key == "cqm": return quality_report(db,params)
    if key == "clinical_reports": return clinical_report(db,user,params)
    if key == "patient_list_creation": return patient_list_creation_report(db,user,params)
    if key == "ippf_cyp_report": return ippf_cyp_report(db,user,params)
    if key == "ippf_daily": return ippf_daily_report(db,user,params)
    if key == "ippf_statistics": return ippf_statistics_report(db,user,params)
    if key == "amc_tracking": return amc_tracking_report(db,user,params)
    if key == "appt_encounter_report": return appointment_encounter_report(db,user,params)
    if key == "collections_report": return collections_report(db,user,params)
    if key == "front_receipts_report": return front_receipts_report(db,user,params)
    if key == "receipts_by_method_report": return receipts_by_method_report(db,user,params)
    if key == "payment_processing_report": return payment_processing_report(db,user,params)
    if key == "prepayment_balance_report": return prepayment_balance_report(db,user,params)
    if key == "svc_code_financial_report": return service_code_financial_report(db,user,params)
    if key == "rwt_2026_report": return real_world_testing_2026_report(db,user,params)
    if key == "custom_report_range": return superbill_report(db,user,params)
    if key == "non_reported": return non_reported_syndromic_report(db,params)
    if key == "pat_ledger": return patient_ledger_report(db,user,params)
    if key == "audit_log_tamper_report": return audit_integrity_report(db,params)
    if key == "background_services":
        columns=["name","service","active","automatic","interval_minutes","currently_busy","last_run_started_at","next_scheduled_run","handler"]
        now=datetime.now(timezone.utc);rows=[]
        for item in db.scalars(select(BackgroundService).order_by(BackgroundService.sort_order,BackgroundService.name)):
            next_run=item.next_run if item.next_run.tzinfo else item.next_run.replace(tzinfo=timezone.utc)
            lock=item.lock_expires_at
            if lock and not lock.tzinfo: lock=lock.replace(tzinfo=timezone.utc)
            automatic=item.active and item.execute_interval_minutes>0
            rows.append({"name":item.name,"service":item.title,"active":item.active,"automatic":automatic,"interval_minutes":item.execute_interval_minutes if automatic else None,"currently_busy":bool(lock and lock>now),"last_run_started_at":value(next_run-timedelta(minutes=item.execute_interval_minutes)) if item.running_state>-1 else None,"next_scheduled_run":value(next_run) if automatic else None,"handler":item.handler})
        return columns,rows,{"services":len(rows),"active":sum(row["active"] for row in rows),"automatic":sum(row["automatic"] for row in rows),"busy":sum(row["currently_busy"] for row in rows)}
    if key == "ip_tracker":
        columns=["ip_address","total_failed_logins","applicable_failed_logins","last_failed_login","auto_blocked","auto_block_ends_at","manually_blocked","skip_timing_protection"]
        now=datetime.now(timezone.utc);window=timedelta(minutes=settings.ip_failure_window_minutes);limit=settings.ip_max_failed_logins;rows=[]
        for item in db.scalars(select(IpLoginTracker).order_by(IpLoginTracker.ip_string)):
            last=item.last_failed_login
            if last and not last.tzinfo:last=last.replace(tzinfo=timezone.utc)
            applicable=item.applicable_failed_logins if last and now-last<window else 0
            auto=applicable>=limit;ends=last+window if auto else None
            row={"ip_address":item.ip_string,"total_failed_logins":item.total_failed_logins,"applicable_failed_logins":applicable,"last_failed_login":value(last),"auto_blocked":auto,"auto_block_ends_at":value(ends),"manually_blocked":item.force_block,"skip_timing_protection":item.skip_timing_protection}
            if params.get("only_with_failures") and not applicable:continue
            if params.get("only_manually_blocked") and not item.force_block:continue
            if params.get("only_auto_blocked") and not auto:continue
            rows.append(row)
        return columns,rows,{"addresses":len(rows),"failed_logins":sum(row["total_failed_logins"] for row in rows),"auto_blocked":sum(row["auto_blocked"] for row in rows),"manually_blocked":sum(row["manually_blocked"] for row in rows)}
    if key == "services_by_category":
        columns=["service_uuid","category","code_type_id","code","modifier","units","description","related_codes","prices"]
        query=select(ServiceCode).where(ServiceCode.active.is_(True))
        if params.get("code_type_id"):query=query.where(ServiceCode.code_type_id==params["code_type_id"])
        if not params.get("include_uncategorized"):query=query.where(ServiceCode.category_code.is_not(None),ServiceCode.category_code!="",ServiceCode.category_code!="0")
        items=list(db.scalars(query.order_by(ServiceCode.category_title,ServiceCode.code_type_id,ServiceCode.code,ServiceCode.modifier)))
        rows=[{"service_uuid":item.uuid,"category":item.category_title or "Uncategorized","code_type_id":item.code_type_id,"code":item.code,"modifier":item.modifier,"units":item.units,"description":item.description,"related_codes":item.related_codes,"prices":item.prices} for item in items]
        return columns,rows,{"services":len(rows),"categories":len({row["category"] for row in rows}),"price_entries":sum(len(row["prices"]) for row in rows)}
    if key == "referrals_report":
        columns=["referral_uuid","refer_to","refer_date","reply_date","patient","patient_uuid","patient_id","reason","status"]
        query=select(Referral.uuid,func.coalesce(Referral.recipient_organization,Referral.recipient_name),Referral.referred_at,Referral.replied_at,(Patient.first_name+" "+Patient.last_name),Patient.uuid,Patient.legacy_pid,Referral.reason,Referral.status).join(Patient,Patient.id==Referral.patient_id)
        scope=facility_scope(db,user)
        if scope is not None:query=query.where(Referral.facility_id.in_(scope))
        if params.get("_facility_id"):query=query.where(Referral.facility_id==params["_facility_id"])
        if start:query=query.where(Referral.referred_at>=start)
        if end:query=query.where(Referral.referred_at<end)
        if status:query=query.where(Referral.status==status)
        rows=rows_from(db.execute(query.order_by(Referral.recipient_organization,Referral.recipient_name,Referral.referred_at,Referral.id)).all(),columns)
        return columns,rows,{"referrals":len(rows),"completed":sum(row["status"]=="completed" for row in rows),"pending":sum(row["status"]!="completed" for row in rows)}
    if key == "external_data":
        patient_id=params.get("_patient_id")
        if not patient_id: raise HTTPException(status_code=422,detail="patient_uuid is required")
        columns=["record_uuid","record_type","date","code","description","provider","facility","external_id"]
        encounter_query=select(ExternalEncounter).where(ExternalEncounter.patient_id==patient_id)
        procedure_query=select(ExternalProcedure).where(ExternalProcedure.patient_id==patient_id)
        if start:
            encounter_query=encounter_query.where(ExternalEncounter.occurred_on>=start.date());procedure_query=procedure_query.where(ExternalProcedure.occurred_on>=start.date())
        if end:
            encounter_query=encounter_query.where(ExternalEncounter.occurred_on<end.date());procedure_query=procedure_query.where(ExternalProcedure.occurred_on<end.date())
        encounters=list(db.scalars(encounter_query));procedures=list(db.scalars(procedure_query))
        rows=[{"record_uuid":item.uuid,"record_type":"encounter","date":item.occurred_on.isoformat(),"code":None,"description":item.diagnosis,"provider":item.provider_name,"facility":item.facility_name,"external_id":item.external_id} for item in encounters]
        rows += [{"record_uuid":item.uuid,"record_type":"procedure","date":item.occurred_on.isoformat(),"code":f"{item.code_system}:{item.code}" if item.code_system and item.code else item.code,"description":item.code_text,"provider":None,"facility":item.facility_name,"external_id":item.external_id} for item in procedures]
        rows.sort(key=lambda row:(row["date"],row["record_type"],row["record_uuid"]),reverse=True)
        return columns,rows,{"records":len(rows),"encounters":len(encounters),"procedures":len(procedures)}
    if key == "patient_edu_web_lookup":
        columns=["resource_uuid","name","url_template","sequence","active","legacy_option_id"]
        items=list(db.scalars(select(PatientEducationResource).order_by(PatientEducationResource.sequence,PatientEducationResource.name)))
        rows=[{"resource_uuid":item.uuid,"name":item.name,"url_template":item.url_template,"sequence":item.sequence,"active":item.active,"legacy_option_id":item.legacy_option_id} for item in items]
        return columns,rows,{"resources":len(rows),"active":sum(row["active"] for row in rows),"inactive":sum(not row["active"] for row in rows)}
    if key == "report_results":
        columns=["run_uuid","title","created_at","status","row_count","checksum","actor"]
        query=select(ReportRun,User).join(User,User.id==ReportRun.actor_id).where(ReportRun.report_key!="report_results")
        if start:query=query.where(ReportRun.created_at>=start)
        if end:query=query.where(ReportRun.created_at<end)
        records=db.execute(query.order_by(ReportRun.created_at.desc(),ReportRun.id.desc())).all()
        rows=[{"run_uuid":item.uuid,"title":item.report_key.replace("_"," ").replace("."," ").title(),"created_at":value(item.created_at),"status":"complete","row_count":item.row_count,"checksum":item.checksum,"actor":actor.email} for item,actor in records]
        return columns,rows,{"runs":len(rows),"rows_materialized":sum(row["row_count"] for row in rows),"integrity_hashes":sum(bool(row["checksum"]) for row in rows)}
    if key == "cdr_log":
        columns=["log_uuid","date","patient_pid","patient_uuid","user_id","actor","facility_id","facility","category","category_title","value","new_value"]
        query=(select(ClinicalRuleLog,Patient,User,Facility)
               .outerjoin(Patient,Patient.id==ClinicalRuleLog.patient_id)
               .outerjoin(User,User.id==ClinicalRuleLog.actor_id)
               .outerjoin(Facility,Facility.id==ClinicalRuleLog.facility_id))
        scope=facility_scope(db,user)
        if scope is not None:
            legacy_ids=list(db.scalars(select(Facility.legacy_facility_id).where(Facility.id.in_(scope),Facility.legacy_facility_id.is_not(None))))
            query=query.where(or_(ClinicalRuleLog.facility_id.in_(scope),ClinicalRuleLog.legacy_facility_id.in_(legacy_ids)))
        if params.get("_facility_id"):
            query=query.where(or_(ClinicalRuleLog.facility_id==params["_facility_id"],ClinicalRuleLog.legacy_facility_id==params.get("_legacy_facility_id")))
        if start:query=query.where(ClinicalRuleLog.occurred_at>=start)
        if end:query=query.where(ClinicalRuleLog.occurred_at<end)
        titles={"clinical_reminder_widget":"Passive Alert","active_reminder_popup":"Active Alert","allergy_alert":"Allergy Warning"}
        rows=[]
        for item,patient,actor,facility in db.execute(query.order_by(ClinicalRuleLog.occurred_at.desc(),ClinicalRuleLog.id.desc())):
            rows.append({"log_uuid":item.uuid,"date":value(item.occurred_at),"patient_pid":item.legacy_patient_id,"patient_uuid":patient.uuid if patient else None,"user_id":item.legacy_user_id,"actor":actor.email if actor else None,"facility_id":item.legacy_facility_id,"facility":facility.name if facility else None,"category":item.category,"category_title":titles.get(item.category,item.category),"value":item.value,"new_value":item.new_value})
        return columns,rows,{"logs":len(rows),"passive_alerts":sum(row["category"]=="clinical_reminder_widget" for row in rows),"active_alerts":sum(row["category"]=="active_reminder_popup" for row in rows),"allergy_warnings":sum(row["category"]=="allergy_alert" for row in rows),"changed_evaluations":sum(row["new_value"] is not None for row in rows)}
    if key == "insurance_allocation_report":return insurance_allocation(db,user,params)
    if key == "inventory_activity": return inventory_activity(db,user,params)
    if key == "chart_location_activity":
        patient_id=params.get("_patient_id")
        if not patient_id: raise HTTPException(status_code=422,detail="patient_uuid is required")
        columns=["event_uuid","occurred_at","patient","patient_uuid","destination_type","destination","custodian_uuid","note"]
        query=(select(ChartLocationEvent.uuid,ChartLocationEvent.occurred_at,(Patient.last_name+", "+Patient.first_name),Patient.uuid,ChartLocationEvent.destination_type,
                      func.coalesce(ChartLocationEvent.location,ChartLocationEvent.custodian_name,literal("Returned to records")),User.uuid,ChartLocationEvent.note)
               .join(Patient,Patient.id==ChartLocationEvent.patient_id).outerjoin(User,User.id==ChartLocationEvent.custodian_user_id)
               .where(ChartLocationEvent.patient_id==patient_id))
        if start: query=query.where(ChartLocationEvent.occurred_at>=start)
        if end: query=query.where(ChartLocationEvent.occurred_at<end)
        rows=rows_from(db.execute(query.order_by(ChartLocationEvent.occurred_at,ChartLocationEvent.id)).all(),columns)
        return columns,rows,{"events":len(rows),"checkouts":sum(row["destination_type"]=="user" for row in rows),"locations":sum(row["destination_type"]=="location" for row in rows),"returns":sum(row["destination_type"]=="returned" for row in rows)}
    if key == "charts_checked_out":
        ranked=(select(ChartLocationEvent.id.label("event_id"),func.row_number().over(partition_by=ChartLocationEvent.patient_id,order_by=(ChartLocationEvent.occurred_at.desc(),ChartLocationEvent.id.desc())).label("position")).subquery())
        columns=["event_uuid","checked_out_at","patient","patient_uuid","custodian","custodian_uuid","note"]
        query=(select(ChartLocationEvent.uuid,ChartLocationEvent.occurred_at,(Patient.last_name+", "+Patient.first_name),Patient.uuid,ChartLocationEvent.custodian_name,User.uuid,ChartLocationEvent.note)
               .join(ranked,ranked.c.event_id==ChartLocationEvent.id).join(Patient,Patient.id==ChartLocationEvent.patient_id)
               .outerjoin(User,User.id==ChartLocationEvent.custodian_user_id)
               .where(ranked.c.position==1,ChartLocationEvent.destination_type=="user"))
        if start: query=query.where(ChartLocationEvent.occurred_at>=start)
        if end: query=query.where(ChartLocationEvent.occurred_at<end)
        rows=rows_from(db.execute(query.order_by(Patient.last_name,Patient.first_name)).all(),columns)
        return columns,rows,{"checked_out":len(rows)}
    if key == "patient_list":
        columns=["patient_uuid","last_name","first_name","date_of_birth","sex","email"]
        result=db.execute(select(Patient.uuid,Patient.last_name,Patient.first_name,Patient.date_of_birth,Patient.sex,Patient.email).order_by(Patient.last_name,Patient.first_name)).all()
        rows=rows_from(result,columns); return columns,rows,{"patients":len(rows)}
    if key == "appointments_report":
        columns=["appointment_uuid","starts_at","patient","status","provider","facility","room"]
        query=select(Appointment.uuid,Appointment.starts_at,(Patient.last_name+", "+Patient.first_name),Appointment.status,Appointment.provider_name,Appointment.facility_name,Appointment.room).join(Patient)
        query=appointment_scope(query,db,user)
        query=selected_facility(query,params)
        if start: query=query.where(Appointment.starts_at>=start)
        if end: query=query.where(Appointment.starts_at<end)
        if status: query=query.where(Appointment.status==status)
        rows=rows_from(db.execute(query.order_by(Appointment.starts_at)).all(),columns); return columns,rows,{"appointments":len(rows)}
    if key == "encounters_report" or key == "unique_seen_patients_report":
        query=select(Encounter.uuid,Encounter.occurred_at,(Patient.last_name+", "+Patient.first_name),Encounter.type,Encounter.status,Encounter.chief_complaint).join(Patient).outerjoin(Appointment,Encounter.appointment_id==Appointment.id)
        query=appointment_scope(query,db,user)
        query=selected_facility(query,params)
        if start: query=query.where(Encounter.occurred_at>=start)
        if end: query=query.where(Encounter.occurred_at<end)
        result=db.execute(query.order_by(Encounter.occurred_at)).all()
        if key == "unique_seen_patients_report":
            patient_names=sorted({row[2] for row in result}); columns=["patient"]; rows=[{"patient":name} for name in patient_names]; return columns,rows,{"unique_patients":len(rows)}
        columns=["encounter_uuid","occurred_at","patient","type","status","chief_complaint"]; rows=rows_from(result,columns); return columns,rows,{"encounters":len(rows)}
    if key == "prescriptions_report":
        columns=["prescription_uuid","prescribed_at","modified_at","patient","drug","rxnorm","dosage","instructions","route","quantity","refills","per_refill","filled_date","pharmacy","indication","diagnosis","prn","request_intent","erx_source","erx_uploaded","status"]
        query=select(Prescription.uuid,Prescription.prescribed_at,Prescription.modified_at,(Patient.last_name+", "+Patient.first_name),Prescription.drug_name,Prescription.rxnorm_code,Prescription.dosage,Prescription.dosage_instructions,Prescription.route,Prescription.quantity,Prescription.refills,Prescription.per_refill,Prescription.filled_date,Pharmacy.name,Prescription.indication,Prescription.diagnosis,Prescription.prn,Prescription.request_intent,Prescription.erx_source,Prescription.erx_uploaded,Prescription.status).join(Patient).outerjoin(Pharmacy,Prescription.pharmacy_id==Pharmacy.id)
        if start: query=query.where(Prescription.prescribed_at>=start)
        if end: query=query.where(Prescription.prescribed_at<end)
        if status: query=query.where(Prescription.status==status)
        rows=rows_from(db.execute(query.order_by(Prescription.prescribed_at)).all(),columns); return columns,rows,{"prescriptions":len(rows)}
    if key == "immunization_report":
        columns=["immunization_uuid","administered_at","patient","patient_uuid","date_of_birth","cvx_code","vaccine","manufacturer","lot_number","route","site","dose","status","refusal_reason"]
        query=select(Immunization.uuid,Immunization.administered_at,(Patient.last_name+", "+Patient.first_name),Patient.uuid,Patient.date_of_birth,Immunization.cvx_code,Immunization.vaccine_name,Immunization.manufacturer,Immunization.lot_number,Immunization.route,Immunization.site,Immunization.dose,Immunization.status,Immunization.refusal_reason).join(Patient,Patient.id==Immunization.patient_id).where(Immunization.status!="entered-in-error")
        if start: query=query.where(Immunization.administered_at>=start)
        if end: query=query.where(Immunization.administered_at<end)
        if status: query=query.where(Immunization.status==status)
        rows=rows_from(db.execute(query.order_by(Immunization.administered_at,Patient.last_name,Patient.first_name)).all(),columns)
        return columns,rows,{"immunizations":len(rows),"patients":len({row["patient_uuid"] for row in rows}),"refused":sum(row["status"]=="not-done" for row in rows)}
    if key == "message_list":
        columns=["message_uuid","thread_uuid","created_at","user","patient","patient_uuid","date_of_birth","type","status","last_update"]
        query=(select(SecureMessage.uuid,MessageThread.uuid,SecureMessage.created_at,func.coalesce(User.username,SecureMessage.sender_name,SecureMessage.sender_kind),(Patient.last_name+", "+Patient.first_name),Patient.uuid,Patient.date_of_birth,MessageThread.subject,MessageThread.status,MessageThread.updated_at)
               .join(MessageThread,MessageThread.id==SecureMessage.thread_id)
               .join(Patient,Patient.id==MessageThread.patient_id)
               .outerjoin(User,User.id==SecureMessage.sender_user_id))
        if start: query=query.where(SecureMessage.created_at>=start)
        if end: query=query.where(SecureMessage.created_at<end)
        if status: query=query.where(MessageThread.status==status)
        rows=rows_from(db.execute(query.order_by(Patient.last_name,Patient.first_name,SecureMessage.created_at)).all(),columns)
        return columns,rows,{"messages":len(rows),"threads":len({row["thread_uuid"] for row in rows})}
    if key == "direct_message_log":
        columns=["delivery_uuid","direction","channel","date_created","sender","recipient","status","status_changed","attempts","error"]
        changed=func.coalesce(CommunicationDelivery.sent_at,CommunicationDelivery.failed_at,CommunicationDelivery.queued_at)
        query=select(CommunicationDelivery.uuid,literal("sent"),CommunicationDelivery.channel,CommunicationDelivery.queued_at,literal("OpenRM"),CommunicationDelivery.recipient,CommunicationDelivery.status,changed,CommunicationDelivery.attempts,CommunicationDelivery.error_message)
        if start: query=query.where(CommunicationDelivery.queued_at>=start)
        if end: query=query.where(CommunicationDelivery.queued_at<end)
        if status: query=query.where(CommunicationDelivery.status==status)
        rows=rows_from(db.execute(query.order_by(CommunicationDelivery.queued_at.desc(),CommunicationDelivery.id.desc())).all(),columns)
        return columns,rows,{"deliveries":len(rows),"failed":sum(row["status"]=="failed" for row in rows)}
    if key in {"inventory_list","destroyed_drugs_report"}:
        columns=["product","ndc","lot","warehouse","expiration","on_hand","destroyed_at"]
        query=select(InventoryProduct.name,InventoryProduct.ndc_number,InventoryLot.lot_number,InventoryLot.warehouse_id,InventoryLot.expiration,InventoryLot.on_hand,InventoryLot.destroyed_at).join(InventoryLot)
        scope=warehouse_scope(db,user)
        if scope is not None: query=query.where(InventoryLot.warehouse_id.in_(scope))
        if params.get("warehouse_code"): query=query.where(InventoryLot.warehouse_id==params["warehouse_code"])
        if key == "destroyed_drugs_report":
            query=query.where(InventoryLot.destroyed_at.is_not(None))
            if params.get("date_from"): query=query.where(InventoryLot.destroyed_at>=params["date_from"])
            if params.get("date_to"): query=query.where(InventoryLot.destroyed_at<=params["date_to"])
        rows=rows_from(db.execute(query.order_by(InventoryProduct.name,InventoryLot.expiration)).all(),columns); return columns,rows,{"lots":len(rows),"on_hand":sum(row["on_hand"] for row in rows)}
    if key in {"inventory_transactions","sales_by_item"}:
        query=select(InventoryProduct.name,InventoryLot.lot_number,InventoryLot.warehouse_id,InventoryTransaction.transaction_type,InventoryTransaction.occurred_on,InventoryTransaction.quantity,InventoryTransaction.fee,InventoryTransaction.actor_name).join(InventoryProduct,InventoryTransaction.product_id==InventoryProduct.id).outerjoin(InventoryLot,InventoryTransaction.lot_id==InventoryLot.id)
        scope=warehouse_scope(db,user)
        if scope is not None: query=query.where(InventoryLot.warehouse_id.in_(scope))
        if params.get("warehouse_code"): query=query.where(InventoryLot.warehouse_id==params["warehouse_code"])
        if params.get("date_from"): query=query.where(InventoryTransaction.occurred_on>=params["date_from"])
        if params.get("date_to"): query=query.where(InventoryTransaction.occurred_on<=params["date_to"])
        if key == "sales_by_item": query=query.where(InventoryTransaction.transaction_type=="dispense")
        columns=["product","lot","warehouse","type","occurred_on","quantity","fee","actor"]; rows=rows_from(db.execute(query.order_by(InventoryTransaction.occurred_on)).all(),columns)
        if key == "sales_by_item":
            grouped={}
            for row in rows:
                item=grouped.setdefault(row["product"],{"product":row["product"],"quantity":0,"fees":Decimal("0")}); item["quantity"]+=row["quantity"]; item["fees"]+=Decimal(row["fee"])
            columns=["product","quantity","fees"]; rows=[{"product":item["product"],"quantity":item["quantity"],"fees":str(item["fees"])} for item in grouped.values()]
        return columns,rows,{"rows":len(rows),"quantity":sum(row["quantity"] for row in rows),"fees":str(sum((Decimal(row.get("fee",row.get("fees","0"))) for row in rows),Decimal("0")))}
    if key == "patient_flow_board_report":
        latest=select(PatientFlowEvent.episode_id,func.max(PatientFlowEvent.sequence).label("seq")).group_by(PatientFlowEvent.episode_id).subquery()
        query=select(PatientFlowEpisode.uuid,PatientFlowEpisode.started_at,(Patient.last_name+", "+Patient.first_name),PatientFlowEvent.status,PatientFlowEvent.room,PatientFlowEvent.started_at).join(Patient).join(PatientFlowEvent,(PatientFlowEvent.episode_id==PatientFlowEpisode.id)).join(latest,(latest.c.episode_id==PatientFlowEvent.episode_id)&(latest.c.seq==PatientFlowEvent.sequence)).outerjoin(Appointment,PatientFlowEpisode.appointment_id==Appointment.id)
        query=appointment_scope(query,db,user)
        query=selected_facility(query,params)
        columns=["episode_uuid","started_at","patient","status","room","current_since"]; rows=rows_from(db.execute(query.order_by(PatientFlowEpisode.started_at)).all(),columns); return columns,rows,{"episodes":len(rows)}
    if key == "daily_summary_report":
        appointment_columns,appointments,_=execute_report(db,user,"appointments_report",params); del appointment_columns
        encounter_columns,encounters,_=execute_report(db,user,"encounters_report",params); del encounter_columns
        days={}
        for row in appointments: days.setdefault(row["starts_at"][:10],{"date":row["starts_at"][:10],"appointments":0,"encounters":0})["appointments"]+=1
        for row in encounters: days.setdefault(row["occurred_at"][:10],{"date":row["occurred_at"][:10],"appointments":0,"encounters":0})["encounters"]+=1
        columns=["date","appointments","encounters"]; rows=[days[key] for key in sorted(days)]; return columns,rows,{"days":len(rows),"appointments":sum(row["appointments"] for row in rows),"encounters":sum(row["encounters"] for row in rows)}
    raise HTTPException(status_code=501,detail="Report implementation pending")
