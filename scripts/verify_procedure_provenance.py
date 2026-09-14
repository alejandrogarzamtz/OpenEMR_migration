#!/usr/bin/env python3
"""Guard the lossless procedure-order import contract in source and CI."""
from pathlib import Path
import os
import re

ROOT=Path(__file__).resolve().parents[1]
EXPECTED={
    "procedure_order":{"procedure_order_id","uuid","provider_id","patient_id","encounter_id","date_collected","date_ordered","order_priority","order_status","patient_instructions","activity","control_id","lab_id","specimen_type","specimen_location","specimen_volume","date_transmitted","clinical_hx","external_id","history_order","order_diagnosis","billing_type","specimen_fasting","order_psc","order_abn","collector_id","account","account_facility","provider_number","procedure_order_type","scheduled_date","scheduled_start","scheduled_end","performer_type","order_intent","location_id"},
    "procedure_order_code":{"procedure_order_id","procedure_order_seq","procedure_code","procedure_name","procedure_source","diagnoses","do_not_send","procedure_order_title","procedure_type","transport","date_end","reason_code","reason_description","reason_date_low","reason_date_high","reason_status"},
    "procedure_report":{"procedure_report_id","uuid","procedure_order_id","procedure_order_seq","date_collected","date_collected_tz","date_report","date_report_tz","source","specimen_num","report_status","review_status","report_notes"},
    "procedure_result":{"procedure_result_id","uuid","procedure_report_id","result_data_type","result_code","result_text","date","facility","units","result","range","abnormal","comments","document_id","result_status","date_end"},
}


def main():
    importer=(ROOT/"backend/app/import_legacy.py").read_text()
    for table in EXPECTED:
        required=(f'SELECT * FROM {table}', 'legacy_payload={key:json_value(value) for key,value in row.items()}')
        if any(token not in importer for token in required):
            raise SystemExit(f"{table}: importer no longer guarantees full-row retention")
    legacy_root=Path(os.environ.get("OPENRM_LEGACY_ROOT",ROOT/"openemr-legacy"))
    database=legacy_root/"sql/database.sql"
    if database.is_file():
        sql=database.read_text()
        for table,expected in EXPECTED.items():
            match=re.search(rf"CREATE TABLE `{table}` \((.*?)\n\) ENGINE",sql,re.S)
            if not match: raise SystemExit(f"missing legacy table {table}")
            actual=set(re.findall(r"^\s*`([A-Za-z][A-Za-z0-9_]*)`\s+",match.group(1),re.M))
            if actual!=expected: raise SystemExit(f"{table}: missing={sorted(expected-actual)} extra={sorted(actual-expected)}")
    print("procedure provenance contract verified")


if __name__=="__main__":main()
