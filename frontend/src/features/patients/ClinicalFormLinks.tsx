import { FormEvent, useEffect, useState } from "react";
import type { ApiRequest } from "../../api/client";

type Target={uuid:string;label:string;linked_at:string;legacy_clinical_note_id?:number};
type Links={documents:Target[];results:Target[]};
type Document={uuid:string;name:string};
type Result={uuid:string;name:string;value:string;unit?:string};

export function ClinicalFormLinks({api,patientUuid,formUuid,documents,results,locked}:{api:ApiRequest;patientUuid:string;formUuid:string;documents:Document[];results:Result[];locked:boolean}){
  const base=`/api/v1/patients/${patientUuid}/clinical-forms/${formUuid}`;const [links,setLinks]=useState<Links>({documents:[],results:[]}),[error,setError]=useState("");
  async function load(){try{setLinks(await api<Links>(`${base}/links`));}catch(reason){setError(reason instanceof Error?reason.message:"No se pudieron cargar los vínculos");}}
  useEffect(()=>{void load();},[patientUuid,formUuid]);
  async function add(event:FormEvent<HTMLFormElement>,kind:"documents"|"results"){event.preventDefault();const form=event.currentTarget,value=String(new FormData(form).get("target")??"");if(!value)return;try{await api(`${base}/${kind}/${value}`,{method:"POST"});form.reset();await load();}catch(reason){setError(reason instanceof Error?reason.message:"No se pudo crear el vínculo");}}
  async function remove(kind:"documents"|"results",uuid:string){try{await api(`${base}/${kind}/${uuid}`,{method:"DELETE"});await load();}catch(reason){setError(reason instanceof Error?reason.message:"No se pudo retirar el vínculo");}}
  const linkedDocuments=new Set(links.documents.map(item=>item.uuid)),linkedResults=new Set(links.results.map(item=>item.uuid));
  return <div className="clinical-form-links"><small>Evidencia vinculada: {links.documents.length} documento(s), {links.results.length} resultado(s)</small>{links.documents.map(item=><span key={`d-${item.uuid}`}>{item.label}{!locked&&<button type="button" aria-label={`Desvincular ${item.label}`} onClick={()=>void remove("documents",item.uuid)}>×</button>}</span>)}{links.results.map(item=><span key={`r-${item.uuid}`}>{item.label}{!locked&&<button type="button" aria-label={`Desvincular ${item.label}`} onClick={()=>void remove("results",item.uuid)}>×</button>}</span>)}{!locked&&<><form onSubmit={event=>add(event,"documents")}><select name="target" aria-label="Documento para vincular" defaultValue=""><option value="">Vincular documento…</option>{documents.filter(item=>!linkedDocuments.has(item.uuid)).map(item=><option key={item.uuid} value={item.uuid}>{item.name}</option>)}</select><button>Vincular</button></form><form onSubmit={event=>add(event,"results")}><select name="target" aria-label="Resultado para vincular" defaultValue=""><option value="">Vincular resultado…</option>{results.filter(item=>!linkedResults.has(item.uuid)).map(item=><option key={item.uuid} value={item.uuid}>{item.name}: {item.value} {item.unit}</option>)}</select><button>Vincular</button></form></>}{error&&<p className="error">{error}</p>}</div>;
}
