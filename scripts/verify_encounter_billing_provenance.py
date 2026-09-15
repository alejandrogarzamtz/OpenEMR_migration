#!/usr/bin/env python3
"""Guard source retention used by appointment/encounter reconciliation."""
from pathlib import Path
import os
import re

ROOT=Path(__file__).resolve().parents[1]
REQUIRED={
    "form_encounter":{"id","pid","encounter","date","facility_id","provider_id","class_code"},
    "billing":{"id","date","code_type","code","pid","encounter","authorized","billed","activity","modifier","fee","justify"},
    "code_types":{"ct_key","ct_id","ct_just","ct_fee","ct_diag","ct_active","ct_proc"},
    "ar_activity":{"pid","encounter","sequence_no","payer_type","post_time","account_code","pay_amount","adj_amount","deleted"},
    "forms":{"id","pid","encounter","authorized","deleted","formdir"},
}


def main():
    importer=(ROOT/"backend/app/import_legacy.py").read_text()
    for table in REQUIRED:
        if f'SELECT * FROM {table}' not in importer:raise SystemExit(f"{table}: complete-row import missing")
    mapped=("authorized=bool(row[\"authorized\"])","billed=bool(row[\"billed\"])","active=bool(row[\"activity\"])","justification=clean(row[\"justify\"])","account_code=clean(row[\"account_code\"])","source_formdir=formdir","registry_payload={key:json_value(value) for key,value in row.items()}","legacy_payload={key:json_value(value) for key,value in row.items()}")
    if any(token not in importer for token in mapped):raise SystemExit("encounter/billing typed provenance mapping is incomplete")
    database=Path(os.environ.get("OPENRM_LEGACY_ROOT",ROOT/"openemr-legacy"))/"sql/database.sql"
    if database.is_file():
        sql=database.read_text()
        for table,required in REQUIRED.items():
            match=re.search(rf"CREATE TABLE `?{table}`? \((.*?)\n\) ENGINE",sql,re.S)
            if not match:raise SystemExit(f"missing legacy table {table}")
            actual=set(re.findall(r"^\s*`?([A-Za-z][A-Za-z0-9_]*)`?\s+",match.group(1),re.M))
            if not required<=actual:raise SystemExit(f"{table}: missing={sorted(required-actual)}")
    print("encounter billing provenance contract verified")


if __name__=="__main__":main()
