#!/usr/bin/env python3
"""Guard OpenEMR Standard and Portal compatibility contracts."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1];parity=json.loads((root/"docs/api-parity.json").read_text());api=(root/"backend/app/api/openemr_compat.py").read_text();tests=(root/"backend/tests/test_openemr_compat.py").read_text();portal=[key for key in parity if "/portal/" in key]
standard=[key for key in parity if "/api/" in key]
assert len(parity)==66 and len(standard)==61 and len(portal)==5
assert all(parity[key]["status"]=="MIGRATED" for key in parity)
for token in ('/apis/{site}/api/patient','/apis/{site}/api/facility','/apis/{site}/api/practitioner','/apis/{site}/portal/patient','soap_note','medical_problem','dental_issue','IdentityAuditEvent','validationErrors'):assert token in api,f"OpenEMR compatibility contract missing: {token}"
for token in ("test_standard_api_core_contract_and_legacy_envelope","test_standard_api_clinical_resources_and_encounter_notes","test_portal_compatibility_contract_is_patient_isolated"):assert token in tests,f"OpenEMR compatibility test missing: {token}"
print(f"OpenEMR API compatibility verified ({len(parity)} routes)")
