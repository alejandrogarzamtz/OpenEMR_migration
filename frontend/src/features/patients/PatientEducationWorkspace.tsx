import {FormEvent,useEffect,useState} from "react";
import type {ApiRequest} from "../../api/client";

type Resource={uuid:string;name:string;url_template:string;sequence:number;active:boolean};
export function PatientEducationWorkspace({api}:{api:ApiRequest}){
 const [items,setItems]=useState<Resource[]>([]),[error,setError]=useState("");
 useEffect(()=>{void api<Resource[]>("/api/v1/patient-education/resources").then(setItems).catch(reason=>setError(reason instanceof Error?reason.message:"Could not load resources"))},[]);
 async function search(event:FormEvent<HTMLFormElement>){event.preventDefault();const data=new FormData(event.currentTarget),uuid=String(data.get("resource")),q=String(data.get("query"));try{const result=await api<{url:string}>(`/api/v1/patient-education/resources/${uuid}/search?q=${encodeURIComponent(q)}`);window.open(result.url,"_blank","noopener,noreferrer")}catch(reason){setError(reason instanceof Error?reason.message:"Could not create search")}}
 return <section className="card education-workspace">
  <header className="education-heading">
   <div><p className="eyebrow">PATIENT EDUCATION</p><h2>Trusted education search</h2></div>
   <p>Search the configured external clinical education resources. Results open on the selected provider site.</p>
  </header>
  <form className="education-search" onSubmit={search}>
   <label>Resource<select name="resource" aria-label="Education resource" required><option value="">Select a resource</option>{items.map(item=><option key={item.uuid} value={item.uuid}>{item.name}</option>)}</select></label>
   <label>Search topic<input name="query" aria-label="Education search" placeholder="Condition, diagnosis, or treatment" maxLength={500} required/></label>
   <button>Search resource</button>
  </form>
  <section className="education-resources" aria-labelledby="education-resources-title">
   <div className="education-resources-heading"><div><p className="eyebrow">AVAILABLE SOURCES</p><h3 id="education-resources-title">Configured resources</h3></div><span>{items.length}</span></div>
   {items.length?<div className="education-resource-list">{items.map(item=><article key={item.uuid}><span aria-hidden="true">↗</span><div><strong>{item.name}</strong><small>Opens in a secure new tab</small></div></article>)}</div>:!error&&<p className="empty education-empty">No active education resources configured.</p>}
  </section>
  {error&&<p className="error education-error">{error}</p>}
 </section>
}
