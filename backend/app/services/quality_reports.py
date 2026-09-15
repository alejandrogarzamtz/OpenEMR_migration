"""Read model for preserved legacy CQM and AMC calculations."""
import json

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Patient, QualityMeasureItem, QualityMeasureReport


def _number(value, default=0):
    try:return int(value)
    except (TypeError,ValueError):return default


def _selected(db:Session,params:dict,*,require_amc=False):
    uuid=params.get("quality_report_uuid")
    if not uuid:return None
    report=db.scalar(select(QualityMeasureReport).where(QualityMeasureReport.uuid==uuid))
    if not report:raise HTTPException(status_code=404,detail="Quality measure report not found")
    if require_amc and report.report_type in {"standard","cqm","cqm_2011","cqm_2014"}:raise HTTPException(status_code=422,detail="The selected report is not an AMC certification report")
    return report


def _summary_rows(report:QualityMeasureReport):
    rows=[];main_pass_filter=0
    for index,raw in enumerate(report.data):
        if not isinstance(raw,dict):continue
        kind="main" if "is_main" in raw else "sub" if "is_sub" in raw else "plan" if "is_plan" in raw else "result"
        eligible=_number(raw.get("pass_filter"));passed=_number(raw.get("pass_target"));excluded=_number(raw.get("excluded"))
        if kind=="main":main_pass_filter=eligible
        failed=(main_pass_filter-passed) if kind=="sub" else (eligible-passed if report.report_type=="standard" else eligible-passed-excluded) if kind=="main" else None
        display=raw.get("display_field") or raw.get("title") or raw.get("id")
        if kind=="sub":display=display or ": ".join(filter(None,(str(raw.get("action_category") or ""),str(raw.get("action_item") or ""))))
        rows.append({"measure_index":index,"measure_type":kind,"measure_id":raw.get("id"),"display_field":display,"total_patients":_number(raw.get("total_patients")),"eligible":eligible,"excluded":excluded,"passed":passed,"failed":failed,"percentage":raw.get("percentage"),"itemized_test_id":raw.get("itemized_test_id")})
    return rows


def quality_report(db:Session,params:dict,*,full_amc=False):
    report=_selected(db,params,require_amc=full_amc)
    if report is None:
        if full_amc:raise HTTPException(status_code=422,detail="quality_report_uuid is required")
        query=select(QualityMeasureReport)
        if params.get("quality_report_type"):query=query.where(QualityMeasureReport.report_type==params["quality_report_type"])
        start,end=params.get("_quality_start"),params.get("_quality_end")
        if start:query=query.where(QualityMeasureReport.reported_at>=start)
        if end:query=query.where(QualityMeasureReport.reported_at<end)
        records=list(db.scalars(query.order_by(QualityMeasureReport.reported_at.desc().nullslast(),QualityMeasureReport.legacy_report_id.desc())))
        counts=dict(db.execute(select(QualityMeasureItem.report_id,func.count()).where(QualityMeasureItem.report_id.in_([x.id for x in records])).group_by(QualityMeasureItem.report_id)).all()) if records else {}
        columns=["quality_report_uuid","legacy_report_id","report_type","status","reported_at","period_start","period_end","provider","plan","measure_count","itemized_count"]
        rows=[{"quality_report_uuid":x.uuid,"legacy_report_id":x.legacy_report_id,"report_type":x.report_type,"status":x.status,"reported_at":x.reported_at.isoformat() if x.reported_at else None,"period_start":x.period_start.isoformat() if x.period_start else None,"period_end":x.period_end.isoformat() if x.period_end else None,"provider":x.provider,"plan":x.plan,"measure_count":len(x.data),"itemized_count":counts.get(x.id,0)} for x in records]
        return columns,rows,{"reports":len(rows),"measures":sum(x["measure_count"] for x in rows),"itemized_results":sum(x["itemized_count"] for x in rows)}
    summaries=_summary_rows(report);base_columns=["measure_index","measure_type","measure_id","display_field","total_patients","eligible","excluded","passed","failed","percentage","itemized_test_id"]
    if not full_amc or not params.get("include_details",True):return base_columns,summaries,{"legacy_report_id":report.legacy_report_id,"report_type":report.report_type,"measures":len(summaries),"itemized_results":0}
    summary_by_test={row["itemized_test_id"]:row for row in summaries if row["itemized_test_id"] is not None};rows=[];labels={0:"failed",1:"passed",2:"excluded",3:"not-applicable"}
    query=select(QualityMeasureItem,Patient).outerjoin(Patient,Patient.id==QualityMeasureItem.patient_id).where(QualityMeasureItem.report_id==report.id).order_by(QualityMeasureItem.sequence)
    for item,patient in db.execute(query):
        summary=summary_by_test.get(item.itemized_test_id,{key:None for key in base_columns})
        rows.append(summary|{"item_sequence":item.sequence,"result":labels.get(item.pass_status,str(item.pass_status)),"numerator_label":item.numerator_label,"patient_uuid":patient.uuid if patient else None,"legacy_patient_id":item.legacy_patient_id,"patient":(" ".join(filter(None,(patient.first_name,patient.middle_name,patient.last_name))) if patient else None),"date_of_birth":patient.date_of_birth.isoformat() if patient else None,"sex":patient.sex if patient else None,"rule_id":item.rule_id,"item_details":json.dumps(item.item_details,sort_keys=True,separators=(",",":")) if item.item_details is not None else None})
    columns=base_columns+["item_sequence","result","numerator_label","patient_uuid","legacy_patient_id","patient","date_of_birth","sex","rule_id","item_details"]
    return columns,rows,{"legacy_report_id":report.legacy_report_id,"report_type":report.report_type,"measures":len(summaries),"itemized_results":len(rows),"passed":sum(x["result"]=="passed" for x in rows),"failed":sum(x["result"]=="failed" for x in rows),"excluded":sum(x["result"]=="excluded" for x in rows)}
