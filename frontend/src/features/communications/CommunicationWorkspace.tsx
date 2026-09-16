import { FormEvent, useEffect, useState } from "react";
import type { ApiRequest } from "../../api/client";
import type { Patient } from "../patients/types";
import { PortalAccessManager } from "./PortalAccessManager";
import { StaffEngagement } from "./StaffEngagement";

export type SecureMessage = {uuid:string;sender_kind:string;sender_name?:string;body:string;created_at:string};
export type MessageThread = {uuid:string;patient_uuid:string;patient_name:string;subject:string;status:string;updated_at:string;messages:SecureMessage[]};

export function CommunicationWorkspace({api,patients}:{api:ApiRequest;patients:Patient[]}) {
  const [threads,setThreads]=useState<MessageThread[]>([]);const [selected,setSelected]=useState<MessageThread|null>(null);const [error,setError]=useState("");const [view,setView]=useState<"patients"|"staff"|"access">("patients");
  async function load(){setThreads(await api<MessageThread[]>("/api/v1/messages"));}
  useEffect(()=>{void load();},[]);
  async function open(uuid:string){setSelected(await api<MessageThread>(`/api/v1/messages/${uuid}`));}
  async function create(event:FormEvent<HTMLFormElement>){event.preventDefault();setError("");const element=event.currentTarget;const form=new FormData(element);try{const thread=await api<MessageThread>(`/api/v1/patients/${form.get("patient_uuid")}/messages`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({subject:form.get("subject"),body:form.get("body")})});element.reset();setSelected(thread);await load();}catch(reason){setError(reason instanceof Error?reason.message:"No se pudo enviar el mensaje");}}
  async function reply(event:FormEvent<HTMLFormElement>){event.preventDefault();if(!selected)return;const element=event.currentTarget;const form=new FormData(element);const thread=await api<MessageThread>(`/api/v1/messages/${selected.uuid}/replies`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({body:form.get("body")})});element.reset();setSelected(thread);await load();}
  return <section className="communication-workspace">
    <header className="communication-hub-heading"><div><p className="eyebrow">CENTRO DE COMUNICACIÓN</p><h2>Conversaciones y acceso al portal</h2></div><p>Elige un área de trabajo para comunicarte con pacientes, coordinar al equipo o administrar representantes autorizados.</p></header>
    <nav className="communication-mode-tabs" aria-label="Áreas de comunicación">
      <button className={view==="patients"?"active":""} onClick={()=>setView("patients")}><span aria-hidden="true">✉</span><div><strong>Pacientes</strong><small>Mensajes seguros del portal</small></div></button>
      <button className={view==="staff"?"active":""} onClick={()=>setView("staff")}><span aria-hidden="true">◎</span><div><strong>Equipo</strong><small>Coordinación y cuestionarios</small></div></button>
      <button className={view==="access"?"active":""} onClick={()=>setView("access")}><span aria-hidden="true">◇</span><div><strong>Acceso delegado</strong><small>Representantes autorizados</small></div></button>
    </nav>
    {view==="patients"&&<section className="communication-section">
      <div className="communication-section-heading"><div><p className="eyebrow">PORTAL DEL PACIENTE</p><h2>Mensajes con pacientes</h2></div><p>Envía información clínica de forma segura y conserva cada respuesta en su conversación.</p></div>
      <div className="communications-grid patient-communications">
        <section className="card communications-list">
          <form className="communications-compose" onSubmit={create}><h3>Nuevo mensaje seguro</h3><label>Destinatario<select name="patient_uuid" aria-label="Paciente" required><option value="">Selecciona un paciente</option>{patients.map(patient=><option key={patient.uuid} value={patient.uuid}>{patient.last_name}, {patient.first_name}</option>)}</select></label><label>Asunto<input name="subject" placeholder="Asunto" required minLength={2}/></label><label>Mensaje<textarea name="body" placeholder="Mensaje clínico seguro" required minLength={2}/></label><button>Enviar al portal</button>{error&&<p className="error">{error}</p>}</form>
          <div className="conversation-list-heading"><h3>Conversaciones</h3><span>{threads.length}</span></div>{threads.map(thread=><button className="thread-row" key={thread.uuid} onClick={()=>void open(thread.uuid)}><strong>{thread.subject}</strong><span>{thread.patient_name} · {thread.status}</span></button>)}{!threads.length&&<p className="empty">No hay conversaciones.</p>}
        </section>
        <section className="card thread-detail">{selected?<><div className="thread-heading"><div><p className="eyebrow">{selected.patient_name}</p><h2>{selected.subject}</h2></div><span>{selected.status}</span></div><div className="message-stack">{selected.messages.map(message=><article className={`secure-message ${message.sender_kind}`} key={message.uuid}><strong>{message.sender_kind==="patient"?"Paciente":message.sender_name||"Personal"}</strong><p>{message.body}</p><small>{new Date(message.created_at).toLocaleString()}</small></article>)}</div>{selected.status==="open"&&<form className="reply-form" onSubmit={reply}><label>Respuesta<textarea name="body" aria-label="Respuesta" placeholder="Escribe una respuesta" required/></label><button>Responder</button></form>}</>:<div className="conversation-empty"><span aria-hidden="true">✉</span><strong>Selecciona una conversación</strong><p>El historial y las respuestas aparecerán en este panel.</p></div>}</section>
      </div>
    </section>}
    {view==="staff"&&<StaffEngagement api={api} patients={patients}/>}
    {view==="access"&&<PortalAccessManager api={api} patients={patients}/>}
  </section>;
}
