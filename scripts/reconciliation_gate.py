#!/usr/bin/env python3
"""Fail a cutover when a post-import dry run is not fully idempotent."""
import argparse
import hashlib
import json
from pathlib import Path


def evaluate(report:dict,allowed_rejections:dict[str,int]|None=None)->dict:
    allowed_rejections=allowed_rejections or {};failures=[];domains={}
    if report.get("mode")!="dry-run":failures.append("report mode must be dry-run")
    for name,value in sorted(report.items()):
        if not isinstance(value,dict) or not {"source","inserted","existing","rejected"}.issubset(value):continue
        source=int(value["source"]);inserted=int(value["inserted"]);existing=int(value["existing"]);rejected=int(value["rejected"]);allowed=allowed_rejections.get(name,0)
        domains[name]={"source":source,"existing":existing,"inserted":inserted,"rejected":rejected,"allowed_rejected":allowed}
        if source!=inserted+existing+rejected:failures.append(f"{name}: accounting mismatch")
        if inserted:failures.append(f"{name}: {inserted} rows would still be inserted")
        if rejected!=allowed:failures.append(f"{name}: rejected={rejected}, approved={allowed}")
    unknown=sorted(set(allowed_rejections)-set(domains))
    if unknown:failures.append("allowlist references unknown domains: "+", ".join(unknown))
    if not domains:failures.append("report contains no domain accounting")
    patient=report.get("patient_demographic_reconciliation",{})
    if not isinstance(patient,dict) or not patient:failures.append("patient demographic reconciliation is missing")
    if patient.get("missing_patient_pids"):failures.append("patient demographics: missing target patients")
    for section in ("typed_fields","legacy_payload_fields"):
        for field,result in patient.get(section,{}).items():
            if result.get("mismatch_pids"):failures.append(f"patient demographics {section}.{field}: mismatches")
            if result.get("records")!=result.get("matches"):failures.append(f"patient demographics {section}.{field}: record count mismatch")
    canonical=json.dumps(report,sort_keys=True,separators=(",",":"),default=str).encode()
    return {"status":"passed" if not failures else "failed","source_sha256":hashlib.sha256(canonical).hexdigest(),"domains":domains,"failures":failures}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("report",type=Path);parser.add_argument("--allow-rejected",action="append",default=[],metavar="DOMAIN=COUNT");parser.add_argument("--output",type=Path);args=parser.parse_args()
    allowed={}
    for item in args.allow_rejected:
        try:name,count=item.rsplit("=",1);allowed[name]=int(count)
        except ValueError:parser.error(f"invalid rejection allowance: {item}")
    evidence=evaluate(json.loads(args.report.read_text()),allowed);encoded=json.dumps(evidence,indent=2,sort_keys=True)+"\n"
    if args.output:args.output.write_text(encoded)
    else:print(encoded,end="")
    raise SystemExit(0 if evidence["status"]=="passed" else 1)


if __name__=="__main__":main()
