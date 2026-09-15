#!/usr/bin/env python3
"""Guard standalone prepayment-session and balance provenance."""
from pathlib import Path
import os
import re

ROOT=Path(__file__).resolve().parents[1]
EXPECTED={"session_id","payer_id","user_id","closed","reference","check_date","deposit_date","pay_total","created_time","modified_time","global_amount","payment_type","description","adjustment_code","post_to_date","patient_id","payment_method"}


def main():
    importer=(ROOT/"backend/app/import_legacy.py").read_text()
    required=("SELECT s.*,{method_column} FROM ar_session s","legacy_session_id=row[\"session_id\"]","pay_total=row[\"pay_total\"] or 0","global_amount=row[\"global_amount\"] or 0","adjustment_code=clean(row[\"adjustment_code\"])","legacy_payload={key:json_value(value) for key,value in row.items()}")
    if any(token not in importer for token in required):raise SystemExit("prepayment session typed/lossless import is incomplete")
    reports=(ROOT/"backend/app/services/reports.py").read_text()
    for token in ('ReceivableSession.adjustment_code=="pre_payment"','ReceivableSession.closed.is_(False)','unapplied=item.pay_total-used','unapplied<=Decimal("0.005")','ReceivableSession.global_amount!=0'):
        if token not in reports:raise SystemExit("prepayment legacy arithmetic/filter contract is incomplete")
    database=Path(os.environ.get("OPENRM_LEGACY_ROOT",ROOT/"openemr-legacy"))/"sql/database.sql"
    if database.is_file():
        match=re.search(r"CREATE TABLE `?ar_session`? \((.*?)\n\) ENGINE",database.read_text(),re.S)
        if not match:raise SystemExit("missing ar_session")
        actual=set(re.findall(r"^\s*`?([A-Za-z][A-Za-z0-9_]*)`?\s+",match.group(1),re.M))-{"PRIMARY","KEY","UNIQUE","CONSTRAINT"}
        if actual!=EXPECTED:raise SystemExit(f"ar_session: missing={sorted(EXPECTED-actual)} extra={sorted(actual-EXPECTED)}")
    print("prepayment provenance contract verified")


if __name__=="__main__":main()
