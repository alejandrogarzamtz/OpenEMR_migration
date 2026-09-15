#!/usr/bin/env python3
"""Guard the versioned non-reported syndromic-surveillance contract."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1];contract=json.loads((root/"docs/legacy-syndromic-contract.json").read_text())
legacy_path=root/"openemr-legacy/interface/reports/non_reported.php";source_mode="versioned-snapshot"
if legacy_path.is_file():
    legacy=legacy_path.read_text()
    for token in contract["required_tokens"]:assert token in legacy,f"legacy syndromic contract missing: {token}"
    assert hashlib.sha256(legacy_path.read_bytes()).hexdigest()==contract["report_sha256"]
    source_mode="preserved-tree-and-versioned-snapshot"
models=(root/"backend/app/models.py").read_text();importer=(root/"backend/app/import_legacy.py").read_text();reports=(root/"backend/app/services/reports.py").read_text();api=(root/"backend/app/api/reports.py").read_text()
for token in ("class SyndromicSubmission","recorded_at: Mapped[datetime | None]","legacy_payload: Mapped[dict | None]"):
    assert token in models,f"syndromic persistence missing: {token}"
for token in ("SELECT * FROM lists WHERE type IN","SELECT * FROM syndromic_surveillance ORDER BY id"):
    assert token in importer,f"syndromic import missing: {token}"
for token in ("def non_reported_syndromic_report","ClinicalItem.code_system==\"ICD9\"","payload.get(\"reportable\")","SyndromicSubmission.clinical_item_id"):
    assert token in reports,f"syndromic report missing: {token}"
for token in ('/export.hl7','ADT^A01^ADT_A01','PH_SS-NoAck^SS Sender','DG1|1||','db.add(SyndromicSubmission'):
    assert token in api,f"syndromic HL7 export missing: {token}"
print(f"Syndromic surveillance provenance verified ({source_mode})")
