import { FormEvent, useEffect, useState } from "react";
import type { ApiRequest } from "../../api/client";
import type { Patient } from "../patients/types";
import { PortalAccessManager } from "./PortalAccessManager";
import { StaffEngagement } from "./StaffEngagement";
import { uiCopy, type UiLanguage } from "../../i18n";

export type SecureMessage = {uuid:string;sender_kind:string;sender_name?:string;body:string;created_at:string};
export type MessageThread = {uuid:string;patient_uuid:string;patient_name:string;subject:string;status:string;updated_at:string;messages:SecureMessage[]};

export function CommunicationWorkspace({api,patients,language="es"}:{api:ApiRequest;patients:Patient[];language?:UiLanguage}) {
  const [threads,setThreads]=useState<MessageThread[]>([]);const [selected,setSelected]=useState<MessageThread|null>(null);const [error,setError]=useState("");const [view,setView]=useState<"patients"|"staff"|"access">("patients");
  const t=(spanish:string,english:string)=>uiCopy(language,spanish,english);
  async function load(){setThreads(await api<MessageThread[]>("/api/v1/messages"));}
  useEffect(()=>{void load();},[]);
  async function open(uuid:string){setSelected(await api<MessageThread>(`/api/v1/messages/${uuid}`));}
  async function create(event:FormEvent<HTMLFormElement>){event.preventDefault();setError("");const element=event.currentTarget;const form=new FormData(element);try{const thread=await api<MessageThread>(`/api/v1/patients/${form.get("patient_uuid")}/messages`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({subject:form.get("subject"),body:form.get("body")})});element.reset();setSelected(thread);await load();}catch(reason){setError(reason instanceof Error?reason.message:t("No se pudo enviar el mensaje","The message could not be sent"));}}
  async function reply(event:FormEvent<HTMLFormElement>){event.preventDefault();if(!selected)return;const element=event.currentTarget;const form=new FormData(element);const thread=await api<MessageThread>(`/api/v1/messages/${selected.uuid}/replies`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({body:form.get("body")})});element.reset();setSelected(thread);await load();}
  return <section className="communication-workspace">
    <header className="communication-hub-heading"><div><p className="eyebrow">{t("CENTRO DE COMUNICACIÓN","COMMUNICATION CENTER")}</p><h2>{t("Conversaciones y acceso al portal","Conversations and portal access")}</h2></div><p>{t("Elige un área de trabajo para comunicarte con pacientes, coordinar al equipo o administrar representantes autorizados.","Choose a workspace to communicate with patients, coordinate the team, or manage authorized representatives.")}</p></header>
    <nav className="communication-mode-tabs" aria-label={t("Áreas de comunicación","Communication areas")}>
      <button className={view==="patients"?"active":""} onClick={()=>setView("patients")}><span aria-hidden="true">✉</span><div><strong>{t("Pacientes","Patients")}</strong><small>{t("Mensajes seguros del portal","Secure portal messages")}</small></div></button>
      <button className={view==="staff"?"active":""} onClick={()=>setView("staff")}><span aria-hidden="true">◎</span><div><strong>{t("Equipo","Team")}</strong><small>{t("Coordinación y cuestionarios","Coordination and questionnaires")}</small></div></button>
      <button className={view==="access"?"active":""} onClick={()=>setView("access")}><span aria-hidden="true">◇</span><div><strong>{t("Acceso delegado","Delegated access")}</strong><small>{t("Representantes autorizados","Authorized representatives")}</small></div></button>
    </nav>
    {view==="patients"&&<section className="communication-section">
      <div className="communication-section-heading"><div><p className="eyebrow">{t("PORTAL DEL PACIENTE","PATIENT PORTAL")}</p><h2>{t("Mensajes con pacientes","Patient messages")}</h2></div><p>{t("Envía información clínica de forma segura y conserva cada respuesta en su conversación.","Send clinical information securely and keep every reply in its conversation.")}</p></div>
      <div className="communications-grid patient-communications">
        <section className="card communications-list">
          <form className="communications-compose" onSubmit={create}><h3>{t("Nuevo mensaje seguro","New secure message")}</h3><label>{t("Destinatario","Recipient")}<select name="patient_uuid" aria-label={t("Paciente","Patient")} required><option value="">{t("Selecciona un paciente","Select a patient")}</option>{patients.map(patient=><option key={patient.uuid} value={patient.uuid}>{patient.last_name}, {patient.first_name}</option>)}</select></label><label>{t("Asunto","Subject")}<input name="subject" placeholder={t("Asunto","Subject")} required minLength={2}/></label><label>{t("Mensaje","Message")}<textarea name="body" placeholder={t("Mensaje clínico seguro","Secure clinical message")} required minLength={2}/></label><button>{t("Enviar al portal","Send to portal")}</button>{error&&<p className="error">{error}</p>}</form>
          <div className="conversation-list-heading"><h3>{t("Conversaciones","Conversations")}</h3><span>{threads.length}</span></div>{threads.map(thread=><button className="thread-row" key={thread.uuid} onClick={()=>void open(thread.uuid)}><strong>{thread.subject}</strong><span>{thread.patient_name} · {thread.status}</span></button>)}{!threads.length&&<p className="empty">{t("No hay conversaciones.","No conversations yet.")}</p>}
        </section>
        <section className="card thread-detail">{selected?<><div className="thread-heading"><div><p className="eyebrow">{selected.patient_name}</p><h2>{selected.subject}</h2></div><span>{selected.status}</span></div><div className="message-stack">{selected.messages.map(message=><article className={`secure-message ${message.sender_kind}`} key={message.uuid}><strong>{message.sender_kind==="patient"?t("Paciente","Patient"):message.sender_name||t("Personal","Staff")}</strong><p>{message.body}</p><small>{new Date(message.created_at).toLocaleString(language)}</small></article>)}</div>{selected.status==="open"&&<form className="reply-form" onSubmit={reply}><label>{t("Respuesta","Reply")}<textarea name="body" aria-label={t("Respuesta","Reply")} placeholder={t("Escribe una respuesta","Write a reply")} required/></label><button>{t("Responder","Reply")}</button></form>}</>:<div className="conversation-empty"><span aria-hidden="true">✉</span><strong>{t("Selecciona una conversación","Select a conversation")}</strong><p>{t("El historial y las respuestas aparecerán en este panel.","The history and replies will appear in this panel.")}</p></div>}</section>
      </div>
    </section>}
    {view==="staff"&&<StaffEngagement api={api} patients={patients} language={language}/>}
    {view==="access"&&<PortalAccessManager api={api} patients={patients} language={language}/>}
  </section>;
}
