#!/usr/bin/env python3
"""Guard OpenEMR Standard and Portal compatibility contracts."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1];parity=json.loads((root/"docs/api-parity.json").read_text());api=(root/"backend/app/api/openemr_compat.py").read_text();tests=(root/"backend/tests/test_openemr_compat.py").read_text();models=(root/"backend/app/models.py").read_text();legacy_import=(root/"backend/app/import_legacy.py").read_text();portal=[key for key in parity if "/portal/" in key]
standard=[key for key in parity if "/api/" in key]
assert len(parity)==74 and len(standard)==69 and len(portal)==5
assert all(parity[key]["status"]=="MIGRATED" for key in parity)
for token in ('/apis/{site}/api/patient','/apis/{site}/api/facility','/apis/{site}/api/practitioner','/apis/{site}/api/insurance_company','/apis/{site}/api/list/{list_name}','/apis/{site}/portal/patient','soap_note','medical_problem','dental_issue','IdentityAuditEvent','validationErrors'):assert token in api,f"OpenEMR compatibility contract missing: {token}"
for token in ("test_standard_api_core_contract_and_legacy_envelope","test_standard_api_clinical_resources_and_encounter_notes","test_standard_api_administration_and_reference_catalogs","test_portal_compatibility_contract_is_patient_isolated"):assert token in tests,f"OpenEMR compatibility test missing: {token}"
for token in ("class ReferenceOption","class InsuranceType","legacy_payload: Mapped[dict | None]"):assert token in models,f"Reference catalog model missing: {token}"
for token in ("SELECT * FROM list_options ORDER BY list_id,seq,option_id","SELECT id,type,claim_type FROM insurance_type_codes ORDER BY id"):assert token in legacy_import,f"Reference catalog import missing: {token}"
print(f"OpenEMR API compatibility verified ({len(parity)} routes)")
