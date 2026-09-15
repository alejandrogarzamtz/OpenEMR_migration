#!/usr/bin/env python3
"""Guard AMC tracking sources, persistence and transitions."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1];contract=json.loads((root/"docs/legacy-amc-tracking-contract.json").read_text());report=root/"openemr-legacy/interface/reports/amc_tracking.php";library=root/"openemr-legacy/library/amc.php";source_mode="versioned-snapshot"
if report.is_file() and library.is_file():
    combined=report.read_text()+library.read_text()
    for token in contract["required_tokens"]:assert token in combined,f"legacy AMC tracking contract missing: {token}"
    assert hashlib.sha256(report.read_bytes()).hexdigest()==contract["report_sha256"] and hashlib.sha256(library.read_bytes()).hexdigest()==contract["library_sha256"]
    source_mode="preserved-tree-and-versioned-snapshot"
models=(root/"backend/app/models.py").read_text();migration=(root/"backend/alembic/versions/20261101_0062_amc_tracking_events.py").read_text();importer=(root/"backend/app/import_legacy.py").read_text();reports=(root/"backend/app/services/reports.py").read_text();api=(root/"backend/app/api/reports.py").read_text();frontend=(root/"frontend/src/features/reports/ReportWorkspace.tsx").read_text()
for text,token in ((models,"class AmcTrackingEvent"),(migration,"amc_tracking_events"),(importer,"SELECT * FROM amc_misc_data"),(reports,"def amc_tracking_report"),(api,'/amc-tracking/{rule_id}/{source_uuid}'),(api,'resource_type="amc-tracking"'),(frontend,"Mark electronic")):assert token in text,f"modern AMC tracking contract missing: {token}"
print(f"AMC tracking provenance verified ({source_mode})")
