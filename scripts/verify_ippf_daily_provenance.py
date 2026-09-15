#!/usr/bin/env python3
"""Guard the preserved IPPF clinic daily-record contract."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1];contract=json.loads((root/"docs/legacy-ippf-daily-contract.json").read_text());legacy_path=root/"openemr-legacy/interface/reports/ippf_daily.php";source_mode="versioned-snapshot"
if legacy_path.is_file():
    legacy=legacy_path.read_text()
    for token in contract["required_tokens"]:assert token in legacy,f"legacy IPPF daily contract missing: {token}"
    assert hashlib.sha256(legacy_path.read_bytes()).hexdigest()==contract["report_sha256"]
    source_mode="preserved-tree-and-versioned-snapshot"
importer=(root/"backend/app/import_legacy.py").read_text();reports=(root/"backend/app/services/reports.py").read_text();frontend=(root/"frontend/src/features/reports/ReportWorkspace.tsx").read_text()
for text,token in ((importer,"lists_ippf_con"),(importer,'"contraceptive": "contraceptive"'),(reports,"def ippf_daily_report"),(reports,"IPPF_DAILY_METHODS"),(reports,'Charge.code_system=="MA"'),(reports,'"255004":"pap_smear"'),(frontend,"The daily record uses the From date")):assert token in text,f"modern IPPF daily contract missing: {token}"
print(f"IPPF daily provenance verified ({source_mode})")
