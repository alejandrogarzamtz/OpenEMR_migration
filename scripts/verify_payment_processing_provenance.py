#!/usr/bin/env python3
"""Guard lossless gateway-audit and reversal provenance."""
from pathlib import Path
import os
import re

ROOT=Path(__file__).resolve().parents[1]
EXPECTED={"uuid","service","pid","success","action_name","amount","ticket","transaction_id","audit_data","date","map_uuid","map_transaction_id","reverted","revert_action_name","revert_transaction_id","revert_audit_data","revert_date"}


def main():
    importer=(ROOT/"backend/app/import_legacy.py").read_text()
    if "SELECT * FROM payment_processing_audit ORDER BY date,uuid" not in importer:raise SystemExit("payment processing complete-row import missing")
    mapped=('legacy_uuid_hex=legacy_uuid','audit_ciphertext=json_value(row["audit_data"])','revert_audit_ciphertext=json_value(row["revert_audit_data"])','map_legacy_uuid_hex=json_value(row["map_uuid"])','map_transaction_id=clean(row["map_transaction_id"])','revert_action_name=clean(row["revert_action_name"])','revert_transaction_id=clean(row["revert_transaction_id"])','legacy_payload={key:json_value(value) for key,value in row.items()}')
    if any(token not in importer for token in mapped):raise SystemExit("payment processing typed/ciphertext provenance is incomplete")
    database=Path(os.environ.get("OPENRM_LEGACY_ROOT",ROOT/"openemr-legacy"))/"sql/database.sql"
    if database.is_file():
        match=re.search(r"CREATE TABLE `?payment_processing_audit`? \((.*?)\n\) ENGINE",database.read_text(),re.S)
        if not match:raise SystemExit("missing payment_processing_audit")
        actual=set(re.findall(r"^\s*`?([A-Za-z][A-Za-z0-9_]*)`?\s+",match.group(1),re.M))-{"PRIMARY","KEY","UNIQUE","CONSTRAINT"}
        if actual!=EXPECTED:raise SystemExit(f"payment_processing_audit: missing={sorted(EXPECTED-actual)} extra={sorted(actual-EXPECTED)}")
    print("payment processing provenance contract verified")


if __name__=="__main__":main()
