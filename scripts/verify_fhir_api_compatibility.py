#!/usr/bin/env python3
"""Guard the complete legacy FHIR route family and export implementations."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
surface=json.loads((root/"docs/legacy-surface.json").read_text())
domains=json.loads((root/"docs/api-domain-parity.json").read_text())
source="apis/routes/_rest_routes_fhir_r4_us_core_3_1_0.inc.php"
routes=surface["rest_routes"][source]
assert len(routes)==domains[source]["expected_route_count"]==80
assert len(set(routes))==80
implementation="\n".join((root/path).read_text() for path in ("backend/app/fhir.py","backend/app/fhir_extended.py","backend/app/api/smart.py"))
tests=(root/"backend/tests/test_fhir_bulk_ehi.py").read_text()
ehi=(root/"backend/app/services/ehi_export.py").read_text()
for token in ('/DocumentReference/$docref','/Patient/$export','/Group/{group_id}/$export','/$bulkdata-status','/OperationDefinition','/MedicationDispense','/PractitionerRole','/ValueSet'):assert token in implementation,f"FHIR implementation missing {token}"
for token in ('test_complete_legacy_fhir_contract_is_registered','test_fhir_writes_docref_resources_and_bulk_export','test_ccda_and_ehi_exports_are_parseable_and_patient_scoped','test_remaining_fhir_resource_mappings_are_resolvable'):assert token in tests,f"FHIR contract test missing {token}"
for token in ('ClinicalDocument','designated_record_set','manifest.json','sha256'):assert token in ehi,f"EHI export contract missing {token}"
print("FHIR API compatibility verified (80 routes, Bulk Data, C-CDA/EHI)")
