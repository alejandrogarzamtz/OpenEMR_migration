import { FormEvent, useEffect, useState } from "react";
import type { ApiRequest } from "../../api/client";
import type { Patient } from "../patients/types";
import { uiCopy, type UiLanguage } from "../../i18n";

type Appointment = {
  uuid: string; patient_uuid: string; starts_at: string; ends_at: string; status: string;
  title?: string; provider_name?: string; facility_name?: string; room?: string;
};
type Facility = {uuid:string;name:string};

export function AppointmentBoard({api,patients,language="es"}:{api:ApiRequest;patients:Patient[];language?:UiLanguage}) {
  const [items,setItems]=useState<Appointment[]>([]);
  const [facilities,setFacilities]=useState<Facility[]>([]);
  const [error,setError]=useState("");
  const t=(spanish:string,english:string)=>uiCopy(language,spanish,english);
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
        <div><p className="eyebrow">{t("NUEVA CITA","NEW APPOINTMENT")}</p><h2>{t("Programar una cita","Schedule an appointment")}</h2></div>
        <p>{t("Selecciona al paciente, define el horario y asigna los recursos necesarios.","Select the patient, set the schedule, and assign the required resources.")}</p>
      </div>
      <div className="appointment-grid">
        <label className="appointment-patient">{t("Paciente","Patient")}<select name="patient_uuid" required><option value="">{t("Seleccionar paciente","Select patient")}</option>{patients.map(patient=><option key={patient.uuid} value={patient.uuid}>{patient.last_name}, {patient.first_name}</option>)}</select></label>
        <label className="appointment-start">{t("Inicio","Starts")}<input name="starts_at" type="datetime-local" required/></label>
        <label className="appointment-end">{t("Fin","Ends")}<input name="ends_at" type="datetime-local" required/></label>
        <label className="appointment-title">{t("Motivo o título","Reason or title")}<input name="title" maxLength={150} placeholder={t("Ej. Consulta de seguimiento","For example, follow-up visit")}/></label>
        <label className="appointment-provider">{t("Profesional","Provider")}<input name="provider_name" maxLength={150} placeholder={t("Nombre del profesional","Provider name")}/></label>
        <label className="appointment-facility">{t("Instalación","Facility")}<select name="facility_uuid"><option value="">{t("Sin instalación","No facility")}</option>{facilities.map(item=><option key={item.uuid} value={item.uuid}>{item.name}</option>)}</select></label>
        <label className="appointment-room">{t("Consultorio","Room")}<input name="room" maxLength={20} placeholder={t("Ej. 204","For example, 204")}/></label>
      </div>
      <div className="appointment-form-actions"><button>{t("Programar cita","Schedule appointment")}</button></div>
    </form>
    {error&&<p className="error">{error}</p>}
    <section className="card appointment-list">
      <div className="appointment-list-heading"><div><p className="eyebrow">{t("AGENDA","SCHEDULE")}</p><h2>{t("Próximas citas","Upcoming appointments")}</h2></div><span>{items.length} {items.length===1?t("cita","appointment"):t("citas","appointments")}</span></div>
      {items.length?<div className="appointment-table"><table><thead><tr><th>{t("Fecha y hora","Date and time")}</th><th>{t("Paciente","Patient")}</th><th>{t("Recursos","Resources")}</th><th>{t("Estado","Status")}</th><th>{t("Acciones","Actions")}</th></tr></thead><tbody>{items.map(item=><tr key={item.uuid}><td><strong>{new Date(item.starts_at).toLocaleDateString(language)}</strong><small>{new Date(item.starts_at).toLocaleTimeString(language, {hour:"2-digit",minute:"2-digit"})}</small></td><td>{patients.find(patient=>patient.uuid===item.patient_uuid)?.last_name??item.patient_uuid.slice(0,8)}</td><td>{[item.provider_name,item.facility_name,item.room].filter(Boolean).join(" · ")||t("Sin asignar","Unassigned")}</td><td><span className={`appointment-status status-${item.status}`}>{item.status}</span></td><td><div className="appointment-actions"><button onClick={()=>void startFlow(item)}>{t("Registrar llegada","Check in")}</button>{item.status!=="fulfilled"&&<button className="secondary" onClick={()=>void setStatus(item,"fulfilled")}>{t("Completar","Complete")}</button>}{item.status!=="cancelled"&&<button className="text-button danger-action" onClick={()=>void setStatus(item,"cancelled")}>{t("Cancelar","Cancel")}</button>}</div></td></tr>)}</tbody></table></div>:<div className="appointment-empty"><span aria-hidden="true">＋</span><strong>{t("Aún no hay citas programadas","No appointments scheduled yet")}</strong><p>{t("Utiliza el formulario superior para agregar la primera cita.","Use the form above to add the first appointment.")}</p></div>}
    </section>
  </section>;
}
