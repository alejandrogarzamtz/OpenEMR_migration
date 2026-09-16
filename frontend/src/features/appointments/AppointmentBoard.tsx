import { FormEvent, useEffect, useState } from "react";
import type { ApiRequest } from "../../api/client";
import type { Patient } from "../patients/types";

type Appointment = {
  uuid: string; patient_uuid: string; starts_at: string; ends_at: string; status: string;
  title?: string; provider_name?: string; facility_name?: string; room?: string;
};
type Facility = {uuid:string;name:string};

export function AppointmentBoard({api,patients}:{api:ApiRequest;patients:Patient[]}) {
  const [items,setItems]=useState<Appointment[]>([]);
  const [facilities,setFacilities]=useState<Facility[]>([]);
  const [error,setError]=useState("");
  async function load(){try{const [appointments,resources]=await Promise.all([api<Appointment[]>("/api/v1/appointments"),api<Facility[]>("/api/v1/appointments/facilities")]);setItems(appointments);setFacilities(resources);}catch(reason){setError(reason instanceof Error?reason.message:"Could not load appointments");}}
  useEffect(()=>{void load();},[]);
  async function create(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setError("");const data=new FormData(event.currentTarget);
    try{await api("/api/v1/appointments",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
      patient_uuid:data.get("patient_uuid"),starts_at:new Date(String(data.get("starts_at"))).toISOString(),ends_at:new Date(String(data.get("ends_at"))).toISOString(),
      title:data.get("title"),provider_name:data.get("provider_name"),facility_uuid:data.get("facility_uuid")||null,room:data.get("room")||null,
    })});event.currentTarget.reset();await load();}catch(reason){setError(reason instanceof Error?reason.message:"Could not save appointment");}
  }
  async function setStatus(item:Appointment,status:string){await api(`/api/v1/appointments/${item.uuid}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({status})});await load();}
  async function startFlow(item:Appointment){try{await api(`/api/v1/appointments/${item.uuid}/patient-flow`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:"arrived",room:item.room??null})});await load();}catch(reason){setError(reason instanceof Error?reason.message:"Could not start patient flow");}}
  return <section className="appointments">
    <form className="card appointment-form" onSubmit={create}>
      <div className="appointment-form-heading">
        <div><p className="eyebrow">NUEVA CITA</p><h2>Programar una cita</h2></div>
        <p>Selecciona al paciente, define el horario y asigna los recursos necesarios.</p>
      </div>
      <div className="appointment-grid">
        <label className="appointment-patient">Paciente<select name="patient_uuid" required><option value="">Seleccionar paciente</option>{patients.map(patient=><option key={patient.uuid} value={patient.uuid}>{patient.last_name}, {patient.first_name}</option>)}</select></label>
        <label className="appointment-start">Inicio<input name="starts_at" type="datetime-local" required/></label>
        <label className="appointment-end">Fin<input name="ends_at" type="datetime-local" required/></label>
        <label className="appointment-title">Motivo o título<input name="title" maxLength={150} placeholder="Ej. Consulta de seguimiento"/></label>
        <label className="appointment-provider">Profesional<input name="provider_name" maxLength={150} placeholder="Nombre del profesional"/></label>
        <label className="appointment-facility">Instalación<select name="facility_uuid"><option value="">Sin instalación</option>{facilities.map(item=><option key={item.uuid} value={item.uuid}>{item.name}</option>)}</select></label>
        <label className="appointment-room">Consultorio<input name="room" maxLength={20} placeholder="Ej. 204"/></label>
      </div>
      <div className="appointment-form-actions"><button>Programar cita</button></div>
    </form>
    {error&&<p className="error">{error}</p>}
    <section className="card appointment-list">
      <div className="appointment-list-heading"><div><p className="eyebrow">AGENDA</p><h2>Próximas citas</h2></div><span>{items.length} {items.length===1?"cita":"citas"}</span></div>
      {items.length?<div className="appointment-table"><table><thead><tr><th>Fecha y hora</th><th>Paciente</th><th>Recursos</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>{items.map(item=><tr key={item.uuid}><td><strong>{new Date(item.starts_at).toLocaleDateString()}</strong><small>{new Date(item.starts_at).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"})}</small></td><td>{patients.find(patient=>patient.uuid===item.patient_uuid)?.last_name??item.patient_uuid.slice(0,8)}</td><td>{[item.provider_name,item.facility_name,item.room].filter(Boolean).join(" · ")||"Sin asignar"}</td><td><span className={`appointment-status status-${item.status}`}>{item.status}</span></td><td><div className="appointment-actions"><button onClick={()=>void startFlow(item)}>Registrar llegada</button>{item.status!=="fulfilled"&&<button className="secondary" onClick={()=>void setStatus(item,"fulfilled")}>Completar</button>}{item.status!=="cancelled"&&<button className="text-button danger-action" onClick={()=>void setStatus(item,"cancelled")}>Cancelar</button>}</div></td></tr>)}</tbody></table></div>:<div className="appointment-empty"><span aria-hidden="true">＋</span><strong>Aún no hay citas programadas</strong><p>Utiliza el formulario superior para agregar la primera cita.</p></div>}
    </section>
  </section>;
}
