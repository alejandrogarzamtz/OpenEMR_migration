#!/usr/bin/env python3
"""Verify specialized modern form contracts against preserved OpenEMR sources."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.clinical_forms import PHYSICAL_EXAM_LINES, ROS_FIELDS, SOAP_FIELDS, STRUCTURED_FORMS  # noqa: E402


def digest(fields: set[str]) -> dict:
    ordered = "\n".join(sorted(fields)).encode()
    return {"fields": len(fields), "sha256": hashlib.sha256(ordered).hexdigest()}


def same(name: str, source: set[str], target: set[str]) -> None:
    missing, extra = sorted(source - target), sorted(target - source)
    if missing or extra:
        raise SystemExit(f"{name} mismatch: missing={missing}; extra={extra}")


def main() -> None:
    legacy_root = Path(os.environ.get("OPENRM_LEGACY_ROOT", ROOT / "openemr-legacy"))
    legacy = legacy_root / "interface" / "forms"
    targets = {"soap": set(SOAP_FIELDS), "ros": set(ROS_FIELDS), "physical_exam": set(PHYSICAL_EXAM_LINES)}
    targets.update({name: {field[0] for field in definition["fields"]} for name, definition in STRUCTURED_FORMS.items()})
    # Legacy progress-note signatures map to the append-only modern signature
    # model rather than accepting a caller-supplied signature timestamp.
    targets["note"].add("date_of_signature")
    expected = json.loads((ROOT / "docs" / "legacy-clinical-form-contract.json").read_text())
    evidence = {name: digest(fields) for name, fields in targets.items()}
    for name, result in evidence.items():
        if result != {key: expected[name][key] for key in ("fields", "sha256")}:
            raise SystemExit(f"{name} differs from versioned legacy contract: expected={expected[name]}; actual={result}")
    source_mode = "versioned-snapshot"
    if legacy.exists():
        soap_sql = (legacy / "soap" / "table.sql").read_text()
        ros_sql = (legacy / "ros" / "table.sql").read_text()
        physical_php = (legacy / "physical_exam" / "lines.php").read_text()
        same("SOAP", set(re.findall(r"`(subjective|objective|assessment|plan)`\s+text", soap_sql)), targets["soap"])
        same("ROS", set(re.findall(r"`([a-z0-9_]+)`\s+varchar\(3\)", ros_sql)), targets["ros"])
        same("physical exam", set(re.findall(r"'([A-Z][A-Z0-9]{2,7})'\s*=>\s*xl\(", physical_php)), targets["physical_exam"])
        common = {"id", "date", "pid", "user", "groupname", "authorized", "activity", "encounter"}
        source_locations = {name: legacy / name / "table.sql" for name in STRUCTURED_FORMS if name != "dictation"}
        source_locations["dictation"] = legacy_root / "sql" / "database.sql"
        for name, path in source_locations.items():
            sql = path.read_text()
            table = re.search(rf"CREATE TABLE(?: IF NOT EXISTS)?\s+`?form_{name}`?\s*\((.*?)\)\s*ENGINE", sql, re.I | re.S)
            if not table: raise SystemExit(f"Could not locate form_{name} in {path}")
            columns = set(re.findall(r"^\s*`?([A-Za-z][A-Za-z0-9_]*)`?\s+(?:bigint|int|tinyint|datetime|timestamp|date|varchar|text|longtext)\b", table.group(1), re.I | re.M)) - common
            same(name, columns, targets[name])
        source_mode = "preserved-tree-and-versioned-snapshot"
    print(json.dumps({"contracts": evidence, "verification_source": source_mode}, sort_keys=True))


if __name__ == "__main__":
    main()
