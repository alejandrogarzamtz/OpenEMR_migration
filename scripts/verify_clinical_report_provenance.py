#!/usr/bin/env python3
"""Guard legacy source retention required by the clinical cohort report."""
from pathlib import Path
import os
import re

ROOT=Path(__file__).resolve().parents[1]
EXPECTED={
    "billing":{"id","date","code_type","code","pid","provider_id","user","groupname","authorized","encounter","code_text","billed","activity","payer_id","bill_process","bill_date","process_date","process_file","modifier","units","fee","justify","target","x12_partner_id","ndc_info","notecodes","external_id","pricelevel","revenue_code","chargecat"},
    "immunizations":{"id","uuid","patient_id","administered_date","immunization_id","cvx_code","manufacturer","lot_number","administered_by_id","administered_by","education_date","vis_date","note","create_date","update_date","created_by","updated_by","amount_administered","amount_administered_unit","expiration_date","route","administration_site","added_erroneously","external_id","completion_status","information_source","refusal_reason","ordering_provider","reason_code","reason_description","encounter_id"},
}


def main():
    importer=(ROOT/"backend/app/import_legacy.py").read_text()
    for table in EXPECTED:
        if f'SELECT * FROM {table}' not in importer:
            raise SystemExit(f"{table}: importer no longer reads complete source rows")
    required=("billed_at=row[\"date\"]","dose_unit=clean(row[\"amount_administered_unit\"])","standard_code=procedure_standards.get","legacy_payload={key:json_value(value) for key,value in row.items()}")
    if any(token not in importer for token in required):raise SystemExit("clinical-report provenance mapping is incomplete")
    database=Path(os.environ.get("OPENRM_LEGACY_ROOT",ROOT/"openemr-legacy"))/"sql/database.sql"
    if database.is_file():
        sql=database.read_text()
        for table,expected in EXPECTED.items():
            match=re.search(rf"CREATE TABLE `{table}` \((.*?)\n\) ENGINE",sql,re.S)
            if not match:raise SystemExit(f"missing legacy table {table}")
            actual=set(re.findall(r"^\s*`([A-Za-z][A-Za-z0-9_]*)`\s+",match.group(1),re.M))
            if actual!=expected:raise SystemExit(f"{table}: missing={sorted(expected-actual)} extra={sorted(actual-expected)}")
    print("clinical report provenance contract verified")


if __name__=="__main__":main()
