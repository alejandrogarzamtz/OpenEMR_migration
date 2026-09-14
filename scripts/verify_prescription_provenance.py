#!/usr/bin/env python3
"""Guard the lossless pharmacy and prescription import contract."""
from pathlib import Path
import os
import re

ROOT=Path(__file__).resolve().parents[1]
EXPECTED={
    "pharmacies":{"id","name","transmit_method","email","ncpdp","npi"},
    "prescriptions":{"id","uuid","patient_id","filled_by_id","pharmacy_id","date_added","date_modified","provider_id","encounter","start_date","drug","drug_id","rxnorm_drugcode","form","dosage","quantity","size","unit","route","interval","substitute","refills","per_refill","filled_date","medication","note","active","datetime","user","site","prescriptionguid","erx_source","erx_uploaded","drug_info_erx","external_id","end_date","indication","prn","ntx","rtx","txDate","usage_category","usage_category_title","request_intent","request_intent_title","drug_dosage_instructions","diagnosis","created_by","updated_by"},
}


def main():
    importer=(ROOT/"backend/app/import_legacy.py").read_text()
    for table in EXPECTED:
        if f'SELECT * FROM {table}' not in importer:
            raise SystemExit(f"{table}: importer no longer reads the complete row")
    if importer.count("legacy_payload={key:json_value(value) for key,value in row.items()}")<4:
        raise SystemExit("full source payload retention is missing")
    database=Path(os.environ.get("OPENRM_LEGACY_ROOT",ROOT/"openemr-legacy"))/"sql/database.sql"
    if database.is_file():
        sql=database.read_text()
        for table,expected in EXPECTED.items():
            match=re.search(rf"CREATE TABLE `{table}` \((.*?)\n\) ENGINE",sql,re.S)
            if not match:raise SystemExit(f"missing legacy table {table}")
            actual=set(re.findall(r"^\s*`([A-Za-z][A-Za-z0-9_]*)`\s+",match.group(1),re.M))
            if actual!=expected:raise SystemExit(f"{table}: missing={sorted(expected-actual)} extra={sorted(actual-expected)}")
    print("prescription provenance contract verified")


if __name__=="__main__":main()
