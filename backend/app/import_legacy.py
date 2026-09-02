"""Idempotent OpenEMR MySQL importer with dry-run reconciliation.

Usage:
  python -m app.import_legacy --source mysql+pymysql://user:pass@host/openemr
  python -m app.import_legacy --source ... --commit
"""
import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import Session
from .db import Base, engine as target_engine
from .models import Charge, Claim, ClinicalForm, ClinicalItem, Coverage, Document, Encounter, Immunization, LabOrder, LabResult, Patient, Payer, Pharmacy, Prescription, VitalSet

TYPE_MAP = {"medical_problem": "problem", "allergy": "allergy", "medication": "medication"}


def clean(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def valid_dob(value):
    return value if isinstance(value, date) and value.year > 1800 else date(1900, 1, 1)


def json_value(value):
    if isinstance(value, (date, datetime)): return value.isoformat()
    if hasattr(value, "as_tuple"): return str(value)
    if isinstance(value, bytes): return value.hex()
    return value


def run(source_url: str, commit: bool = False) -> dict:
    source = create_engine(source_url)
    Base.metadata.create_all(target_engine)
    names = ("patients", "clinical_items", "encounters", "lab_orders", "lab_results", "documents", "payers", "coverages", "charges", "claims", "immunizations", "vitals", "pharmacies", "prescriptions", "clinical_forms")
    stats = {name: {"source": 0, "inserted": 0, "existing": 0, "rejected": 0} for name in names}
    with source.connect() as legacy, Session(target_engine) as target:
        patients = legacy.execute(text("SELECT pid,fname,lname,DOB,sex,email,phone_cell,phone_home FROM patient_data ORDER BY pid"))
        for row in patients.mappings():
            stats["patients"]["source"] += 1
            patient = target.scalar(select(Patient).where(Patient.legacy_pid == row["pid"]))
            if patient: stats["patients"]["existing"] += 1; continue
            target.add(Patient(legacy_pid=row["pid"], first_name=clean(row["fname"]) or "Unknown", last_name=clean(row["lname"]) or "Unknown", date_of_birth=valid_dob(row["DOB"]), sex=clean(row["sex"]) or "unknown", email=clean(row["email"]), phone=clean(row["phone_cell"]) or clean(row["phone_home"])))
            stats["patients"]["inserted"] += 1
        target.flush()
        items = legacy.execute(text("SELECT id,pid,type,title,begdate,enddate,diagnosis,activity,comments,reaction,severity_al FROM lists WHERE type IN ('medical_problem','allergy','medication') ORDER BY id"))
        for row in items.mappings():
            stats["clinical_items"]["source"] += 1
            if target.scalar(select(ClinicalItem.id).where(ClinicalItem.legacy_list_id == row["id"])): stats["clinical_items"]["existing"] += 1; continue
            patient = target.scalar(select(Patient).where(Patient.legacy_pid == row["pid"])); title = clean(row["title"])
            if not patient or not title: continue
            diagnosis = clean(row["diagnosis"]); system, code = (diagnosis.split(":", 1) if diagnosis and ":" in diagnosis else (None, diagnosis))
            target.add(ClinicalItem(legacy_list_id=row["id"], patient_id=patient.id, category=TYPE_MAP[row["type"]], title=title, code_system=system, code=code, status="active" if row["activity"] else "inactive", onset_date=row["begdate"].date() if row["begdate"] else None, end_date=row["enddate"].date() if row["enddate"] else None, note=clean(row["comments"]), reaction=clean(row["reaction"]), severity=clean(row["severity_al"])))
            stats["clinical_items"]["inserted"] += 1
        encounters = legacy.execute(text("SELECT id,pid,encounter,date,reason,class_code FROM form_encounter ORDER BY id"))
        for row in encounters.mappings():
            stats["encounters"]["source"] += 1
            if target.scalar(select(Encounter.id).where(Encounter.legacy_encounter_id == row["encounter"])): stats["encounters"]["existing"] += 1; continue
            patient = target.scalar(select(Patient).where(Patient.legacy_pid == row["pid"]))
            if not patient or not row["date"]: continue
            target.add(Encounter(legacy_encounter_id=row["encounter"], patient_id=patient.id, occurred_at=row["date"], type=clean(row["class_code"]) or "AMB", chief_complaint=clean(row["reason"])))
            stats["encounters"]["inserted"] += 1
        target.flush()
        orders = legacy.execute(text("""SELECT po.procedure_order_id,po.patient_id,po.encounter_id,po.date_ordered,po.order_priority,po.order_status,po.patient_instructions,poc.procedure_code,poc.procedure_name FROM procedure_order po LEFT JOIN procedure_order_code poc ON poc.procedure_order_id=po.procedure_order_id AND poc.procedure_order_seq=(SELECT MIN(x.procedure_order_seq) FROM procedure_order_code x WHERE x.procedure_order_id=po.procedure_order_id) WHERE po.activity=1 ORDER BY po.procedure_order_id"""))
        for row in orders.mappings():
            stats["lab_orders"]["source"] += 1
            if target.scalar(select(LabOrder.id).where(LabOrder.legacy_order_id == row["procedure_order_id"])): stats["lab_orders"]["existing"] += 1; continue
            patient = target.scalar(select(Patient).where(Patient.legacy_pid == row["patient_id"]))
            encounter = target.scalar(select(Encounter).where(Encounter.legacy_encounter_id == row["encounter_id"])) if row["encounter_id"] else None
            if not patient or not row["date_ordered"] or not clean(row["procedure_name"]): stats["lab_orders"]["rejected"] += 1; continue
            target.add(LabOrder(legacy_order_id=row["procedure_order_id"], patient_id=patient.id, encounter_id=encounter.id if encounter else None, ordered_at=row["date_ordered"], code=clean(row["procedure_code"]) or "unknown", name=clean(row["procedure_name"]), priority=clean(row["order_priority"]) or "routine", status=clean(row["order_status"]) or "pending", instructions=clean(row["patient_instructions"])))
            stats["lab_orders"]["inserted"] += 1
        target.flush()
        results = legacy.execute(text("""SELECT pr.procedure_result_id,rep.procedure_order_id,pr.date,pr.result_code,pr.result_text,pr.result,pr.units,pr.range,pr.abnormal,pr.result_status FROM procedure_result pr JOIN procedure_report rep ON rep.procedure_report_id=pr.procedure_report_id ORDER BY pr.procedure_result_id"""))
        for row in results.mappings():
            stats["lab_results"]["source"] += 1
            if target.scalar(select(LabResult.id).where(LabResult.legacy_result_id == row["procedure_result_id"])): stats["lab_results"]["existing"] += 1; continue
            order = target.scalar(select(LabOrder).where(LabOrder.legacy_order_id == row["procedure_order_id"]))
            if not order or not row["date"] or not clean(row["result"]): stats["lab_results"]["rejected"] += 1; continue
            target.add(LabResult(legacy_result_id=row["procedure_result_id"], order_id=order.id, observed_at=row["date"], code=clean(row["result_code"]) or "unknown", name=clean(row["result_text"]) or clean(row["result_code"]) or "Result", value=clean(row["result"]), unit=clean(row["units"]), reference_range=clean(row["range"]), interpretation=clean(row["abnormal"]), status=clean(row["result_status"]) or "final"))
            stats["lab_results"]["inserted"] += 1
        documents = legacy.execute(text("SELECT id,foreign_id,name,mimetype,document_data,date FROM documents WHERE deleted=0 ORDER BY id"))
        for row in documents.mappings():
            stats["documents"]["source"] += 1
            if target.scalar(select(Document.id).where(Document.legacy_document_id == row["id"])): stats["documents"]["existing"] += 1; continue
            patient = target.scalar(select(Patient).where(Patient.legacy_pid == row["foreign_id"])); content = row["document_data"]
            if not patient or not content: stats["documents"]["rejected"] += 1; continue
            payload = content.encode() if isinstance(content, str) else bytes(content)
            target.add(Document(legacy_document_id=row["id"], patient_id=patient.id, name=clean(row["name"]) or f"document-{row['id']}", mime_type=clean(row["mimetype"]) or "application/octet-stream", content=payload, sha256=hashlib.sha256(payload).hexdigest(), uploaded_at=row["date"] or datetime.now(timezone.utc)))
            stats["documents"]["inserted"] += 1
        payers = legacy.execute(text("SELECT id,name,cms_id,x12_receiver_id,inactive FROM insurance_companies ORDER BY id"))
        for row in payers.mappings():
            stats["payers"]["source"] += 1
            if target.scalar(select(Payer.id).where(Payer.legacy_payer_id == row["id"])): stats["payers"]["existing"] += 1; continue
            if not clean(row["name"]): stats["payers"]["rejected"] += 1; continue
            target.add(Payer(legacy_payer_id=row["id"], name=clean(row["name"]), payer_identifier=clean(row["x12_receiver_id"]) or clean(row["cms_id"]), active=not bool(row["inactive"])))
            stats["payers"]["inserted"] += 1
        target.flush()
        coverages = legacy.execute(text("SELECT id,pid,type,provider,plan_name,policy_number,group_number,subscriber_fname,subscriber_lname,subscriber_relationship,date,date_end FROM insurance_data ORDER BY id"))
        for row in coverages.mappings():
            stats["coverages"]["source"] += 1
            if target.scalar(select(Coverage.id).where(Coverage.legacy_insurance_id == row["id"])): stats["coverages"]["existing"] += 1; continue
            patient=target.scalar(select(Patient).where(Patient.legacy_pid==row["pid"])); payer=target.scalar(select(Payer).where(Payer.legacy_payer_id==int(row["provider"]))) if str(row["provider"] or "").isdigit() else None
            subscriber=" ".join(filter(None,(clean(row["subscriber_fname"]),clean(row["subscriber_lname"]))))
            if not patient or not payer or not clean(row["policy_number"]) or not subscriber: stats["coverages"]["rejected"] += 1; continue
            target.add(Coverage(legacy_insurance_id=row["id"],patient_id=patient.id,payer_id=payer.id,priority=clean(row["type"]) or "primary",plan_name=clean(row["plan_name"]),policy_number=clean(row["policy_number"]),group_number=clean(row["group_number"]),subscriber_name=subscriber,relationship=clean(row["subscriber_relationship"]) or "self",starts_on=row["date"],ends_on=row["date_end"]))
            stats["coverages"]["inserted"] += 1
        target.flush()
        charges=legacy.execute(text("SELECT id,pid,encounter,code_type,code,code_text,units,fee,activity FROM billing ORDER BY id"))
        for row in charges.mappings():
            stats["charges"]["source"] += 1
            if target.scalar(select(Charge.id).where(Charge.legacy_billing_id==row["id"])): stats["charges"]["existing"] += 1; continue
            patient=target.scalar(select(Patient).where(Patient.legacy_pid==row["pid"])); encounter=target.scalar(select(Encounter).where(Encounter.legacy_encounter_id==row["encounter"]))
            if not patient or not encounter or not row["activity"] or not clean(row["code"]) or not row["fee"]: stats["charges"]["rejected"] += 1; continue
            target.add(Charge(legacy_billing_id=row["id"],patient_id=patient.id,encounter_id=encounter.id,code_system=clean(row["code_type"]) or "CPT",code=clean(row["code"]),description=clean(row["code_text"]) or clean(row["code"]),units=row["units"] or 1,unit_price=row["fee"]))
            stats["charges"]["inserted"] += 1
        target.flush()
        claims=legacy.execute(text("SELECT patient_id,encounter_id,version,payer_id,status,bill_time FROM claims ORDER BY patient_id,encounter_id,version"))
        for row in claims.mappings():
            stats["claims"]["source"] += 1; key=f"{row['patient_id']}:{row['encounter_id']}:{row['version']}"
            if target.scalar(select(Claim.id).where(Claim.legacy_claim_key==key)): stats["claims"]["existing"] += 1; continue
            patient=target.scalar(select(Patient).where(Patient.legacy_pid==row["patient_id"])); encounter=target.scalar(select(Encounter).where(Encounter.legacy_encounter_id==row["encounter_id"])); coverage=target.scalar(select(Coverage).where(Coverage.patient_id==patient.id,Coverage.payer_id==target.scalar(select(Payer.id).where(Payer.legacy_payer_id==row["payer_id"])))) if patient and row["payer_id"] else None
            claim_charges=list(target.scalars(select(Charge).where(Charge.patient_id==patient.id,Charge.encounter_id==encounter.id,Charge.claim_id.is_(None)))) if patient and encounter else []
            if not patient or not encounter or not claim_charges: stats["claims"]["rejected"] += 1; continue
            total=sum((x.unit_price*x.units for x in claim_charges),0); claim=Claim(legacy_claim_key=key,patient_id=patient.id,encounter_id=encounter.id,coverage_id=coverage.id if coverage else None,status="submitted" if row["bill_time"] else "draft",total=total,submitted_at=row["bill_time"]); target.add(claim); target.flush()
            for charge in claim_charges: charge.claim_id=claim.id
            stats["claims"]["inserted"] += 1
        immunizations=legacy.execute(text("SELECT id,patient_id,administered_date,cvx_code,manufacturer,lot_number,route,administration_site,amount_administered,amount_administered_unit,completion_status,refusal_reason,note,encounter_id FROM immunizations ORDER BY id"))
        for row in immunizations.mappings():
            stats["immunizations"]["source"]+=1
            if target.scalar(select(Immunization.id).where(Immunization.legacy_immunization_id==row["id"])): stats["immunizations"]["existing"]+=1; continue
            patient=target.scalar(select(Patient).where(Patient.legacy_pid==row["patient_id"])); encounter=target.scalar(select(Encounter).where(Encounter.legacy_encounter_id==row["encounter_id"])) if row["encounter_id"] else None; cvx=clean(row["cvx_code"])
            if not patient or not row["administered_date"] or not cvx: stats["immunizations"]["rejected"]+=1; continue
            dose=" ".join(filter(None,(str(row["amount_administered"]) if row["amount_administered"] else None,clean(row["amount_administered_unit"])))) or None
            target.add(Immunization(legacy_immunization_id=row["id"],patient_id=patient.id,encounter_id=encounter.id if encounter else None,administered_at=row["administered_date"],cvx_code=cvx,vaccine_name=f"CVX {cvx}",manufacturer=clean(row["manufacturer"]),lot_number=clean(row["lot_number"]),route=clean(row["route"]),site=clean(row["administration_site"]),dose=dose,status=clean(row["completion_status"]) or "completed",refusal_reason=clean(row["refusal_reason"]),note=clean(row["note"])))
            stats["immunizations"]["inserted"]+=1
        vitals=legacy.execute(text("SELECT id,pid,date,bps,bpd,weight,height,temperature,pulse,respiration,oxygen_saturation,BMI,note FROM form_vitals WHERE activity=1 ORDER BY id"))
        for row in vitals.mappings():
            stats["vitals"]["source"]+=1
            if target.scalar(select(VitalSet.id).where(VitalSet.legacy_vitals_id==row["id"])): stats["vitals"]["existing"]+=1; continue
            patient=target.scalar(select(Patient).where(Patient.legacy_pid==row["pid"]))
            if not patient or not row["date"]: stats["vitals"]["rejected"]+=1; continue
            target.add(VitalSet(legacy_vitals_id=row["id"],patient_id=patient.id,observed_at=row["date"],systolic=row["bps"] or None,diastolic=row["bpd"] or None,weight_kg=row["weight"] or None,height_cm=row["height"] or None,temperature_c=row["temperature"] or None,heart_rate=row["pulse"] or None,respiratory_rate=row["respiration"] or None,oxygen_saturation=row["oxygen_saturation"] or None,bmi=row["BMI"] or None,note=clean(row["note"])))
            stats["vitals"]["inserted"]+=1
        pharmacies=legacy.execute(text("SELECT id,name,email,ncpdp,npi FROM pharmacies ORDER BY id"))
        for row in pharmacies.mappings():
            stats["pharmacies"]["source"]+=1
            if target.scalar(select(Pharmacy.id).where(Pharmacy.legacy_pharmacy_id==row["id"])): stats["pharmacies"]["existing"]+=1; continue
            if not clean(row["name"]): stats["pharmacies"]["rejected"]+=1; continue
            target.add(Pharmacy(legacy_pharmacy_id=row["id"],name=clean(row["name"]),email=clean(row["email"]),ncpdp=str(row["ncpdp"]) if row["ncpdp"] else None,npi=str(row["npi"]) if row["npi"] else None)); stats["pharmacies"]["inserted"]+=1
        target.flush()
        prescriptions=legacy.execute(text("SELECT id,patient_id,pharmacy_id,encounter,date_added,start_date,end_date,drug,rxnorm_drugcode,drug_dosage_instructions,dosage,quantity,refills,substitute,indication,active FROM prescriptions ORDER BY id"))
        for row in prescriptions.mappings():
            stats["prescriptions"]["source"]+=1
            if target.scalar(select(Prescription.id).where(Prescription.legacy_prescription_id==row["id"])): stats["prescriptions"]["existing"]+=1; continue
            patient=target.scalar(select(Patient).where(Patient.legacy_pid==row["patient_id"])); encounter=target.scalar(select(Encounter).where(Encounter.legacy_encounter_id==row["encounter"])) if row["encounter"] else None; pharmacy=target.scalar(select(Pharmacy).where(Pharmacy.legacy_pharmacy_id==row["pharmacy_id"])) if row["pharmacy_id"] else None
            if not patient or not clean(row["drug"]): stats["prescriptions"]["rejected"]+=1; continue
            target.add(Prescription(legacy_prescription_id=row["id"],patient_id=patient.id,encounter_id=encounter.id if encounter else None,pharmacy_id=pharmacy.id if pharmacy else None,prescribed_at=row["date_added"] or datetime.now(timezone.utc),start_date=row["start_date"],end_date=row["end_date"],drug_name=clean(row["drug"]),rxnorm_code=clean(row["rxnorm_drugcode"]),dosage_instructions=clean(row["drug_dosage_instructions"]) or clean(row["dosage"]) or "As directed",quantity=clean(row["quantity"]),refills=row["refills"] or 0,substitutions_allowed=bool(row["substitute"]),indication=clean(row["indication"]),status="active" if row["active"] else "stopped")); stats["prescriptions"]["inserted"]+=1
        # OpenEMR's `forms` registry points to both core and installed/custom form tables.
        # Reflecting only tables that actually exist preserves every registered form payload.
        legacy_tables = set(inspect(source).get_table_names())
        forms = legacy.execute(text("SELECT id,date,encounter,form_name,form_id,pid,authorized,deleted,formdir FROM forms ORDER BY id"))
        known_types = {"soap": "soap", "ros": "ros", "physical_exam": "physical_exam", "clinic_note": "clinic_note"}
        for row in forms.mappings():
            stats["clinical_forms"]["source"] += 1; legacy_key = f"forms:{row['id']}"
            if target.scalar(select(ClinicalForm.id).where(ClinicalForm.legacy_form_key == legacy_key)): stats["clinical_forms"]["existing"] += 1; continue
            patient = target.scalar(select(Patient).where(Patient.legacy_pid == row["pid"])); encounter = target.scalar(select(Encounter).where(Encounter.legacy_encounter_id == row["encounter"]))
            formdir = clean(row["formdir"]) or "custom"; table_name = f"form_{formdir}"
            if not patient or not encounter or row["deleted"] or table_name not in legacy_tables: stats["clinical_forms"]["rejected"] += 1; continue
            columns = {item["name"] for item in inspect(source).get_columns(table_name)}
            key_column = "forms_id" if "forms_id" in columns else "id"
            payload_rows = legacy.execute(text(f"SELECT * FROM `{table_name}` WHERE `{key_column}`=:form_id"), {"form_id": row["form_id"] if key_column == "id" else row["id"]}).mappings().all()
            if not payload_rows: stats["clinical_forms"]["rejected"] += 1; continue
            content = {"rows": [{key: json_value(value) for key, value in payload.items()} for payload in payload_rows]}
            if formdir == "soap": content = {key: json_value(payload_rows[0].get(key)) for key in ("subjective", "objective", "assessment", "plan")}
            target.add(ClinicalForm(legacy_form_key=legacy_key, patient_id=patient.id, encounter_id=encounter.id, form_type=known_types.get(formdir, "custom"), title=clean(row["form_name"]) or formdir.replace("_", " ").title(), content=content, status="signed" if row["authorized"] else "draft", authored_at=row["date"] or encounter.occurred_at))
            stats["clinical_forms"]["inserted"] += 1
        if commit: target.commit()
        else: target.rollback()
    stats["mode"] = "committed" if commit else "dry-run"
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--source", required=True); parser.add_argument("--commit", action="store_true")
    args = parser.parse_args(); print(json.dumps(run(args.source, args.commit), indent=2))
