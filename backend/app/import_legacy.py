"""Idempotent OpenEMR MySQL importer with dry-run reconciliation.

Usage:
  python -m app.import_legacy --source mysql+pymysql://user:pass@host/openemr
  python -m app.import_legacy --source ... --commit
"""
import argparse
import json
from datetime import date
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session
from .db import Base, engine as target_engine
from .models import ClinicalItem, Encounter, Patient

TYPE_MAP = {"medical_problem": "problem", "allergy": "allergy", "medication": "medication"}


def clean(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def valid_dob(value):
    return value if isinstance(value, date) and value.year > 1800 else date(1900, 1, 1)


def run(source_url: str, commit: bool = False) -> dict:
    source = create_engine(source_url)
    Base.metadata.create_all(target_engine)
    stats = {"patients": {"source": 0, "inserted": 0, "existing": 0}, "clinical_items": {"source": 0, "inserted": 0, "existing": 0}, "encounters": {"source": 0, "inserted": 0, "existing": 0}}
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
        if commit: target.commit()
        else: target.rollback()
    stats["mode"] = "committed" if commit else "dry-run"
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--source", required=True); parser.add_argument("--commit", action="store_true")
    args = parser.parse_args(); print(json.dumps(run(args.source, args.commit), indent=2))
