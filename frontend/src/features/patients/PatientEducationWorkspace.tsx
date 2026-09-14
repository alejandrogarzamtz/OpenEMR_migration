import {FormEvent,useEffect,useState} from "react";
import type {ApiRequest} from "../../api/client";

type Resource={uuid:string;name:string;url_template:string;sequence:number;active:boolean};
export function PatientEducationWorkspace({api}:{api:ApiRequest}){
 const [items,setItems]=useState<Resource[]>([]),[error,setError]=useState("");
 useEffect(()=>{void api<Resource[]>("/api/v1/patient-education/resources").then(setItems).catch(reason=>setError(reason instanceof Error?reason.message:"Could not load resources"))},[]);
 async function search(event:FormEvent<HTMLFormElement>){event.preventDefault();const data=new FormData(event.currentTarget),uuid=String(data.get("resource")),q=String(data.get("query"));try{const result=await api<{url:string}>(`/api/v1/patient-education/resources/${uuid}/search?q=${encodeURIComponent(q)}`);window.open(result.url,"_blank","noopener,noreferrer")}catch(reason){setError(reason instanceof Error?reason.message:"Could not create search")}}
 return <section className="card"><p className="eyebrow">PATIENT EDUCATION</p><h2>Trusted education search</h2><p>Search the configured external clinical education resources. Results open on the selected provider site.</p><form className="quick-add" onSubmit={search}><select name="resource" aria-label="Education resource" required><option value="">Select a resource</option>{items.map(item=><option key={item.uuid} value={item.uuid}>{item.name}</option>)}</select><input name="query" aria-label="Education search" placeholder="Condition, diagnosis, or treatment" maxLength={500} required/><button>Search resource</button></form>{!items.length&&!error&&<p>No active education resources configured.</p>}{error&&<p className="error">{error}</p>}</section>
}
