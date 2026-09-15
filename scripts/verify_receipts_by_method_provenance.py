#!/usr/bin/env python3
"""Guard payment, payer, method and encounter provenance for receipt summaries."""
from pathlib import Path
import os
import re

ROOT=Path(__file__).resolve().parents[1]
REQUIRED={
    "ar_activity":{"pid","encounter","sequence_no","session_id","memo","payer_type","code_type","code","modifier","pay_amount","adj_amount","follow_up_note","reason_code","deleted","post_date","payer_claim_number"},
    "ar_session":{"session_id","payer_id","reference","deposit_date","payment_method"},
    "list_options":{"list_id","option_id","title"},
    "billing":{"pid","encounter","code_type","code","modifier","provider_id","fee","activity"},
    "form_encounter":{"pid","encounter","date","facility_id","provider_id","invoice_refno"},
}


def main():
    importer=(ROOT/"backend/app/import_legacy.py").read_text()
    mapped=("lo.list_id='payment_method'","payment_method_label=clean(row[\"session_payment_method_label\"])","memo=clean(row[\"memo\"])","follow_up_note=clean(row[\"follow_up_note\"])","reason_code=clean(row[\"reason_code\"])","post_date=row[\"post_date\"]","payer_claim_number=clean(row[\"payer_claim_number\"])")
    if any(token not in importer for token in mapped):raise SystemExit("receipts-by-method provenance mapping is incomplete")
    database=Path(os.environ.get("OPENRM_LEGACY_ROOT",ROOT/"openemr-legacy"))/"sql/database.sql"
    if database.is_file():
        sql=database.read_text()
        for table,required in REQUIRED.items():
            match=re.search(rf"CREATE TABLE `?{table}`? \((.*?)\n\) ENGINE",sql,re.S)
            if not match:raise SystemExit(f"missing legacy table {table}")
            actual=set(re.findall(r"^\s*`?([A-Za-z][A-Za-z0-9_]*)`?\s+",match.group(1),re.M))-{"PRIMARY","KEY","UNIQUE","CONSTRAINT"}
            if not required<=actual:raise SystemExit(f"{table}: missing={sorted(required-actual)}")
    print("receipts by method provenance contract verified")


if __name__=="__main__":main()
