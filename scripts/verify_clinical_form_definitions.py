#!/usr/bin/env python3
"""Verify specialized modern form contracts against preserved OpenEMR sources."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.clinical_forms import PHYSICAL_EXAM_LINES, ROS_FIELDS, SOAP_FIELDS  # noqa: E402


def same(name: str, source: set[str], target: set[str]) -> dict:
    missing, extra = sorted(source - target), sorted(target - source)
    if missing or extra:
        raise SystemExit(f"{name} mismatch: missing={missing}; extra={extra}")
    ordered = "\n".join(sorted(source)).encode()
    return {"fields": len(source), "sha256": hashlib.sha256(ordered).hexdigest()}


def main() -> None:
    legacy = ROOT / "openemr-legacy" / "interface" / "forms"
    soap_sql = (legacy / "soap" / "table.sql").read_text()
    ros_sql = (legacy / "ros" / "table.sql").read_text()
    physical_php = (legacy / "physical_exam" / "lines.php").read_text()
    soap_source = set(re.findall(r"`(subjective|objective|assessment|plan)`\s+text", soap_sql))
    ros_source = set(re.findall(r"`([a-z0-9_]+)`\s+varchar\(3\)", ros_sql))
    physical_source = set(re.findall(r"'([A-Z][A-Z0-9]{2,7})'\s*=>\s*xl\(", physical_php))
    evidence = {
        "soap": same("SOAP", soap_source, set(SOAP_FIELDS)),
        "ros": same("ROS", ros_source, set(ROS_FIELDS)),
        "physical_exam": same("physical exam", physical_source, set(PHYSICAL_EXAM_LINES)),
    }
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()
