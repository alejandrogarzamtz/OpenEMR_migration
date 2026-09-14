import { FormEvent, useEffect, useState } from "react";
import type { ApiRequest } from "../../api/client";
import type { Patient } from "../patients/types";

type Appointment = {
  uuid: string; patient_uuid: string; starts_at: string; ends_at: string; status: string;
  title?: string; provider_name?: string; facility_name?: string; room?: string;
};

export function AppointmentBoard({api,patients}:{api:ApiRequest;patients:Patient[]}) {
  const [items,setItems]=useState<Appointment[]>([]);
  const [error,setError]=useState("");
  async function load(){try{setItems(await api<Appointment[]>("/api/v1/appointments"));}catch(reason){setError(reason instanceof Error?reason.message:"Could not load appointments");}}
  useEffect(()=>{void load();},[]);
  async function create(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setError("");const data=new FormData(event.currentTarget);
    try{await api("/api/v1/appointments",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
      patient_uuid:data.get("patient_uuid"),starts_at:new Date(String(data.get("starts_at"))).toISOString(),ends_at:new Date(String(data.get("ends_at"))).toISOString(),
      title:data.get("title"),provider_name:data.get("provider_name"),facility_name:data.get("facility_name"),room:data.get("room")||null,
    })});event.currentTarget.reset();await load();}catch(reason){setError(reason instanceof Error?reason.message:"Could not save appointment");}
  }
  async function setStatus(item:Appointment,status:string){await api(`/api/v1/appointments/${item.uuid}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({status})});await load();}
  async function startFlow(item:Appointment){try{await api(`/api/v1/appointments/${item.uuid}/patient-flow`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:"arrived",room:item.room??null})});await load();}catch(reason){setError(reason instanceof Error?reason.message:"Could not start patient flow");}}
  return <section className="appointments"><form className="card appointment-form" onSubmit={create}><h2>Schedule appointment</h2><div className="form-grid">
    <label>Patient<select name="patient_uuid" required><option value="">Select patient</option>{patients.map(patient=><option key={patient.uuid} value={patient.uuid}>{patient.last_name}, {patient.first_name}</option>)}</select></label>
    <label>Starts<input name="starts_at" type="datetime-local" required/></label><label>Ends<input name="ends_at" type="datetime-local" required/></label>
    <label>Title<input name="title" maxLength={150}/></label><label>Provider<input name="provider_name" maxLength={150}/></label>
    <label>Facility<input name="facility_name" maxLength={150}/></label><label>Room<input name="room" maxLength={20}/></label>
  </div><button>Schedule</button></form>{error&&<p className="error">{error}</p>}
  <section className="card"><h2>Appointments</h2>{items.length?<table><thead><tr><th>When</th><th>Patient</th><th>Resource</th><th>Status</th><th>Actions</th></tr></thead><tbody>{items.map(item=><tr key={item.uuid}><td>{new Date(item.starts_at).toLocaleString()}</td><td>{patients.find(patient=>patient.uuid===item.patient_uuid)?.last_name??item.patient_uuid.slice(0,8)}</td><td>{[item.provider_name,item.facility_name,item.room].filter(Boolean).join(" · ")||"—"}</td><td>{item.status}</td><td><button onClick={()=>void startFlow(item)}>Arrive</button> {item.status!=="fulfilled"&&<button onClick={()=>void setStatus(item,"fulfilled")}>Complete</button>} {item.status!=="cancelled"&&<button onClick={()=>void setStatus(item,"cancelled")}>Cancel</button>}</td></tr>)}</tbody></table>:<div className="empty">No appointments to show.</div>}</section></section>;
}
