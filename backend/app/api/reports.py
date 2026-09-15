import csv
import hashlib
import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent, ClinicalItem, Facility, Patient, ReportRun, SyndromicSubmission, User
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


def hl7_escape(value) -> str:
    return str(value or "").replace("\\","\\E\\").replace("|","\\F\\").replace("^","\\S\\").replace("~","\\R\\").replace("&","\\T\\").replace("\r"," ").replace("\n"," ")


@router.get("/report-runs/{run_uuid}/export.hl7")
def export_syndromic_hl7(run_uuid: str,db: Session=Depends(get_db),user: User=Depends(current_user)):
    run=stored_run(db,user,run_uuid)
    if run.report_key!="non_reported":raise HTTPException(status_code=422,detail="HL7 export is only available for the non-reported syndromic report")
    facility_uuid=run.parameters.get("facility_uuid")
    if not facility_uuid:raise HTTPException(status_code=422,detail="A facility is required for syndromic HL7 export")
    facility=db.scalar(select(Facility).where(Facility.uuid==facility_uuid))
    if not facility:raise HTTPException(status_code=404,detail="Facility not found")
    require_facility_access(db,user,facility.id)
    if not facility.npi:raise HTTPException(status_code=422,detail="The sending facility requires an NPI")
    issue_uuids=[str(row["issue_uuid"]) for row in run.rows];items={item.uuid:item for item in db.scalars(select(ClinicalItem).where(ClinicalItem.uuid.in_(issue_uuids)))} if issue_uuids else {}
    submitted=set(db.scalars(select(SyndromicSubmission.clinical_item_id).where(SyndromicSubmission.clinical_item_id.in_([item.id for item in items.values()])))) if items else set()
    if submitted:raise HTTPException(status_code=409,detail="One or more issues in this snapshot were already submitted; run the report again")
    now=datetime.now(timezone.utc);stamp=now.strftime("%Y%m%d%H%M%S");filename=f"syn_sur_{now.strftime('%Y%m%d%H%M')}.hl7";segments=[]
    for index,row in enumerate(run.rows,1):
        item=items.get(str(row["issue_uuid"]))
        if not item:raise HTTPException(status_code=409,detail="A clinical issue in this snapshot no longer exists")
        control=f"{run.uuid[:8]}-{index}";sex={"male":"M","female":"F"}.get(str(row.get("sex") or "").lower(),"")
        marital={"married":"M","single":"S","divorced":"D","widowed":"W","separated":"A","domestic partner":"P"}.get(str(row.get("marital_status") or "").lower(),"")
        dob=str(row.get("date_of_birth") or "").replace("-","");begin=str(row.get("begin_date") or "").replace("-","").replace(":","").replace("T","")[:12]
        code=str(row.get("diagnosis") or "").split(":",1)[-1].replace(".","")
        segments.extend([
            f"MSH|^~\\&|OPENRM|{hl7_escape(facility.name)}^{hl7_escape(facility.npi)}^NPI|||{stamp}||ADT^A01^ADT_A01|{control}|P^T|2.5.1|||||||||PH_SS-NoAck^SS Sender^2.16.840.1.114222.4.10.3^ISO",
            f"EVN||{stamp}|||||{hl7_escape(facility.name)}^{hl7_escape(facility.npi)}^NPI",
            f"PID|1||{hl7_escape(row.get('legacy_patient_id'))}^^^^MR||^^^^^^~^^^^^^S||{dob}|{sex}|||{hl7_escape(row.get('address'))}|||{hl7_escape(row.get('phone_home'))}||||{marital}",
            f"PV1|1|||||||||||||||||{(stamp+'_'+str(row.get('legacy_patient_id') or ''))[:15]}^^^^VN|||||||||||||||||||||||||{begin}",
            f"OBX|1|CWE|8661-1^^LN||^^^^^^^^{hl7_escape(row.get('issue_title'))}||||||F",
            f"DG1|1||{hl7_escape(code)}^{hl7_escape(row.get('code_text'))}^I9CDX|||W",
        ])
        db.add(SyndromicSubmission(clinical_item_id=item.id,submitted_at=now,filename=filename,facility_id=facility.id,actor_id=user.id,message_control_id=control))
    content="\r".join(segments)+("\r" if segments else "")
    db.add(AuditEvent(actor_id=user.id,action="export",resource_type="report",resource_id=run.uuid,detail="hl7-syndromic"));db.commit()
    return Response(content,media_type="text/plain",headers={"Content-Disposition":f'attachment; filename="{filename}"',"X-Report-Checksum":run.checksum})
