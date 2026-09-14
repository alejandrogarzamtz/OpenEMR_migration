from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, literal, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Appointment, AuditEvent, AuditEventSeal, BackgroundService, ChartLocationEvent, Charge, CommunicationDelivery, Encounter, Facility, IdentityAuditEvent, Immunization, InventoryLot, InventoryProduct, InventoryTransaction, IpLoginTracker, MessageThread, Patient, PatientFlowEpisode, PatientFlowEvent, Prescription, SecureMessage, ServiceCode, User, audit_event_checksum
from .access import facility_scope, warehouse_scope

REPORT_PATHS = [
    "amc_full_report", "amc_tracking", "appointments_report", "appt_encounter_report", "audit_log_tamper_report", "background_services", "cdr_log", "chart_location_activity", "charts_checked_out", "clinical_reports", "collections_report", "cqm", "criteria.tab", "custom_report_range", "daily_summary_report", "destroyed_drugs_report", "direct_message_log", "encounters_report", "external_data", "front_receipts_report", "immunization_report", "insurance_allocation_report", "inventory_activity", "inventory_list", "inventory_transactions", "ip_tracker", "ippf_cyp_report", "ippf_daily", "ippf_statistics", "message_list", "non_reported", "pat_ledger", "patient_edu_web_lookup", "patient_flow_board_report", "patient_list", "patient_list_creation", "payment_processing_report", "prepayment_balance_report", "prescriptions_report", "receipts_by_method_report", "referrals_report", "report.script", "report_results", "rwt_2026_report", "sales_by_item", "services_by_category", "svc_code_financial_report", "unique_seen_patients_report",
]
IMPLEMENTED = {"appointments_report", "audit_log_tamper_report", "background_services", "chart_location_activity", "charts_checked_out", "daily_summary_report", "destroyed_drugs_report", "direct_message_log", "encounters_report", "immunization_report", "inventory_activity", "inventory_list", "inventory_transactions", "ip_tracker", "message_list", "patient_flow_board_report", "patient_list", "prescriptions_report", "sales_by_item", "services_by_category", "unique_seen_patients_report"}
PERMISSION_OVERRIDES = {
    "appointments_report":"patients:appt:read", "appt_encounter_report":"acct:rep_a:read",
    "audit_log_tamper_report":"admin:super:read", "background_services":"admin:super:read",
    "collections_report":"acct:rep_a:read", "custom_report_range":"encounters:coding_a:read",
    "chart_location_activity":"patients:demo:read", "charts_checked_out":"patients:demo:read",
    "daily_summary_report":"acct:rep_a:read", "direct_message_log":"admin:super:read",
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
        columns=["prescription_uuid","prescribed_at","patient","drug","rxnorm","quantity","refills","status"]
        query=select(Prescription.uuid,Prescription.prescribed_at,(Patient.last_name+", "+Patient.first_name),Prescription.drug_name,Prescription.rxnorm_code,Prescription.quantity,Prescription.refills,Prescription.status).join(Patient)
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
