#!/usr/bin/env python3
"""Guard the multidimensional IPPF statistics contract."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1];contract=json.loads((root/"docs/legacy-ippf-statistics-contract.json").read_text());legacy_path=root/"openemr-legacy/interface/reports/ippf_statistics.php";source_mode="versioned-snapshot"
if legacy_path.is_file():
    legacy=legacy_path.read_text()
    for token in contract["required_tokens"]:assert token in legacy,f"legacy IPPF statistics contract missing: {token}"
    assert hashlib.sha256(legacy_path.read_bytes()).hexdigest()==contract["report_sha256"]
    source_mode="preserved-tree-and-versioned-snapshot"
schemas=(root/"backend/app/schemas.py").read_text();reports=(root/"backend/app/services/reports.py").read_text();frontend=(root/"frontend/src/features/reports/ReportWorkspace.tsx").read_text()
for text,token in ((schemas,"ippf_report_type"),(schemas,"ippf_columns"),(reports,"def ippf_statistics_report"),(reports,"_ippf_contraceptive_method"),(reports,"_ippf_abortion_method"),(reports,"referral_definitions"),(reports,'"age_0_10"'),(frontend,"Member Association"),(frontend,"External referral follow-ups")):assert token in text,f"modern IPPF statistics contract missing: {token}"
print(f"IPPF statistics provenance verified ({source_mode})")
