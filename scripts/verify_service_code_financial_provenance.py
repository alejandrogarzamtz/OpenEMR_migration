#!/usr/bin/env python3
"""Guard financial service-code provenance and legacy aggregation rules."""
from pathlib import Path
import os
import re

ROOT=Path(__file__).resolve().parents[1]


def main():
    importer=(ROOT/"backend/app/import_legacy.py").read_text()
    for token in ('SELECT * FROM codes ORDER BY id','financial_reporting=bool(row["financial_reporting"])','legacy_payload={field:json_value(value) for field,value in row.items()}'):
        if token not in importer:raise SystemExit("service-code financial reporting provenance is incomplete")
    reports=(ROOT/"backend/app/services/reports.py").read_text()
    required=('BillingCodeType.fee.is_(True)','ReceivableActivity.deleted_at.is_(None)','entry["amount_billed"]+=charge.unit_price','entry["paid_amount"]+=activity[0]','balance=entry["amount_billed"]-entry["paid_amount"]-entry["adjustment_amount"]','financial_reporting_only')
    if any(token not in reports for token in required):raise SystemExit("financial summary legacy aggregation is incomplete")
    database=Path(os.environ.get("OPENRM_LEGACY_ROOT",ROOT/"openemr-legacy"))/"sql/database.sql"
    if database.is_file():
        match=re.search(r"CREATE TABLE `?codes`? \((.*?)\n\) ENGINE",database.read_text(),re.S)
        if not match or not re.search(r"^\s*`?financial_reporting`?\s+",match.group(1),re.M):raise SystemExit("codes.financial_reporting source column missing")
    print("service code financial provenance contract verified")


if __name__=="__main__":main()
