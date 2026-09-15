#!/usr/bin/env python3
"""Guard the saved AMC calculation and itemized-patient contract."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1];contract=json.loads((root/"docs/legacy-amc-full-report-contract.json").read_text());legacy=root/contract["source"];source_mode="versioned-snapshot"
if legacy.is_file():
    content=legacy.read_text()
    for token in contract["required_tokens"]:assert token in content,f"legacy AMC full-report contract missing: {token}"
    assert hashlib.sha256(legacy.read_bytes()).hexdigest()==contract["sha256"]
    source_mode="preserved-tree-and-versioned-snapshot"
models=(root/"backend/app/models.py").read_text();migration=(root/"backend/alembic/versions/20261102_0063_quality_measure_reports.py").read_text();importer=(root/"backend/app/import_legacy.py").read_text();service=(root/"backend/app/services/quality_reports.py").read_text();frontend=(root/"frontend/src/features/reports/ReportWorkspace.tsx").read_text()
for text,token in ((models,"class QualityMeasureReport"),(models,"class QualityMeasureItem"),(migration,"quality_measure_items"),(importer,"SELECT report_id,field_id,field_value FROM report_results"),(importer,"SELECT * FROM report_itemized"),(service,"def quality_report"),(service,"eligible-passed-excluded"),(frontend,"Saved AMC report UUID")):assert token in text,f"modern AMC full-report contract missing: {token}"
print(f"AMC full-report provenance verified ({source_mode})")
