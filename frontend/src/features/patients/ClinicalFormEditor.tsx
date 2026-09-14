import { FormEvent, useEffect, useState } from "react";
import type { ApiRequest } from "../../api/client";

type Field={key:string;label:string;type:string;required?:boolean};
type ExamLine={line_id:string;system:string;label:string};
type Definition={title:string;kind:string;fields?:Field[];lines?:ExamLine[];values?:string[]};
type Definitions=Record<string,Definition>;

export function ClinicalFormEditor({api,patientUuid,encounterUuid,onSaved}:{api:ApiRequest;patientUuid:string;encounterUuid:string;onSaved:()=>void|Promise<void>}){
  const [definitions,setDefinitions]=useState<Definitions>({}),[formType,setFormType]=useState("soap"),[error,setError]=useState("");
  useEffect(()=>{void api<Definitions>("/api/v1/clinical-form-definitions").then(setDefinitions).catch(reason=>setError(reason instanceof Error?reason.message:"No se pudieron cargar los formularios"));},[api]);
  const definition=definitions[formType];
  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setError("");const form=event.currentTarget;const data=new FormData(form);let content:Record<string,unknown>={};
    try{
      if(definition?.kind==="narrative")content=Object.fromEntries((definition.fields??[]).map(field=>[field.key,String(data.get(field.key)??"")]));
      else if(definition?.kind==="review-of-systems")content=Object.fromEntries((definition.fields??[]).map(field=>[field.key,String(data.get(field.key)??"not-assessed")]));
      else if(definition?.kind==="exam-findings")content={findings:(definition.lines??[]).map(line=>({line_id:line.line_id,status:String(data.get(`status:${line.line_id}`)??"not-examined"),diagnosis:String(data.get(`diagnosis:${line.line_id}`)??""),comments:String(data.get(`comments:${line.line_id}`)??"")}))};
      else content=JSON.parse(String(data.get("custom_content")||"{}"));
      await api(`/api/v1/patients/${patientUuid}/clinical-forms`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({encounter_uuid:encounterUuid,form_type:formType,title:data.get("title"),content})});
      form.reset();await onSaved();
    }catch(reason){setError(reason instanceof Error?reason.message:"No se pudo guardar el formulario");}
  }
  return <form className="clinical-form-editor" onSubmit={submit}>
    <div className="quick-add compact"><label>Tipo<select aria-label="Tipo de formulario" value={formType} onChange={event=>setFormType(event.target.value)}>{Object.entries(definitions).map(([key,value])=><option key={key} value={key}>{value.title}</option>)}</select></label><label>Título<input name="title" required maxLength={255}/></label></div>
    {definition?.kind==="narrative"&&(definition.fields??[]).map(field=><label key={field.key}>{field.label}<textarea name={field.key} required={field.required} maxLength={20_000}/></label>)}
    {definition?.kind==="review-of-systems"&&<div className="form-grid">{(definition.fields??[]).map(field=><label key={field.key}>{field.label}<select name={field.key} defaultValue="not-assessed"><option value="not-assessed">No evaluado</option><option value="negative">Negativo</option><option value="positive">Positivo</option></select></label>)}</div>}
    {definition?.kind==="exam-findings"&&<div className="exam-grid">{(definition.lines??[]).map(line=><fieldset key={line.line_id}><legend>{line.system} · {line.label}</legend><select aria-label={`${line.label} estado`} name={`status:${line.line_id}`} defaultValue="not-examined"><option value="not-examined">No examinado</option><option value="normal">Normal</option><option value="abnormal">Anormal</option></select><input name={`diagnosis:${line.line_id}`} placeholder="Diagnóstico" maxLength={20_000}/><input name={`comments:${line.line_id}`} placeholder="Comentarios" maxLength={20_000}/></fieldset>)}</div>}
    {definition?.kind==="custom-json"&&<label>Contenido JSON<textarea name="custom_content" defaultValue="{}" required/></label>}
    {definition&&<button>Guardar borrador</button>}{error&&<p className="error">{error}</p>}
  </form>;
}
