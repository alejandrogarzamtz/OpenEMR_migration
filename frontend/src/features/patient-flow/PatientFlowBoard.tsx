import { FormEvent, useEffect, useState } from "react";
import type { ApiRequest } from "../../api/client";
import { uiCopy, type UiLanguage } from "../../i18n";

type FlowEpisode = { uuid:string; patient_name:string; started_at:string; current_status:string|null; current_room:string|null; current_since:string|null };
const statuses=["arrived","checked-in","in-progress","fulfilled","cancelled","no-show"];

export function PatientFlowBoard({api,language="en"}:{api:ApiRequest;language?:UiLanguage}){
  const [items,setItems]=useState<FlowEpisode[]>([]); const [error,setError]=useState("");
  const t=(spanish:string,english:string)=>uiCopy(language,spanish,english);
  async function load(){try{setItems(await api<FlowEpisode[]>("/api/v1/patient-flow"));setError("");}catch(reason){setError(reason instanceof Error?reason.message:t("No se pudo cargar el flujo de pacientes","Could not load patient flow"));}}
  useEffect(()=>{void load();},[]);
  async function transition(event:FormEvent<HTMLFormElement>,episode:FlowEpisode){event.preventDefault();const data=new FormData(event.currentTarget);try{await api(`/api/v1/patient-flow/${episode.uuid}/events`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:data.get("status"),room:data.get("room")||null})});await load();}catch(reason){setError(reason instanceof Error?reason.message:t("No se pudo actualizar el flujo de pacientes","Could not update patient flow"));}}
  return <section className="card flow-board"><div className="board-heading"><div><p className="eyebrow">{t("OPERACIÓN EN VIVO","LIVE OPERATIONS")}</p><h2>{t("Flujo de pacientes","Patient flow")}</h2></div><button onClick={()=>void load()}>{t("Actualizar","Refresh")}</button></div>{error&&<p className="error">{error}</p>}{items.length?<div className="flow-grid">{items.map(item=><article key={item.uuid} className="flow-card"><h3>{item.patient_name}</h3><p><strong>{item.current_status??t("pendiente","pending")}</strong> · {item.current_room??t("Sin consultorio","No room")}</p><small>{t("Desde","Since")} {new Date(item.current_since??item.started_at).toLocaleString(language)}</small><form onSubmit={event=>void transition(event,item)}><select name="status" defaultValue={item.current_status??"arrived"}>{statuses.map(value=><option key={value}>{value}</option>)}</select><input name="room" defaultValue={item.current_room??""} placeholder={t("Consultorio","Room")} maxLength={20}/><button>{t("Actualizar","Update")}</button></form></article>)}</div>:<div className="empty">{t("No hay episodios activos de flujo de pacientes.","No active patient-flow episodes.")}</div>}</section>;
}
