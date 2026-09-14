#!/usr/bin/env python3
"""Guard the legacy patient-provider-facility assignment contract."""
from pathlib import Path
import os
import re

ROOT=Path(__file__).resolve().parents[1]


def main():
    importer=(ROOT/"backend/app/import_legacy.py").read_text()
    for token in ('("providerID","primary")','("ref_providerID","referring")','user_row["facility_id"]','legacy_assignment_key==key'):
        if token not in importer:raise SystemExit(f"assignment importer contract missing: {token}")
    report=(ROOT/"openemr-legacy/interface/reports/clinical_reports.php")
    legacy_root=Path(os.environ.get("OPENRM_LEGACY_ROOT",ROOT/"openemr-legacy"))
    report=legacy_root/"interface/reports/clinical_reports.php"
    if report.is_file():
        source=report.read_text()
        if not re.search(r"users\s+as\s+u\s+on\s+u\.id\s*=\s*pd\.providerid",source,re.I):raise SystemExit("clinical report provider join changed")
        if not re.search(r"facility\s+as\s+f\s+on\s+f\.id\s*=\s*u\.facility_id",source,re.I):raise SystemExit("clinical report facility join changed")
    print("patient provider assignment contract verified")


if __name__=="__main__":main()
