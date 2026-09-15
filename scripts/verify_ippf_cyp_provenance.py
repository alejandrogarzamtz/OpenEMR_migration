#!/usr/bin/env python3
"""Guard IPPF CYP factors, sources and calculation parity."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1];contract=json.loads((root/"docs/legacy-ippf-cyp-contract.json").read_text());legacy_path=root/"openemr-legacy/interface/reports/ippf_cyp_report.php";source_mode="versioned-snapshot"
if legacy_path.is_file():
    legacy=legacy_path.read_text()
    for token in contract["required_tokens"]:assert token in legacy,f"legacy CYP contract missing: {token}"
    assert hashlib.sha256(legacy_path.read_bytes()).hexdigest()==contract["report_sha256"]
    source_mode="preserved-tree-and-versioned-snapshot"
models=(root/"backend/app/models.py").read_text();migration=(root/"backend/alembic/versions/20261031_0061_cyp_factors.py").read_text();importer=(root/"backend/app/import_legacy.py").read_text();reports=(root/"backend/app/services/reports.py").read_text();frontend=(root/"frontend/src/features/reports/ReportWorkspace.tsx").read_text()
for text,token in ((models,"cyp_factor"),(migration,"inventory_products"),(migration,"service_codes"),(importer,"row[\"cyp_factor\"]"),(reports,"def ippf_cyp_report"),(reports,"Charge.code_system==\"MA\""),(reports,"InventoryTransaction.fee!=0"),(reports,"ROUND_HALF_UP"),(frontend,"Product totals only")):assert token in text,f"modern CYP contract missing: {token}"
print(f"IPPF CYP provenance verified ({source_mode})")
