#!/usr/bin/env python3
"""Fail CI if the printable Superbill loses a required legacy contract."""
from pathlib import Path

root=Path(__file__).resolve().parents[1]
legacy=(root/"openemr-legacy/interface/reports/custom_report_range.php").read_text()
library=(root/"openemr-legacy/library/report.inc.php").read_text()
models=(root/"backend/app/models.py").read_text()
importer=(root/"backend/app/import_legacy.py").read_text()
reports=(root/"backend/app/services/reports.py").read_text()

for token in ("form_name = 'New Patient Encounter'","getRecPatientData","getRecInsuranceData","getPatientBillingEncounter","getPatientCopay","Physician Signature"):
    assert token in legacy,f"legacy Superbill contract missing: {token}"
for token in ("select * from patient_data","select *, ic.name as provider_name","b.provider_id != 0","b.provider_id  = 0","activity = '1'"):
    assert token in library,f"legacy report helper contract missing: {token}"
for token in ("def superbill_report","ClinicalForm.title==\"New Patient Encounter\"","Charge.active.is_(True)","ReceivableActivity.account_code==\"PCP\"","ReceivableActivity.deleted_at.is_(None)","physician_signature"):
    assert token in reports,f"modern Superbill contract missing: {token}"
assert "legacy_payload: Mapped[dict | None]" in models
assert 'SELECT * FROM insurance_data ORDER BY id' in importer
assert 'legacy_payload=payload' in importer
print("Superbill provenance contract verified")
