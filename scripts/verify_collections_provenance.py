#!/usr/bin/env python3
"""Guard source and typed provenance required by the collections report."""
from pathlib import Path
import os
import re

ROOT=Path(__file__).resolve().parents[1]
REQUIRED={
    "form_encounter":{"pid","encounter","date","facility_id","provider_id","last_level_closed","stmt_count","last_stmt_date","invoice_refno","in_collection"},
    "billing":{"id","pid","encounter","date","code_type","code","modifier","fee","activity"},
    "drug_sales":{"sale_id","pid","encounter","sale_date","fee","quantity"},
    "ar_activity":{"pid","encounter","sequence_no","session_id","payer_type","post_time","account_code","code_type","code","modifier","pay_amount","adj_amount","deleted"},
    "ar_session":{"session_id","payer_id","reference","check_date","deposit_date","payment_method"},
    "insurance_data":{"id","pid","type","provider","policy_number","group_number","date","date_end"},
}


def main():
    importer=(ROOT/"backend/app/import_legacy.py").read_text()
    tokens=('SELECT a.*,','LEFT JOIN ar_session s ON s.session_id=a.session_id','legacy_session_id=row["session_id"]','legacy_payer_id=row["session_payer_id"]','payment_reference=clean(row["session_reference"])','check_date=row["session_check_date"]','deposit_date=row["session_deposit_date"]','payment_method=clean(row["session_payment_method"])')
    if any(token not in importer for token in tokens):raise SystemExit("collections payment-session mapping is incomplete")
    database=Path(os.environ.get("OPENRM_LEGACY_ROOT",ROOT/"openemr-legacy"))/"sql/database.sql"
    if database.is_file():
        sql=database.read_text()
        for table,required in REQUIRED.items():
            match=re.search(rf"CREATE TABLE `?{table}`? \((.*?)\n\) ENGINE",sql,re.S)
            if not match:raise SystemExit(f"missing legacy table {table}")
            actual=set(re.findall(r"^\s*`?([A-Za-z][A-Za-z0-9_]*)`?\s+",match.group(1),re.M))
            if not required<=actual:raise SystemExit(f"{table}: missing={sorted(required-actual)}")
    print("collections report provenance contract verified")


if __name__=="__main__":main()
