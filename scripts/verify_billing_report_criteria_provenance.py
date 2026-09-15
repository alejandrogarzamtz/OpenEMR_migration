#!/usr/bin/env python3
"""Guard the two embedded Billing Manager criteria assets and their typed replacements."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1];contract=json.loads((root/"docs/legacy-billing-report-criteria-contract.json").read_text());source_mode="versioned-snapshot"
if all((root/item["path"]).is_file() for item in contract["sources"].values()):
    for name,item in contract["sources"].items():
        path=root/item["path"];content=path.read_text()
        for token in item["required_tokens"]:assert token in content,f"legacy {name} contract missing: {token}"
        assert hashlib.sha256(path.read_bytes()).hexdigest()==item["sha256"]
    source_mode="preserved-tree-and-versioned-snapshot"
schemas=(root/"backend/app/schemas.py").read_text();reports=(root/"backend/app/services/reports.py").read_text();frontend=(root/"frontend/src/features/reports/ReportWorkspace.tsx").read_text()
for token in ("date_from", "date_to", "status", "patient_uuid", "facility_uuid", "payer_legacy_id", "provider_legacy_id"):assert token in schemas,f"typed billing criterion missing: {token}"
for token in ('embedded={"criteria.tab","report.script"}', '"migration_status"'):assert token in reports,f"embedded catalog contract missing: {token}"
for token in ("CollectionFilters", "ReceiptMethodFilters", "PaymentProcessingFilters", "Embedded component"):assert token in frontend,f"modern billing criteria UI missing: {token}"
print(f"Embedded billing-report criteria provenance verified ({source_mode})")
