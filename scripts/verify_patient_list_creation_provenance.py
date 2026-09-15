#!/usr/bin/env python3
"""Guard patient-list cohort and source-provenance parity."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1];contract=json.loads((root/"docs/legacy-patient-list-creation-contract.json").read_text());legacy_path=root/"openemr-legacy/interface/reports/patient_list_creation.php";source_mode="versioned-snapshot"
if legacy_path.is_file():
    legacy=legacy_path.read_text()
    for token in contract["required_tokens"]:assert token in legacy,f"legacy patient-list contract missing: {token}"
    assert hashlib.sha256(legacy_path.read_bytes()).hexdigest()==contract["report_sha256"]
    source_mode="preserved-tree-and-versioned-snapshot"
reports=(root/"backend/app/services/reports.py").read_text();schemas=(root/"backend/app/schemas.py").read_text();api=(root/"backend/app/api/reports.py").read_text();importer=(root/"backend/app/import_legacy.py").read_text();frontend=(root/"frontend/src/features/reports/ReportWorkspace.tsx").read_text()
for token in ("def patient_list_creation_report","demos|allergs|probs|meds|prescripts|comms|insurers|encounts|observs|procs|results","procedure_provider_names","source_formdir==\"observation\"","patient_list_sort_order"):
    assert token in reports+schemas+importer,f"modern patient-list contract missing: {token}"
for token in ("option_permission","patients:rx:read","encounters:coding_a:read","patients:lab:read"):assert token in api,f"patient-list permission contract missing: {token}"
assert "function PatientListCreationFilters" in frontend
print(f"Patient-list creation provenance verified ({source_mode})")
