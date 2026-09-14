import { useEffect, useState } from "react";
import type { ApiRequest } from "../../api/client";

type Appointment = {uuid:string;starts_at:string;status:string;title?:string;provider_name?:string;location?:string};
type Result = {uuid:string;order_name:string;name:string;value:string;unit?:string;reference_range?:string;observed_at:string};
type Document = {uuid:string;name:string;mime_type:string;uploaded_at:string};
type ClinicalForm = {uuid:string;title:string;form_type:string;content:Record<string,unknown>;signed_at:string};

export function PortalRecords({api}:{api:ApiRequest}) {
  const [appointments,setAppointments]=useState<Appointment[]>([]); const [results,setResults]=useState<Result[]>([]); const [documents,setDocuments]=useState<Document[]>([]); const [forms,setForms]=useState<ClinicalForm[]>([]); const [error,setError]=useState("");
  useEffect(()=>{void Promise.all([api<Appointment[]>("/api/v1/portal/appointments"),api<Result[]>("/api/v1/portal/results"),api<Document[]>("/api/v1/portal/documents"),api<ClinicalForm[]>("/api/v1/portal/forms")]).then(([a,r,d,f])=>{setAppointments(a);setResults(r);setDocuments(d);setForms(f);}).catch(reason=>setError(reason instanceof Error?reason.message:"Health records could not be loaded"));},[]);
  async function download(item:Document){try{if(!api.raw)throw new Error("Download is unavailable");const response=await api.raw(`/api/v1/portal/documents/${item.uuid}/content`);const url=URL.createObjectURL(await response.blob());const link=globalThis.document.createElement("a");link.href=url;link.download=item.name;link.click();URL.revokeObjectURL(url);}catch(reason){setError(reason instanceof Error?reason.message:"Document could not be downloaded");}}
  return <section aria-label="My health records">{error&&<p className="error">{error}</p>}<div className="portal-record-grid">
    <section className="card"><h2>Appointments</h2>{appointments.length?appointments.map(item=><article key={item.uuid}><strong>{item.title||"Appointment"}</strong><p>{new Date(item.starts_at).toLocaleString()} · {item.status}</p><small>{[item.provider_name,item.location].filter(Boolean).join(" · ")}</small></article>):<p>No appointments are scheduled.</p>}</section>
    <section className="card"><h2>Results</h2>{results.length?results.map(item=><article key={item.uuid}><strong>{item.name}</strong><p>{item.value} {item.unit}</p><small>{item.order_name} · {new Date(item.observed_at).toLocaleDateString()}{item.reference_range?` · Reference ${item.reference_range}`:""}</small></article>):<p>No results have been released.</p>}</section>
    <section className="card"><h2>Documents</h2>{documents.length?documents.map(item=><article key={item.uuid}><button className="text-button" onClick={()=>void download(item)}>{item.name}</button><small>{item.mime_type} · {new Date(item.uploaded_at).toLocaleDateString()}</small></article>):<p>No documents have been released.</p>}</section>
    <section className="card"><h2>Visit forms</h2>{forms.length?forms.map(item=><article key={item.uuid}><strong>{item.title}</strong><p>{Object.entries(item.content).map(([key,value])=>`${key}: ${String(value)}`).join(" · ")}</p><small>{item.form_type} · signed {new Date(item.signed_at).toLocaleDateString()}</small></article>):<p>No signed forms have been released.</p>}</section>
  </div></section>;
}
