#!/usr/bin/env python3
"""Create checksummed release evidence only after every cutover gate passes."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess


def checked_json(path:Path,kind:str)->dict:
    document=json.loads(path.read_text())
    if document.get("status")!="passed":raise ValueError(f"{kind} evidence has not passed")
    return document


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--release",required=True);parser.add_argument("--reconciliation",type=Path,required=True);parser.add_argument("--acceptance",type=Path,required=True);parser.add_argument("--backup-manifest",type=Path,required=True);parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    reconciliation=checked_json(args.reconciliation,"reconciliation");acceptance=checked_json(args.acceptance,"acceptance");backup=json.loads(args.backup_manifest.read_text())
    if acceptance.get("release")!=args.release:raise ValueError("acceptance evidence belongs to a different release")
    if not backup.get("sha256") or not backup.get("schema_revision"):raise ValueError("backup manifest is incomplete")
    commit=subprocess.run(["git","rev-parse","HEAD"],check=True,capture_output=True,text=True).stdout.strip()
    evidence={"release":args.release,"commit":commit,"created_at":datetime.now(timezone.utc).isoformat(),"reconciliation_evidence_sha256":hashlib.sha256(args.reconciliation.read_bytes()).hexdigest(),"reconciliation_source_sha256":reconciliation["source_sha256"],"acceptance_sha256":hashlib.sha256(args.acceptance.read_bytes()).hexdigest(),"backup_manifest_sha256":hashlib.sha256(args.backup_manifest.read_bytes()).hexdigest(),"backup_sha256":backup["sha256"],"schema_revision":backup["schema_revision"]}
    evidence["manifest_sha256"]=hashlib.sha256(json.dumps(evidence,sort_keys=True,separators=(",",":")).encode()).hexdigest();args.output.write_text(json.dumps(evidence,indent=2,sort_keys=True)+"\n")


if __name__=="__main__":main()
