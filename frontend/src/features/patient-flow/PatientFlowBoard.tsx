import { FormEvent, useEffect, useState } from "react";
import type { ApiRequest } from "../../api/client";

type FlowEpisode = { uuid:string; patient_name:string; started_at:string; current_status:string|null; current_room:string|null; current_since:string|null };
const statuses=["arrived","checked-in","in-progress","fulfilled","cancelled","no-show"];

export function PatientFlowBoard({api}:{api:ApiRequest}){
  const [items,setItems]=useState<FlowEpisode[]>([]); const [error,setError]=useState("");
  async function load(){try{setItems(await api<FlowEpisode[]>("/api/v1/patient-flow"));setError("");}catch(reason){setError(reason instanceof Error?reason.message:"Could not load patient flow");}}
  useEffect(()=>{void load();},[]);
  async function transition(event:FormEvent<HTMLFormElement>,episode:FlowEpisode){event.preventDefault();const data=new FormData(event.currentTarget);try{await api(`/api/v1/patient-flow/${episode.uuid}/events`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:data.get("status"),room:data.get("room")||null})});await load();}catch(reason){setError(reason instanceof Error?reason.message:"Could not update patient flow");}}
  return <section className="card flow-board"><div className="board-heading"><div><p className="eyebrow">LIVE OPERATIONS</p><h2>Patient flow</h2></div><button onClick={()=>void load()}>Refresh</button></div>{error&&<p className="error">{error}</p>}{items.length?<div className="flow-grid">{items.map(item=><article key={item.uuid} className="flow-card"><h3>{item.patient_name}</h3><p><strong>{item.current_status??"pending"}</strong> · {item.current_room??"No room"}</p><small>Since {new Date(item.current_since??item.started_at).toLocaleString()}</small><form onSubmit={event=>void transition(event,item)}><select name="status" defaultValue={item.current_status??"arrived"}>{statuses.map(value=><option key={value}>{value}</option>)}</select><input name="room" defaultValue={item.current_room??""} placeholder="Room" maxLength={20}/><button>Update</button></form></article>)}</div>:<div className="empty">No active patient-flow episodes.</div>}</section>;
}
