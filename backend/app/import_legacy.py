"""Idempotent OpenEMR MySQL importer with dry-run reconciliation.

Usage:
  python -m app.import_legacy --source mysql+pymysql://user:pass@host/openemr
  python -m app.import_legacy --source ... --commit
"""
import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session
from .db import Base, engine as target_engine
from .models import ClinicalItem, Document, Encounter, LabOrder, LabResult, Patient

TYPE_MAP = {"medical_problem": "problem", "allergy": "allergy", "medication": "medication"}


def clean(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def valid_dob(value):
    return value if isinstance(value, date) and value.year > 1800 else date(1900, 1, 1)


def run(source_url: str, commit: bool = False) -> dict:
    source = create_engine(source_url)
    Base.metadata.create_all(target_engine)
    names = ("patients", "clinical_items", "encounters", "lab_orders", "lab_results", "documents")
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
        if commit: target.commit()
        else: target.rollback()
    stats["mode"] = "committed" if commit else "dry-run"
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--source", required=True); parser.add_argument("--commit", action="store_true")
    args = parser.parse_args(); print(json.dumps(run(args.source, args.commit), indent=2))
