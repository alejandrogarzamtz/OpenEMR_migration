from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from itertools import product

from fastapi import HTTPException
from sqlalchemy import func, literal, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Appointment, AuditEvent, AuditEventSeal, BackgroundService, BillingCodeType, ChartLocationEvent, Charge, ClinicalForm, ClinicalItem, ClinicalRuleLog, CommunicationDelivery, Coverage, Encounter, ExternalEncounter, ExternalProcedure, Facility, IdentityAuditEvent, Immunization, InventoryLot, InventoryProduct, InventoryTransaction, IpLoginTracker, LabOrder, LabResult, MessageThread, Patient, PatientEducationResource, PatientFlowEpisode, PatientFlowEvent, PatientProviderAssignment, Payer, Pharmacy, Practitioner, Prescription, ProcedureOrderLine, ReceivableActivity, Referral, ReportRun, SecureMessage, ServiceCode, SocialHistory, User, audit_event_checksum
from .access import facility_scope, warehouse_scope

REPORT_PATHS = [
    "amc_full_report", "amc_tracking", "appointments_report", "appt_encounter_report", "audit_log_tamper_report", "background_services", "cdr_log", "chart_location_activity", "charts_checked_out", "clinical_reports", "collections_report", "cqm", "criteria.tab", "custom_report_range", "daily_summary_report", "destroyed_drugs_report", "direct_message_log", "encounters_report", "external_data", "front_receipts_report", "immunization_report", "insurance_allocation_report", "inventory_activity", "inventory_list", "inventory_transactions", "ip_tracker", "ippf_cyp_report", "ippf_daily", "ippf_statistics", "message_list", "non_reported", "pat_ledger", "patient_edu_web_lookup", "patient_flow_board_report", "patient_list", "patient_list_creation", "payment_processing_report", "prepayment_balance_report", "prescriptions_report", "receipts_by_method_report", "referrals_report", "report.script", "report_results", "rwt_2026_report", "sales_by_item", "services_by_category", "svc_code_financial_report", "unique_seen_patients_report",
]
IMPLEMENTED = {"appointments_report", "appt_encounter_report", "audit_log_tamper_report", "background_services", "cdr_log", "chart_location_activity", "charts_checked_out", "clinical_reports", "collections_report", "daily_summary_report", "destroyed_drugs_report", "direct_message_log", "encounters_report", "external_data", "immunization_report", "insurance_allocation_report", "inventory_activity", "inventory_list", "inventory_transactions", "ip_tracker", "message_list", "patient_edu_web_lookup", "patient_flow_board_report", "patient_list", "prescriptions_report", "referrals_report", "report_results", "sales_by_item", "services_by_category", "unique_seen_patients_report"}
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
    "sales_by_item":"acct:rep:read", "svc_code_financial_report":"acct:rep_a:read",
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
    return [{"key":key,"title":key.replace("_"," ").replace("."," ").title(),"category":category_for(key),"permission":permission_for(key),"legacy_path":f"interface/reports/{key}.php","migrated":key in IMPLEMENTED} for key in REPORT_PATHS]


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


def execute_report(db: Session, user: User, key: str, params: dict) -> tuple[list[str],list[dict],dict]:
    if key not in REPORT_PATHS: raise HTTPException(status_code=404,detail="Report not found")
    if key not in IMPLEMENTED: raise HTTPException(status_code=501,detail="Legacy report is cataloged but not yet migrated")
    start,end=bounds(params.get("date_from"),params.get("date_to")); status=params.get("status")
    if key == "clinical_reports": return clinical_report(db,user,params)
    if key == "appt_encounter_report": return appointment_encounter_report(db,user,params)
    if key == "collections_report": return collections_report(db,user,params)
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
