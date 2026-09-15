#!/usr/bin/env python3
"""Guard complete source retention required by front-office receipts."""
from pathlib import Path
import os
import re

ROOT=Path(__file__).resolve().parents[1]
EXPECTED={"id","pid","dtime","encounter","user","method","source","amount1","amount2","posted1","posted2"}


def main():
    importer=(ROOT/"backend/app/import_legacy.py").read_text()
    if "SELECT * FROM payments ORDER BY id" not in importer:raise SystemExit("payments complete-row import missing")
    mapped=('legacy_payment_id=row["id"]','received_at=row["dtime"]','current_amount=row["amount1"]','previous_amount=row["amount2"]','posted_current_amount=row["posted1"]','posted_previous_amount=row["posted2"]','legacy_payload={key:json_value(value) for key,value in row.items()}')
    if any(token not in importer for token in mapped):raise SystemExit("front receipt typed provenance mapping is incomplete")
    database=Path(os.environ.get("OPENRM_LEGACY_ROOT",ROOT/"openemr-legacy"))/"sql/database.sql"
    if database.is_file():
        match=re.search(r"CREATE TABLE `?payments`? \((.*?)\n\) ENGINE",database.read_text(),re.S)
        if not match:raise SystemExit("missing legacy payments table")
        actual=set(re.findall(r"^\s*`?([A-Za-z][A-Za-z0-9_]*)`?\s+",match.group(1),re.M))-{"PRIMARY","KEY","UNIQUE","CONSTRAINT"}
        if actual!=EXPECTED:raise SystemExit(f"payments: missing={sorted(EXPECTED-actual)} extra={sorted(actual-EXPECTED)}")
    print("front receipts provenance contract verified")


if __name__=="__main__":main()
