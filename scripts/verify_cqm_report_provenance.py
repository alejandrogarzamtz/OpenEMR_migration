#!/usr/bin/env python3
"""Guard the preserved CQM report-selection and result contract."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1];contract=json.loads((root/"docs/legacy-cqm-report-contract.json").read_text());legacy=root/contract["source"];source_mode="versioned-snapshot"
if legacy.is_file():
    content=legacy.read_text()
    for token in contract["required_tokens"]:assert token in content,f"legacy CQM report contract missing: {token}"
    assert hashlib.sha256(legacy.read_bytes()).hexdigest()==contract["sha256"]
    source_mode="preserved-tree-and-versioned-snapshot"
reports=(root/"backend/app/services/reports.py").read_text();quality=(root/"backend/app/services/quality_reports.py").read_text();schemas=(root/"backend/app/schemas.py").read_text();frontend=(root/"frontend/src/features/reports/ReportWorkspace.tsx").read_text()
for text,token in ((reports,'"cqm"'),(reports,'if key == "cqm"'),(quality,"quality_report_type"),(quality,"QualityMeasureReport.reported_at"),(schemas,"quality_report_uuid"),(frontend,"Leave blank to list saved reports")):assert token in text,f"modern CQM report contract missing: {token}"
print(f"CQM report provenance verified ({source_mode})")
