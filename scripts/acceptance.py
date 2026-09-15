#!/usr/bin/env python3
"""Run non-destructive acceptance checks against a deployed OpenRM release."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request,urlopen


def get(url:str)->tuple[int,dict,dict,float]:
    started=time.perf_counter()
    with urlopen(Request(url,headers={"User-Agent":"OpenRM-Acceptance/1.0"}),timeout=10) as response:
        return response.status,json.loads(response.read()),dict(response.headers),time.perf_counter()-started


def run(base_url:str,release:str,requests:int)->dict:
    base=base_url.rstrip("/");failures=[]
    if not base.startswith("https://"):failures.append("acceptance requires an HTTPS base URL")
    try:
        status,ready,headers,_=get(base+"/health/ready")
        if status!=200 or ready.get("status")!="ready":failures.append("readiness failed")
        if ready.get("release")!=release:failures.append("deployed release does not match")
        required={"X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Cache-Control":"no-store","Strict-Transport-Security":None}
        for name,value in required.items():
            if name not in headers or value is not None and headers[name]!=value:failures.append(f"security header missing or invalid: {name}")
        _,openapi,_,_=get(base+"/openapi.json")
        if len(openapi.get("paths",{}))<100:failures.append("OpenAPI surface is unexpectedly incomplete")
    except Exception as exc:failures.append(f"contract check failed: {type(exc).__name__}")
    timings=[]
    try:
        with ThreadPoolExecutor(max_workers=min(20,requests)) as pool:
            for status,body,_,elapsed in pool.map(lambda _:get(base+"/health/live"),range(requests)):
                timings.append(elapsed)
                if status!=200 or body.get("status")!="live":failures.append("liveness load check failed")
    except Exception as exc:failures.append(f"load check failed: {type(exc).__name__}")
    timings.sort();p95=timings[min(len(timings)-1,int(len(timings)*.95))] if timings else None
    if p95 is not None and p95>2:failures.append("liveness p95 exceeded 2 seconds")
    evidence={"status":"passed" if not failures else "failed","release":release,"checked_at":datetime.now(timezone.utc).isoformat(),"requests":requests,"p95_seconds":p95,"failures":failures}
    evidence["sha256"]=hashlib.sha256(json.dumps(evidence,sort_keys=True,separators=(",",":")).encode()).hexdigest();return evidence


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--base-url",required=True);parser.add_argument("--release",required=True);parser.add_argument("--requests",type=int,default=100);parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    if args.requests<1:parser.error("requests must be positive")
    evidence=run(args.base_url,args.release,args.requests);args.output.write_text(json.dumps(evidence,indent=2,sort_keys=True)+"\n");raise SystemExit(0 if evidence["status"]=="passed" else 1)


if __name__=="__main__":main()
