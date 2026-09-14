import csv
import hashlib
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent, Facility, Patient, ReportRun, User
from ..schemas import ReportCatalogItem, ReportRunCreate, ReportRunOut
from ..security import current_user, user_has_permission
from ..services.access import require_facility_access, require_warehouse_access
from ..services.reports import catalog, execute_report

router=APIRouter(prefix="/api/v1",tags=["reports"])


def authorize(user: User, permission: str) -> None:
    section,value,mode=permission.split(":")
    if not user_has_permission(user,section,value,mode): raise HTTPException(status_code=403,detail="Permission denied")


def spec_for(key: str) -> dict:
    item=next((item for item in catalog() if item["key"]==key),None)
    if not item: raise HTTPException(status_code=404,detail="Report not found")
    return item


def run_out(item: ReportRun) -> ReportRunOut:
    return ReportRunOut(**{key:getattr(item,key) for key in ("uuid","report_key","parameters","columns","rows","totals","row_count","checksum","created_at")})


@router.get("/reports",response_model=list[ReportCatalogItem])
def list_reports(user: User=Depends(current_user)):
    del user
    return catalog()


@router.post("/reports/{report_key}/runs",response_model=ReportRunOut,status_code=status.HTTP_201_CREATED)
def run_report(report_key: str,body: ReportRunCreate,db: Session=Depends(get_db),user: User=Depends(current_user)):
    spec=spec_for(report_key); authorize(user,spec["permission"]); parameters=body.model_dump(); public_parameters=body.model_dump(mode="json")
    if body.facility_uuid:
        facility=db.scalar(select(Facility).where(Facility.uuid==body.facility_uuid))
        if not facility: raise HTTPException(status_code=404,detail="Facility not found")
        require_facility_access(db,user,facility.id); parameters.update(_facility_id=facility.id,_legacy_facility_id=facility.legacy_facility_id)
    if body.warehouse_code: require_warehouse_access(db,user,body.warehouse_code)
    if body.patient_uuid:
        patient=db.scalar(select(Patient).where(Patient.uuid==body.patient_uuid,Patient.merged_into_id.is_(None)))
        if not patient: raise HTTPException(status_code=404,detail="Patient not found")
        parameters["_patient_id"]=patient.id
    columns,rows,totals=execute_report(db,user,report_key,parameters)
    canonical=json.dumps({"report":report_key,"parameters":public_parameters,"columns":columns,"rows":rows,"totals":totals},sort_keys=True,separators=(",",":"))
    item=ReportRun(report_key=report_key,parameters=public_parameters,columns=columns,rows=rows,totals=totals,row_count=len(rows),checksum=hashlib.sha256(canonical.encode()).hexdigest(),actor_id=user.id)
    db.add(item);db.flush();db.add(AuditEvent(actor_id=user.id,action="run",resource_type="report",resource_id=item.uuid,detail=report_key));db.commit();db.refresh(item);return run_out(item)


def stored_run(db: Session,user: User,run_uuid: str) -> ReportRun:
    item=db.scalar(select(ReportRun).where(ReportRun.uuid==run_uuid))
    if not item: raise HTTPException(status_code=404,detail="Report run not found")
    authorize(user,spec_for(item.report_key)["permission"])
    if item.actor_id != user.id and not user_has_permission(user,"admin","super","read"):
        raise HTTPException(status_code=403,detail="Report run belongs to another user")
    return item


@router.get("/report-runs/{run_uuid}",response_model=ReportRunOut)
def get_report_run(run_uuid: str,db: Session=Depends(get_db),user: User=Depends(current_user)):
    item=stored_run(db,user,run_uuid);db.add(AuditEvent(actor_id=user.id,action="read",resource_type="report",resource_id=item.uuid));db.commit();return run_out(item)


@router.get("/report-runs/{run_uuid}/export.csv")
def export_report_csv(run_uuid: str,db: Session=Depends(get_db),user: User=Depends(current_user)):
    item=stored_run(db,user,run_uuid);stream=io.StringIO(newline="");writer=csv.DictWriter(stream,fieldnames=item.columns,extrasaction="ignore");writer.writeheader();writer.writerows(item.rows)
    db.add(AuditEvent(actor_id=user.id,action="export",resource_type="report",resource_id=item.uuid,detail="csv"));db.commit()
    return Response(stream.getvalue(),media_type="text/csv",headers={"Content-Disposition":f'attachment; filename="{item.report_key}-{item.uuid}.csv"',"X-Report-Checksum":item.checksum})
