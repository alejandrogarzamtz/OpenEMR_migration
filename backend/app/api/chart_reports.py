from datetime import date, datetime, timezone
from hashlib import sha256
from html import escape
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent, CarePlan, Claim, ClinicalForm, ClinicalItem, Coverage, Document, Encounter, Immunization, LabOrder, LabResult, PatientAddress, PatientEmployment, PatientNameHistory, PatientRelatedPerson, PatientTelecom, Payer, Prescription, User, VitalSet
from ..security import patient_report_user, user_has_permission
from ..services.patients import patient_by_uuid
from ..services.patient_report_pdf import render_patient_report_pdf

router=APIRouter(prefix="/api/v1/patients",tags=["patient-reports"])
SECTION_KEYS=("demographics","addresses","telecommunications","previous-names","related-people","employment","clinical-items","prescriptions","immunizations","vitals","encounters","clinical-forms","care-plans","laboratory","documents","insurance","claims")


def text(value) -> str:
    if value is None or value == "": return "—"
    if isinstance(value,(date,datetime)): return escape(value.isoformat())
    return escape(str(value))


def rows(items:list[list[object]],headers:list[str]) -> str:
    head="".join(f"<th>{escape(header)}</th>" for header in headers)
    body="".join("<tr>"+"".join(f"<td>{text(value)}</td>" for value in item)+"</tr>" for item in items)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body or f'<tr><td colspan="{len(headers)}">No records</td></tr>'}</tbody></table>"


def in_period(column,start:date|None,end:date|None):
    conditions=[]
    if start:conditions.append(column>=datetime.combine(start,datetime.min.time(),tzinfo=timezone.utc))
    if end:conditions.append(column<datetime.combine(end,datetime.max.time(),tzinfo=timezone.utc))
    return conditions


def selected_sections(value:str|None)->set[str]:
    from fastapi import HTTPException
    if value is None:return set(SECTION_KEYS)
    selected={item.strip() for item in value.split(",") if item.strip()};invalid=selected-set(SECTION_KEYS)
    if invalid:raise HTTPException(status_code=422,detail=f"Unknown report sections: {', '.join(sorted(invalid))}")
    if not selected:raise HTTPException(status_code=422,detail="At least one report section is required")
    return selected


def build_patient_report(patient_uuid:str,start:date|None,end:date|None,sections_selected:set[str],db:Session,user:User,output_format:str):
    patient=patient_by_uuid(db,patient_uuid)
    if start and end and start>end: from fastapi import HTTPException; raise HTTPException(status_code=422,detail="Report start date must not be after end date")
    can_demo=user_has_permission(user,"patients","demo");can_med=user_has_permission(user,"patients","med");can_docs=user_has_permission(user,"patients","docs");can_bill=user_has_permission(user,"acct","bill")
    addresses=list(db.scalars(select(PatientAddress).where(PatientAddress.patient_id==patient.id,PatientAddress.active.is_(True)).order_by(PatientAddress.is_primary.desc(),PatientAddress.priority))) if can_demo else []
    telecoms=list(db.scalars(select(PatientTelecom).where(PatientTelecom.patient_id==patient.id,PatientTelecom.active.is_(True)).order_by(PatientTelecom.is_primary.desc(),PatientTelecom.rank))) if can_demo else []
    names=list(db.scalars(select(PatientNameHistory).where(PatientNameHistory.patient_id==patient.id).order_by(PatientNameHistory.period_end.desc()))) if can_demo else []
    related=list(db.scalars(select(PatientRelatedPerson).where(PatientRelatedPerson.patient_id==patient.id,PatientRelatedPerson.active.is_(True)).order_by(PatientRelatedPerson.priority))) if can_demo else []
    employments=list(db.scalars(select(PatientEmployment).where(PatientEmployment.patient_id==patient.id).order_by(PatientEmployment.starts_at.desc()))) if can_demo else []
    items=list(db.scalars(select(ClinicalItem).where(ClinicalItem.patient_id==patient.id).order_by(ClinicalItem.category,ClinicalItem.created_at.desc()))) if can_med else []
    prescriptions=list(db.scalars(select(Prescription).where(Prescription.patient_id==patient.id).order_by(Prescription.prescribed_at.desc()))) if can_med else []
    immunizations=list(db.scalars(select(Immunization).where(Immunization.patient_id==patient.id,*in_period(Immunization.administered_at,start,end)).order_by(Immunization.administered_at.desc()))) if can_med else []
    vitals=list(db.scalars(select(VitalSet).where(VitalSet.patient_id==patient.id,*in_period(VitalSet.observed_at,start,end)).order_by(VitalSet.observed_at.desc()))) if can_med else []
    encounters=list(db.scalars(select(Encounter).where(Encounter.patient_id==patient.id,*in_period(Encounter.occurred_at,start,end)).order_by(Encounter.occurred_at.desc()))) if can_med else []
    encounter_ids=[item.id for item in encounters]
    forms=list(db.scalars(select(ClinicalForm).where(ClinicalForm.patient_id==patient.id,ClinicalForm.encounter_id.in_(encounter_ids)).order_by(ClinicalForm.authored_at.desc()))) if encounter_ids else []
    care_plans=list(db.scalars(select(CarePlan).where(CarePlan.patient_id==patient.id,CarePlan.encounter_id.in_(encounter_ids)).order_by(CarePlan.recorded_at.desc()))) if encounter_ids else []
    labs=db.execute(select(LabOrder,LabResult).outerjoin(LabResult).where(LabOrder.patient_id==patient.id,*in_period(LabOrder.ordered_at,start,end)).order_by(LabOrder.ordered_at.desc(),LabResult.observed_at.desc())).all() if can_med else []
    documents=list(db.scalars(select(Document).where(Document.patient_id==patient.id).order_by(Document.uploaded_at.desc()))) if can_docs else []
    coverages=db.execute(select(Coverage,Payer).join(Payer).where(Coverage.patient_id==patient.id).order_by(Coverage.priority)).all() if can_bill else []
    claims=list(db.scalars(select(Claim).where(Claim.patient_id==patient.id,*in_period(Claim.created_at,start,end)).order_by(Claim.created_at.desc()))) if can_bill else []
    generated=datetime.now(timezone.utc)
    evidence={"patient_uuid":patient.uuid,"generated_at":generated,"generated_by":user.uuid,"period":{"start":start,"end":end},"sections":sorted(sections_selected),"section_access":{"demographics":can_demo,"medical":can_med,"documents":can_docs,"billing":can_bill},"counts":{"addresses":len(addresses),"telecoms":len(telecoms),"previous_names":len(names),"related_people":len(related),"employments":len(employments),"clinical_items":len(items),"prescriptions":len(prescriptions),"immunizations":len(immunizations),"vitals":len(vitals),"encounters":len(encounters),"forms":len(forms),"care_plans":len(care_plans),"lab_rows":len(labs),"documents":len(documents),"coverages":len(coverages),"claims":len(claims)}}
    digest=sha256(json.dumps(evidence,sort_keys=True,default=str).encode()).hexdigest()
    restricted="<p>Restricted by section ACL.</p>"
    sections=[
      ("Demographics",rows([[patient.first_name,patient.middle_name,patient.last_name,patient.date_of_birth,patient.sex,patient.gender_identity,patient.email,patient.phone]], ["First","Middle","Last","DOB","Sex","Gender identity","Email","Phone"])),
      ("Addresses",rows([[x.use,x.line1,x.line2,x.city,x.state,x.postal_code,x.country_code] for x in addresses],["Use","Line 1","Line 2","City","State","Postal code","Country"])),
      ("Telecommunications",rows([[x.system,x.use,x.value,"Yes" if x.is_primary else "No"] for x in telecoms],["System","Use","Value","Primary"])),
      ("Previous names",rows([[x.use," ".join(filter(None,(x.first_name,x.middle_name,x.last_name))),x.period_start,x.period_end,x.reason] for x in names],["Use","Name","From","Until","Reason"])),
      ("Related people",rows([[f"{x.first_name} {x.last_name}",x.relationship_code,x.role_code,x.phone,x.email] for x in related],["Name","Relationship","Role","Phone","Email"])),
      ("Employment",rows([[x.employer_name,x.occupation_code,x.industry_code,x.starts_at,x.ends_at] for x in employments],["Employer","Occupation","Industry","From","Until"])),
      ("Problems, allergies, and medications",rows([[x.category,x.title,x.code_system,x.code,x.status,x.reaction or x.dosage] for x in items],["Category","Description","Code system","Code","Status","Details"])),
      ("Prescriptions",rows([[x.prescribed_at,x.drug_name,x.rxnorm_code,x.dosage_instructions,x.quantity,x.refills,x.status] for x in prescriptions],["Prescribed","Drug","RxNorm","Instructions","Quantity","Refills","Status"])),
      ("Immunizations",rows([[x.administered_at,x.vaccine_name,x.cvx_code,x.lot_number,x.status] for x in immunizations],["Administered","Vaccine","CVX","Lot","Status"])),
      ("Vital signs",rows([[x.observed_at,x.systolic,x.diastolic,x.heart_rate,x.oxygen_saturation,x.bmi] for x in vitals],["Observed","Systolic","Diastolic","Pulse","SpO2","BMI"])),
      ("Encounters",rows([[x.occurred_at,x.type,x.status,x.chief_complaint,x.clinical_note] for x in encounters],["Date","Type","Status","Chief complaint","Clinical note"])),
      ("Clinical forms",rows([[x.authored_at,x.form_type,x.title,x.status,json.dumps(x.content,sort_keys=True,default=str)] for x in forms],["Authored","Type","Title","Status","Content"])),
      ("Care plans",rows([[x.recorded_at,x.code,x.code_text,x.description,x.plan_type,x.status,x.target_date,x.ends_at] for x in care_plans],["Recorded","Code","Code text","Description","Type","Status","Target","Ends"])),
      ("Laboratory and procedures",rows([[order.ordered_at,order.code,order.name,order.status,result.value if result else None,result.unit if result else None,result.status if result else None] for order,result in labs],["Ordered","Code","Name","Order status","Result","Unit","Result status"])),
      ("Documents",rows([[x.uploaded_at,x.name,x.mime_type,x.sha256] for x in documents],["Uploaded","Name","MIME type","SHA-256"])),
      ("Insurance",rows([[coverage.priority,payer.name,coverage.plan_name,coverage.policy_number,coverage.starts_on,coverage.ends_on] for coverage,payer in coverages],["Priority","Payer","Plan","Policy","Starts","Ends"])),
      ("Claims",rows([[x.created_at,x.status,x.total,x.submitted_at] for x in claims],["Created","Status","Total","Submitted"])),
    ]
    for indexes,allowed in (((1,2,3,4,5),can_demo),((6,7,8,9,10,11,12,13),can_med),((14,),can_docs),((15,16),can_bill)):
        if not allowed:
            for index in indexes:sections[index]=(sections[index][0],restricted)
    section_html="".join(f"<section><h2>{title}</h2>{content}</section>" for key,(title,content) in zip(SECTION_KEYS,sections) if key in sections_selected)
    html=f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Patient report - {text(patient.first_name)} {text(patient.last_name)}</title><style>@page{{margin:14mm}}body{{font:12px system-ui,sans-serif;color:#17201e}}header{{border-bottom:2px solid #176b5b;margin-bottom:18px}}h1{{margin-bottom:4px}}h2{{font-size:15px;color:#176b5b;margin-top:20px;break-after:avoid}}table{{width:100%;border-collapse:collapse;table-layout:fixed}}th,td{{border:1px solid #ccd7d3;padding:5px;text-align:left;vertical-align:top;overflow-wrap:anywhere}}th{{background:#eef5f2}}tr{{break-inside:avoid}}.meta{{color:#52615e;font-size:10px}}</style></head><body><header><h1>Patient report</h1><p>{text(patient.first_name)} {text(patient.middle_name)} {text(patient.last_name)} · DOB {text(patient.date_of_birth)} · ID {text(patient.uuid)}</p><p class="meta">Generated {text(generated)} · Period {text(start)} to {text(end)} · Evidence SHA-256 {digest}</p></header>{section_html}</body></html>"""
    db.add(AuditEvent(actor_id=user.id,action="export",resource_type="patient_report",resource_id=patient.uuid,detail=f"format={output_format}; sha256={digest}; start={start}; end={end}; counts={evidence['counts']}"));db.commit()
    common={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff","X-Report-SHA256":digest}
    if output_format=="pdf":return Response(render_patient_report_pdf(html),media_type="application/pdf",headers=common|{"Content-Disposition":f'attachment; filename="patient-{patient.uuid}-report.pdf"'})
    return Response(html,media_type="text/html",headers=common|{"Content-Disposition":f'inline; filename="patient-{patient.uuid}-report.html"',"Content-Security-Policy":"default-src 'none'; style-src 'unsafe-inline'"})


@router.get("/{patient_uuid}/report.html")
def printable_patient_report(patient_uuid:str,start:date|None=Query(default=None),end:date|None=Query(default=None),sections:str|None=Query(default=None),db:Session=Depends(get_db),user:User=Depends(patient_report_user)):
    return build_patient_report(patient_uuid,start,end,selected_sections(sections),db,user,"html")


@router.get("/{patient_uuid}/report.pdf")
def patient_report_pdf(patient_uuid:str,start:date|None=Query(default=None),end:date|None=Query(default=None),sections:str|None=Query(default=None),db:Session=Depends(get_db),user:User=Depends(patient_report_user)):
    return build_patient_report(patient_uuid,start,end,selected_sections(sections),db,user,"pdf")
