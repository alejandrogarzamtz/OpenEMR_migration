#!/usr/bin/env python3
"""Guard patient-ledger monetary and source-provenance parity."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1];contract=json.loads((root/"docs/legacy-patient-ledger-contract.json").read_text());legacy_path=root/"openemr-legacy/interface/reports/pat_ledger.php";source_mode="versioned-snapshot"
if legacy_path.is_file():
    legacy=legacy_path.read_text()
    for token in contract["required_tokens"]:assert token in legacy,f"legacy patient-ledger contract missing: {token}"
    assert hashlib.sha256(legacy_path.read_bytes()).hexdigest()==contract["report_sha256"]
    source_mode="preserved-tree-and-versioned-snapshot"
reports=(root/"backend/app/services/reports.py").read_text();models=(root/"backend/app/models.py").read_text();importer=(root/"backend/app/import_legacy.py").read_text()
for token in ("def patient_ledger_report","Patient ledger requires patient_uuid","BillingCodeType.procedure.is_(True)","Charge.active.is_(True)","ReceivableActivity.deleted_at.is_(None)","session.pay_total-applied","effect=-(payment+adjustment)"):
    assert token in reports,f"modern patient-ledger contract missing: {token}"
for token in ("class ReceivableSession","class ReceivableActivity","legacy_payload: Mapped[dict | None]"):
    assert token in models,f"patient-ledger persistence missing: {token}"
for token in ("SELECT s.*,","FROM ar_session s","SELECT a.*,"):
    assert token in importer,f"patient-ledger import missing: {token}"
print(f"Patient ledger provenance verified ({source_mode})")
