#!/usr/bin/env python3
"""Fail CI if the printable Superbill loses a required legacy contract."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
contract=json.loads((root/"docs/legacy-superbill-contract.json").read_text())
legacy_path=root/"openemr-legacy/interface/reports/custom_report_range.php"
library_path=root/"openemr-legacy/library/report.inc.php"
models=(root/"backend/app/models.py").read_text()
importer=(root/"backend/app/import_legacy.py").read_text()
reports=(root/"backend/app/services/reports.py").read_text()

source_mode="versioned-snapshot"
if legacy_path.is_file() and library_path.is_file():
    legacy=legacy_path.read_text();library=library_path.read_text()
    for token in contract["required_report_tokens"]:
        assert token in legacy,f"legacy Superbill contract missing: {token}"
    for token in contract["required_library_tokens"]:
        assert token in library,f"legacy report helper contract missing: {token}"
    assert hashlib.sha256(legacy_path.read_bytes()).hexdigest()==contract["report_sha256"]
    assert hashlib.sha256(library_path.read_bytes()).hexdigest()==contract["library_sha256"]
    source_mode="preserved-tree-and-versioned-snapshot"
for token in ("def superbill_report","ClinicalForm.title==\"New Patient Encounter\"","Charge.active.is_(True)","ReceivableActivity.account_code==\"PCP\"","ReceivableActivity.deleted_at.is_(None)","physician_signature"):
    assert token in reports,f"modern Superbill contract missing: {token}"
assert "legacy_payload: Mapped[dict | None]" in models
assert 'SELECT * FROM insurance_data ORDER BY id' in importer
assert 'legacy_payload=payload' in importer
print(f"Superbill provenance contract verified ({source_mode})")
