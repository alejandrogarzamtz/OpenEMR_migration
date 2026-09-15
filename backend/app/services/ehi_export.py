"""Patient C-CDA and electronic-health-information export generation."""
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Base
from ..models import ClinicalItem, Encounter, Immunization, LabOrder, LabResult, Patient, Prescription

CDA="urn:hl7-org:v3"
ET.register_namespace("",CDA)


def q(name:str)->str:return f"{{{CDA}}}{name}"


def _text(parent,name,value):
    child=ET.SubElement(parent,q(name));child.text=str(value or "");return child


def _section(component,title,code,rows):
    templates={"11450-4":"2.16.840.1.113883.10.20.22.2.5.1","48765-2":"2.16.840.1.113883.10.20.22.2.6.1","10160-0":"2.16.840.1.113883.10.20.22.2.1.1","11369-6":"2.16.840.1.113883.10.20.22.2.2.1","46240-8":"2.16.840.1.113883.10.20.22.2.22.1","30954-2":"2.16.840.1.113883.10.20.22.2.3.1"}
    section=ET.SubElement(ET.SubElement(component,q("component")),q("section"));ET.SubElement(section,q("templateId"),root=templates[code]);ET.SubElement(section,q("code"),code=code,codeSystem="2.16.840.1.113883.6.1");_text(section,"title",title)
    table=ET.SubElement(ET.SubElement(section,q("text")),q("table"));body=ET.SubElement(table,q("tbody"))
    if not rows:rows=[("No information available","")]
    for label,value in rows:
        tr=ET.SubElement(body,q("tr"));_text(tr,"td",label);_text(tr,"td",value)
    return section


def ccda_document(db:Session,patient:Patient)->bytes:
    timestamp=datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S+0000");root=ET.Element(q("ClinicalDocument"));ET.SubElement(root,q("realmCode"),code="US");ET.SubElement(root,q("typeId"),root="2.16.840.1.113883.1.3",extension="POCD_HD000040");ET.SubElement(root,q("templateId"),root="2.16.840.1.113883.10.20.22.1.1",extension="2015-08-01");ET.SubElement(root,q("templateId"),root="2.16.840.1.113883.10.20.22.1.2",extension="2015-08-01");ET.SubElement(root,q("id"),root=patient.uuid);ET.SubElement(root,q("code"),code="34133-9",codeSystem="2.16.840.1.113883.6.1",displayName="Summarization of Episode Note");_text(root,"title","OpenRM Patient Clinical Summary");ET.SubElement(root,q("effectiveTime"),value=timestamp);ET.SubElement(root,q("confidentialityCode"),code="N",codeSystem="2.16.840.1.113883.5.25");ET.SubElement(root,q("languageCode"),code=patient.language or "en-US")
    record=ET.SubElement(ET.SubElement(root,q("recordTarget")),q("patientRole"));ET.SubElement(record,q("id"),root="urn:openrm:patient",extension=patient.uuid)
    if patient.address_line_1:
        address=ET.SubElement(record,q("addr"),use="HP");_text(address,"streetAddressLine",patient.address_line_1);_text(address,"city",patient.city);_text(address,"state",patient.state);_text(address,"postalCode",patient.postal_code);_text(address,"country",patient.country_code)
    patient_node=ET.SubElement(record,q("patient"));name=ET.SubElement(patient_node,q("name"));_text(name,"given",patient.first_name);_text(name,"given",patient.middle_name);_text(name,"family",patient.last_name);ET.SubElement(patient_node,q("administrativeGenderCode"),code={"male":"M","female":"F"}.get(patient.sex.lower(),"UN"));ET.SubElement(patient_node,q("birthTime"),value=patient.date_of_birth.strftime("%Y%m%d"))
    author=ET.SubElement(root,q("author"));ET.SubElement(author,q("time"),value=timestamp);assigned=ET.SubElement(author,q("assignedAuthor"));ET.SubElement(assigned,q("id"),root="urn:openrm:system",extension="OpenRM")
    custodian=ET.SubElement(root,q("custodian"));assigned_custodian=ET.SubElement(custodian,q("assignedCustodian"));organization=ET.SubElement(assigned_custodian,q("representedCustodianOrganization"));ET.SubElement(organization,q("id"),root="urn:openrm:organization",extension="OpenRM");_text(organization,"name","OpenRM")
    body=ET.SubElement(ET.SubElement(root,q("component")),q("structuredBody"))
    items=list(db.scalars(select(ClinicalItem).where(ClinicalItem.patient_id==patient.id)))
    _section(body,"Problems","11450-4",[(x.title,x.status) for x in items if x.category=="problem"])
    _section(body,"Allergies","48765-2",[(x.title,x.reaction or x.status) for x in items if x.category=="allergy"])
    prescriptions=list(db.scalars(select(Prescription).where(Prescription.patient_id==patient.id)));_section(body,"Medications","10160-0",[(x.medication,x.dosage or x.status) for x in prescriptions])
    immunizations=list(db.scalars(select(Immunization).where(Immunization.patient_id==patient.id)));_section(body,"Immunizations","11369-6",[(x.vaccine_name,x.administered_on.isoformat()) for x in immunizations])
    encounters=list(db.scalars(select(Encounter).where(Encounter.patient_id==patient.id)));_section(body,"Encounters","46240-8",[(x.type,x.occurred_at.isoformat()) for x in encounters])
    results=db.execute(select(LabResult).join(LabOrder).where(LabOrder.patient_id==patient.id)).scalars().all();_section(body,"Results","30954-2",[(x.name,f"{x.value} {x.unit or ''}".strip()) for x in results])
    return ET.tostring(root,encoding="utf-8",xml_declaration=True)


def _json_value(value):
    if isinstance(value,(date,datetime)):return value.isoformat()
    if isinstance(value,Decimal):return str(value)
    if isinstance(value,bytes):return {"encoding":"omitted-binary","size":len(value),"sha256":sha256(value).hexdigest()}
    return value


def designated_record_set(db:Session,patient:Patient)->dict[str,list[dict]]:
    """Follow the database FK graph outward from one patient without crossing into other patients."""
    selected={"patients":{patient.id}};export={"patients":[{key:_json_value(value) for key,value in dict(db.execute(Base.metadata.tables["patients"].select().where(Base.metadata.tables["patients"].c.id==patient.id)).mappings().one()).items()}]}
    changed=True
    while changed:
        changed=False
        for table in Base.metadata.sorted_tables:
            if table.name=="patients":continue
            predicates=[]
            for column in table.c:
                for foreign_key in column.foreign_keys:
                    target=foreign_key.column.table.name
                    if target in selected:predicates.append(column.in_(selected[target]))
            if not predicates:continue
            from sqlalchemy import or_
            rows=[dict(row) for row in db.execute(table.select().where(or_(*predicates))).mappings()]
            serialized=[{key:_json_value(value) for key,value in row.items()} for row in rows]
            existing={json.dumps(row,sort_keys=True,separators=(",",":")) for row in export.get(table.name,[])}
            additions=[row for row in serialized if json.dumps(row,sort_keys=True,separators=(",",":")) not in existing]
            if additions:
                export.setdefault(table.name,[]).extend(additions)
                if "id" in table.c:selected.setdefault(table.name,set()).update(row["id"] for row in rows)
                changed=True
    return export


def ehi_zip(db:Session,patient:Patient)->bytes:
    files={"ccda.xml":ccda_document(db,patient),"designated-record-set.json":json.dumps(designated_record_set(db,patient),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()}
    manifest={"schemaVersion":"1.0","patient":patient.uuid,"format":"OpenRM EHI export","files":[{"name":name,"sha256":sha256(content).hexdigest(),"bytes":len(content)} for name,content in files.items()]}
    files["manifest.json"]=json.dumps(manifest,sort_keys=True,indent=2).encode()
    output=BytesIO()
    with ZipFile(output,"w",ZIP_DEFLATED) as archive:
        for name in sorted(files):archive.writestr(name,files[name])
    return output.getvalue()
