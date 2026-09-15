#!/usr/bin/env python3
"""Guard the six-source 2026 ONC real-world-testing evidence contract."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    importer=(ROOT/"backend/app/import_legacy.py").read_text()
    for token in ("SELECT * FROM ccda ORDER BY id","SELECT * FROM direct_message_log WHERE status IN ('S','R') ORDER BY id","SELECT * FROM audit_master WHERE is_qrda_document = 1 ORDER BY id","SELECT * FROM log WHERE event = 'qrda3-export' AND success = 1 ORDER BY id","SELECT * FROM api_log ORDER BY id","SELECT * FROM ehi_export_job_tasks WHERE status = 'completed' ORDER BY ehi_task_id"):
        if token not in importer:raise SystemExit(f"RWT source import missing: {token}")
    reports=(ROOT/"backend/app/services/reports.py").read_text()
    for token in ("datetime(2026,4,1","datetime(2026,10,1",'"ccda-generated"','"direct-sent"','"direct-received"','"qrda-import"','"qrda3-export"','"api-request"','"ehi-export"'):
        if token not in reports:raise SystemExit(f"RWT metric contract missing: {token}")
    main=(ROOT/"backend/app/main.py").read_text()
    if '@app.middleware("http")' not in main or 'metric_type="api-request"' not in main or 'response.status_code<400' not in main:raise SystemExit("modern API analytics recording missing")
    print("2026 real-world-testing provenance contract verified")


if __name__=="__main__":main()
