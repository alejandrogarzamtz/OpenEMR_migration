import React, { FormEvent, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import "./clinical.css";
import { createApiClient } from "./api/client";
import { PatientForm } from "./features/patients/PatientForm";
import { PatientContacts } from "./features/patients/PatientContacts";
import { PatientPhotos } from "./features/patients/PatientPhotos";
import { PatientDuplicates } from "./features/patients/PatientDuplicates";
import { PatientReportButton } from "./features/patients/PatientReportButton";
import { ClinicalFormEditor } from "./features/patients/ClinicalFormEditor";
import { CarePlanWorkspace } from "./features/patients/CarePlanWorkspace";
import { ClinicalFormLinks } from "./features/patients/ClinicalFormLinks";
import type { Patient, PatientInput } from "./features/patients/types";
import { AppointmentBoard } from "./features/appointments/AppointmentBoard";
import { PatientFlowBoard } from "./features/patient-flow/PatientFlowBoard";
import { InventoryWorkspace } from "./features/inventory/InventoryWorkspace";
import { AdministrationWorkspace } from "./features/administration/AdministrationWorkspace";
import { ReportWorkspace } from "./features/reports/ReportWorkspace";
import { CommunicationWorkspace } from "./features/communications/CommunicationWorkspace";
import { PortalApp } from "./features/communications/PortalApp";
import { SecurityWorkspace } from "./features/security/SecurityWorkspace";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
type Item = { uuid:string; title:string; status:string; code?:string; reaction?:string; dosage?:string };
type LabOrder = { uuid:string; ordered_at:string; code:string; name:string; status:string };
type LabResult = { uuid:string; name:string; value:string; unit?:string };
type ClinicalDocument = { uuid:string; name:string; mime_type:string; uploaded_at:string; released_to_patient_at?:string };
type Coverage = { uuid:string; payer_name:string; policy_number:string; priority:string };
type Charge = { uuid:string; encounter_uuid:string; code:string; description:string; unit_price:string; units:number };
type Claim = { uuid:string; status:string; total:string; balance:string; released_to_patient_at?:string };
type Immunization = { uuid:string; vaccine_name:string; cvx_code:string; administered_at:string };
type Vitals = { uuid:string; observed_at:string; systolic?:string; diastolic?:string; heart_rate?:string; oxygen_saturation?:string; bmi?:string };
type Prescription = { uuid:string; drug_name:string; dosage_instructions:string; status:string };
type ClinicalForm = { uuid:string; encounter_uuid:string; form_type:string; title:string; content:Record<string,unknown>; status:string; authored_at:string; signed_at?:string; locked:boolean; signature_count:number; released_to_patient_at?:string };
type EncounterSummary={uuid:string;occurred_at:string;chief_complaint?:string;locked:boolean;signature_count:number};
type Summary = { patient:Patient; problems:Item[]; allergies:Item[]; medications:Item[]; encounters:EncounterSummary[]; labOrders:LabOrder[]; labResults:LabResult[]; documents:ClinicalDocument[]; coverages:Coverage[]; charges:Charge[]; claims:Claim[]; immunizations:Immunization[]; vitals:Vitals[]; prescriptions:Prescription[]; clinicalForms:ClinicalForm[] };

function Login({ done }:{ done:(token:string)=>void }) {
  const [error,setError]=useState("");
  const [challenge,setChallenge]=useState("");
  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault(); const data=new FormData(event.currentTarget);
    const response=await fetch(`${API}/api/v1/auth/token`,{method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:data.get("email"),password:data.get("password")})});
    if(!response.ok)return setError("Credenciales inválidas");
    const body=await response.json(); if(body.mfa_required){setChallenge(body.challenge_token);setError("");}else done(body.access_token);
  }
  async function verify(event:FormEvent<HTMLFormElement>){event.preventDefault();const form=new FormData(event.currentTarget);const response=await fetch(`${API}/api/v1/auth/mfa/challenge`,{method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({challenge_token:challenge,code:form.get("code")})});if(!response.ok)return setError("Código inválido o desafío vencido");done((await response.json()).access_token);}
  if(challenge)return <main className="login"><form onSubmit={verify}><p className="eyebrow">VERIFICACIÓN MFA</p><h1>Código de seguridad</h1><p>Ingresa el código de tu aplicación autenticadora o un código de recuperación.</p><label>Código<input name="code" autoComplete="one-time-code" autoFocus required/></label>{error&&<p className="error">{error}</p>}<button>Verificar</button><button className="secondary" type="button" onClick={()=>{setChallenge("");setError("");}}>Cancelar</button></form></main>;
  return <main className="login"><form onSubmit={submit}><p className="eyebrow">OPENRM</p><h1>Expediente clínico</h1><label>Correo<input name="email" type="email" defaultValue="admin@example.com" required/></label><label>Contraseña<input name="password" type="password" defaultValue="change-me-now" required/></label>{error&&<p className="error">{error}</p>}<button>Ingresar</button><a className="auth-link" href="/reset-password">Olvidé mi contraseña</a></form></main>;
}

function PasswordRecovery(){
  const token=new URLSearchParams(window.location.search).get("token"); const [message,setMessage]=useState(""); const [error,setError]=useState("");
  async function submit(event:FormEvent<HTMLFormElement>){event.preventDefault();setError("");const form=new FormData(event.currentTarget);const path=token?"confirm":"request";const body=token?{token,new_password:form.get("password")}:{email:form.get("email")};const response=await fetch(`${API}/api/v1/auth/password-reset/${path}`,{method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});if(!response.ok){const data=await response.json().catch(()=>null);return setError(data?.detail??"No se pudo completar la solicitud");}setMessage(token?"Contraseña actualizada. Ya puedes iniciar sesión.":"Si la cuenta existe, recibirás instrucciones de recuperación.");}
  return <main className="login"><form onSubmit={submit}><p className="eyebrow">OPENRM</p><h1>{token?"Crear nueva contraseña":"Recuperar acceso"}</h1>{token?<label>Nueva contraseña<input name="password" type="password" minLength={12} required/></label>:<label>Correo<input name="email" type="email" required/></label>}{message&&<p className="success">{message}</p>}{error&&<p className="error">{error}</p>}<button>{token?"Guardar contraseña":"Enviar instrucciones"}</button><a className="auth-link" href="/">Volver al inicio de sesión</a></form></main>;
}

function Group({title,items}:{title:string;items:Item[]}){
  return <section className="summary-group"><h3>{title}<span>{items.length}</span></h3>{items.length?items.map(item=><article key={item.uuid}><strong>{item.title}</strong><small>{item.code||item.reaction||item.dosage||item.status}</small></article>):<p>Sin registros activos</p>}</section>;
}

function App(){
  const [token,setToken]=useState("");
  const [authReady,setAuthReady]=useState(false);
  const refreshInFlight=useRef<Promise<string|null>|null>(null);
  const [patients,setPatients]=useState<Patient[]>([]);
  const [query,setQuery]=useState("");
  const [selected,setSelected]=useState<Summary|null>(null);
  const [error,setError]=useState("");
  const [creatingPatient,setCreatingPatient]=useState(false);
  const [section,setSection]=useState<"patients"|"appointments"|"flow"|"inventory"|"communications"|"security"|"administration"|"reports">("patients");

  function refreshAccessToken(){
    if(!refreshInFlight.current)refreshInFlight.current=fetch(`${API}/api/v1/auth/refresh`,{method:"POST",credentials:"include"}).then(async response=>{if(!response.ok)return null;const body=await response.json();setToken(body.access_token);return body.access_token as string;}).finally(()=>{refreshInFlight.current=null;});
    return refreshInFlight.current;
  }
  const api=createApiClient({baseUrl:API,getToken:()=>token,refreshAccessToken,onUnauthorized:()=>setToken("")});
  async function logout(){try{await api("/api/v1/auth/logout",{method:"POST"});}finally{setToken("");}}
  async function loadPatients(search=query){setPatients((await api(`/api/v1/patients?q=${encodeURIComponent(search)}`)).items);}
  async function createPatient(patient:PatientInput){
    setError("");
    try{await api("/api/v1/patients",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(patient)});setCreatingPatient(false);await loadPatients("");}
    catch(reason){setError(reason instanceof Error?reason.message:"No se pudo guardar el paciente");}
  }
  async function openPatient(patient:Patient){
    setError("");
    const [summary,labOrders,documents,coverages,charges,claims,immunizations,vitals,prescriptions,clinicalForms]=await Promise.all([api(`/api/v1/patients/${patient.uuid}/summary`),api(`/api/v1/patients/${patient.uuid}/lab-orders`),api(`/api/v1/patients/${patient.uuid}/documents`),api(`/api/v1/patients/${patient.uuid}/coverages`),api(`/api/v1/patients/${patient.uuid}/charges`),api(`/api/v1/patients/${patient.uuid}/claims`),api(`/api/v1/patients/${patient.uuid}/immunizations`),api(`/api/v1/patients/${patient.uuid}/vitals`),api(`/api/v1/patients/${patient.uuid}/prescriptions`),api(`/api/v1/patients/${patient.uuid}/clinical-forms`)]);
    const labResults=(await Promise.all((labOrders as LabOrder[]).map(order=>api<{results:LabResult[]}>(`/api/v1/lab-orders/${order.uuid}`)))).flatMap(order=>order.results);
    setSelected({...summary,labOrders,labResults,documents,coverages,charges,claims,immunizations,vitals,prescriptions,clinicalForms});
  }
  async function addItem(event:FormEvent<HTMLFormElement>){
    event.preventDefault(); if(!selected)return; const data=new FormData(event.currentTarget);
    await api(`/api/v1/patients/${selected.patient.uuid}/clinical-items`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({category:data.get("category"),title:data.get("title")})});
    event.currentTarget.reset(); await openPatient(selected.patient);
  }
  async function addLabOrder(event:FormEvent<HTMLFormElement>){
    event.preventDefault(); if(!selected)return; const data=new FormData(event.currentTarget);
    await api(`/api/v1/patients/${selected.patient.uuid}/lab-orders`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ordered_at:new Date().toISOString(),code:data.get("code"),name:data.get("name")})});
    event.currentTarget.reset(); await openPatient(selected.patient);
  }
  async function uploadDocument(event:FormEvent<HTMLFormElement>){
    event.preventDefault(); if(!selected)return; const data=new FormData(event.currentTarget);
    await api(`/api/v1/patients/${selected.patient.uuid}/documents`,{method:"POST",body:data});
    event.currentTarget.reset(); await openPatient(selected.patient);
  }
  async function downloadDocument(document:ClinicalDocument){
    if(!selected)return;
    const response=await fetch(`${API}/api/v1/patients/${selected.patient.uuid}/documents/${document.uuid}/content`,{headers:{Authorization:`Bearer ${token}`}});
    if(!response.ok)return setError("No se pudo descargar el documento");
    const url=URL.createObjectURL(await response.blob()); const link=globalThis.document.createElement("a"); link.href=url; link.download=document.name; link.click(); URL.revokeObjectURL(url);
  }
  async function addCoverage(event:FormEvent<HTMLFormElement>){
    event.preventDefault(); if(!selected)return; const data=new FormData(event.currentTarget);
    await api(`/api/v1/patients/${selected.patient.uuid}/coverages`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({payer_name:data.get("payer_name"),policy_number:data.get("policy_number"),subscriber_name:`${selected.patient.first_name} ${selected.patient.last_name}`})});
    event.currentTarget.reset(); await openPatient(selected.patient);
  }
  async function addCharge(event:FormEvent<HTMLFormElement>){
    event.preventDefault(); if(!selected?.encounters.length)return; const data=new FormData(event.currentTarget);
    await api(`/api/v1/patients/${selected.patient.uuid}/charges`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({encounter_uuid:selected.encounters[0].uuid,code_system:"CPT",code:data.get("code"),description:data.get("description"),units:1,unit_price:data.get("unit_price")})});
    event.currentTarget.reset(); await openPatient(selected.patient);
  }
  async function createClaim(){
    if(!selected?.encounters.length||!selected.charges.length)return;
    const chargeUuids=selected.charges.filter(charge=>charge.encounter_uuid===selected.encounters[0].uuid).map(charge=>charge.uuid); if(!chargeUuids.length)return setError("No hay cargos del encuentro más reciente");
    await api(`/api/v1/patients/${selected.patient.uuid}/claims`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({encounter_uuid:selected.encounters[0].uuid,coverage_uuid:selected.coverages[0]?.uuid??null,charge_uuids:chargeUuids})});
    await openPatient(selected.patient);
  }
  async function toggleClaimRelease(item:Claim){
    if(!selected)return; await api(`/api/v1/patients/${selected.patient.uuid}/claims/${item.uuid}/release`,{method:item.released_to_patient_at?"DELETE":"POST"}); await openPatient(selected.patient);
  }
  async function signClinicalForm(item:ClinicalForm){
    if(!selected)return; const password=window.prompt("Confirma tu contraseña para firmar. La firma bloqueará el formulario.");if(!password)return;
    try{await api(`/api/v1/patients/${selected.patient.uuid}/clinical-forms/${item.uuid}/sign`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password,lock:true,attestation:"I attest that this clinical record is accurate and complete."})});await openPatient(selected.patient);}catch(reason){setError(reason instanceof Error?reason.message:"No se pudo firmar el formulario");}
  }
  async function signEncounter(item:EncounterSummary){if(!selected)return;const password=window.prompt("Confirma tu contraseña para firmar y bloquear todo el encuentro.");if(!password)return;try{await api(`/api/v1/patients/${selected.patient.uuid}/encounters/${item.uuid}/sign`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password,lock:true,attestation:"I attest that this encounter is accurate and complete."})});await openPatient(selected.patient);}catch(reason){setError(reason instanceof Error?reason.message:"No se pudo firmar el encuentro");}}
  async function toggleDocumentRelease(item:ClinicalDocument){
    if(!selected)return; await api(`/api/v1/patients/${selected.patient.uuid}/documents/${item.uuid}/release`,{method:item.released_to_patient_at?"DELETE":"POST"}); await openPatient(selected.patient);
  }
  async function toggleFormRelease(item:ClinicalForm){
    if(!selected)return; await api(`/api/v1/patients/${selected.patient.uuid}/clinical-forms/${item.uuid}/release`,{method:item.released_to_patient_at?"DELETE":"POST"}); await openPatient(selected.patient);
  }
  async function releaseLabResults(order:LabOrder){
    if(!selected)return; try{await api(`/api/v1/lab-orders/${order.uuid}/release-results`,{method:"POST"});}catch(reason){setError(reason instanceof Error?reason.message:"No se pudieron publicar los resultados");}
  }
  useEffect(()=>{if(token){setAuthReady(true);return;}void refreshAccessToken().finally(()=>setAuthReady(true));},[]);
  useEffect(()=>{if(token)void loadPatients("");},[token]);
  if(!authReady)return <main className="login"><p>Verificando sesión…</p></main>;
  if(!token)return <Login done={setToken}/>;
  return <div className="shell">
    <aside><div className="brand">OR</div><nav><button className={section==="patients"?"active":""} onClick={()=>setSection("patients")}>Pacientes</button><button className={section==="appointments"?"active":""} onClick={()=>setSection("appointments")}>Agenda</button><button className={section==="flow"?"active":""} onClick={()=>setSection("flow")}>Flujo</button><button className={section==="inventory"?"active":""} onClick={()=>setSection("inventory")}>Inventario</button><button className={section==="communications"?"active":""} onClick={()=>setSection("communications")}>Mensajes</button><button className={section==="reports"?"active":""} onClick={()=>setSection("reports")}>Reportes</button><button className={section==="administration"?"active":""} onClick={()=>setSection("administration")}>Administración</button><button className={section==="security"?"active":""} onClick={()=>setSection("security")}>Seguridad</button></nav><button className="logout" onClick={()=>void logout()}>Salir</button></aside>
    <main><header><div><p className="eyebrow">ATENCIÓN CLÍNICA</p><h1>{section==="patients"?"Pacientes":section==="appointments"?"Agenda":section==="flow"?"Flujo de pacientes":section==="inventory"?"Inventario":section==="communications"?"Mensajes seguros":section==="security"?"Seguridad":section==="reports"?"Reportes":"Administración"}</h1></div>{section==="patients"&&<button onClick={()=>setCreatingPatient(true)}>Nuevo paciente</button>}</header>
      {error&&<p className="error">{error}</p>}
      {section==="appointments"?<AppointmentBoard api={api} patients={patients}/>:section==="flow"?<PatientFlowBoard api={api}/>:section==="inventory"?<InventoryWorkspace api={api}/>:section==="communications"?<CommunicationWorkspace api={api} patients={patients}/>:section==="security"?<SecurityWorkspace api={api}/>:section==="administration"?<AdministrationWorkspace api={api}/>:section==="reports"?<ReportWorkspace api={api}/>:<>{creatingPatient&&<PatientForm onSubmit={createPatient} onCancel={()=>setCreatingPatient(false)}/>}
      <div className={selected?"workspace detail-open":"workspace"}><section className="card">
        <div className="toolbar"><input aria-label="Buscar pacientes" placeholder="Buscar por nombre o correo" value={query} onChange={event=>setQuery(event.target.value)} onKeyDown={event=>event.key==="Enter"&&void loadPatients()}/><span>{patients.length} resultados</span></div>
        <table><thead><tr><th>Paciente</th><th>Fecha de nacimiento</th><th>Sexo</th><th>Correo</th></tr></thead><tbody>{patients.map(patient=><tr className="patient-row" key={patient.uuid} onClick={()=>void openPatient(patient)}><td><strong>{patient.last_name}, {patient.first_name}</strong><small>{patient.uuid.slice(0,8)}</small></td><td>{patient.date_of_birth}</td><td>{patient.sex}</td><td>{patient.email??"—"}</td></tr>)}</tbody></table>
        {!patients.length&&<div className="empty">No hay pacientes que mostrar.</div>}
      </section>{selected&&<aside className="patient-drawer">
        <button className="close" onClick={()=>setSelected(null)}>×</button><p className="eyebrow">RESUMEN CLÍNICO</p><h2>{selected.patient.first_name} {selected.patient.last_name}</h2><p>{selected.patient.date_of_birth} · {selected.patient.sex}</p>
        <PatientReportButton api={api} patientUuid={selected.patient.uuid}/>
        <PatientPhotos api={api} patientUuid={selected.patient.uuid}/>
        <PatientContacts api={api} patientUuid={selected.patient.uuid}/>
        <PatientDuplicates api={api} patientUuid={selected.patient.uuid} onOpen={openPatient}/>
        <Group title="Problemas" items={selected.problems}/><Group title="Alergias" items={selected.allergies}/><Group title="Medicamentos" items={selected.medications}/>
        <section className="summary-group"><h3>Inmunizaciones<span>{selected.immunizations.length}</span></h3>{selected.immunizations.map(item=><article key={item.uuid}><strong>{item.vaccine_name}</strong><small>CVX {item.cvx_code} · {new Date(item.administered_at).toLocaleDateString()}</small></article>)}</section>
        <section className="summary-group"><h3>Signos vitales<span>{selected.vitals.length}</span></h3>{selected.vitals.slice(0,3).map(item=><article key={item.uuid}><strong>{item.systolic&&item.diastolic?`${item.systolic}/${item.diastolic} mmHg`:"Registro de vitales"}</strong><small>FC {item.heart_rate??"—"} · SpO₂ {item.oxygen_saturation??"—"}% · BMI {item.bmi??"—"}</small></article>)}</section>
        <section className="summary-group"><h3>Recetas<span>{selected.prescriptions.length}</span></h3>{selected.prescriptions.map(item=><article key={item.uuid}><strong>{item.drug_name}</strong><small>{item.dosage_instructions} · {item.status}</small></article>)}</section>
        <section className="summary-group"><h3>Laboratorio<span>{selected.labOrders.length}</span></h3>{selected.labOrders.map(order=><article key={order.uuid}><strong>{order.name}</strong><small>{order.code} · {order.status}</small>{order.status==="complete"&&<button className="text-button" onClick={()=>void releaseLabResults(order)}>Publicar resultados finales</button>}</article>)}</section>
        <form className="quick-add compact" onSubmit={addLabOrder}><input name="code" placeholder="Código LOINC" required/><input name="name" placeholder="Estudio" required/><button>Crear orden</button></form>
        <section className="summary-group"><h3>Documentos<span>{selected.documents.length}</span></h3>{selected.documents.map(document=><article key={document.uuid}><button className="text-button" onClick={()=>void downloadDocument(document)}>{document.name}</button><small>{document.mime_type} · {document.released_to_patient_at?"Publicado en portal":"Privado"}</small><button className="text-button" onClick={()=>void toggleDocumentRelease(document)}>{document.released_to_patient_at?"Retirar del portal":"Publicar en portal"}</button></article>)}</section>
        <form className="quick-add compact" onSubmit={uploadDocument}><input name="file" type="file" required/><button>Subir documento</button></form>
        <section className="summary-group"><h3>Encuentros<span>{selected.encounters.length}</span></h3>{selected.encounters.map(encounter=><article key={encounter.uuid}><strong>{encounter.chief_complaint||"Encuentro clínico"}</strong><small>{new Date(encounter.occurred_at).toLocaleString()} · {encounter.locked?"bloqueado":"abierto"} · {encounter.signature_count} firma(s)</small>{!encounter.locked&&<button className="text-button" onClick={()=>void signEncounter(encounter)}>Firmar y bloquear encuentro</button>}</article>)}</section>
        <section className="summary-group"><h3>Formularios clínicos<span>{selected.clinicalForms.length}</span></h3>{selected.clinicalForms.map(item=><article key={item.uuid}><strong>{item.title}</strong><small>{item.form_type} · {item.status}{item.locked?" · bloqueado":""} · {item.signature_count} firma(s) · {item.released_to_patient_at?"Publicado en portal":"Privado"}</small><ClinicalFormLinks api={api} patientUuid={selected.patient.uuid} formUuid={item.uuid} documents={selected.documents} results={selected.labResults} locked={item.locked}/>{item.status!=="signed"?<button className="text-button" onClick={()=>void signClinicalForm(item)}>Firmar y bloquear</button>:<button className="text-button" onClick={()=>void toggleFormRelease(item)}>{item.released_to_patient_at?"Retirar del portal":"Publicar en portal"}</button>}</article>)}</section>
        {selected.encounters.length>0&&<CarePlanWorkspace api={api} patientUuid={selected.patient.uuid} encounterUuid={selected.encounters[0].uuid} locked={selected.encounters[0].locked}/>}
        {selected.encounters.length>0&&!selected.encounters[0].locked&&<ClinicalFormEditor api={api} patientUuid={selected.patient.uuid} encounterUuid={selected.encounters[0].uuid} onSaved={()=>openPatient(selected.patient)}/>}
        <section className="summary-group"><h3>Coberturas<span>{selected.coverages.length}</span></h3>{selected.coverages.map(coverage=><article key={coverage.uuid}><strong>{coverage.payer_name}</strong><small>{coverage.policy_number} · {coverage.priority}</small></article>)}</section>
        <form className="quick-add compact" onSubmit={addCoverage}><input name="payer_name" placeholder="Aseguradora" required/><input name="policy_number" placeholder="Póliza" required/><button>Agregar cobertura</button></form>
        <section className="summary-group"><h3>Facturación<span>{selected.claims.length}</span></h3>{selected.claims.map(claim=><article key={claim.uuid}><strong>${claim.total} · {claim.status}</strong><small>Saldo ${claim.balance} · {claim.released_to_patient_at?"Publicado en portal":"Privado"}</small><button className="text-button" onClick={()=>void toggleClaimRelease(claim)}>{claim.released_to_patient_at?"Retirar del portal":"Publicar estado de cuenta"}</button></article>)}{selected.charges.map(charge=><article key={charge.uuid}><strong>{charge.code} · ${charge.unit_price}</strong><small>Cargo sin reclamar</small></article>)}</section>
        {selected.encounters.length>0&&<form className="quick-add compact" onSubmit={addCharge}><input name="code" placeholder="Código CPT" required/><input name="description" placeholder="Descripción" required/><input name="unit_price" type="number" step="0.01" min="0.01" placeholder="Importe" required/><button>Agregar cargo</button></form>}
        {selected.charges.length>0&&<button className="wide-action" onClick={()=>void createClaim()}>Crear reclamación</button>}
        <form className="quick-add" onSubmit={addItem}><h3>Agregar al expediente</h3><select name="category"><option value="problem">Problema</option><option value="allergy">Alergia</option><option value="medication">Medicamento</option></select><input name="title" placeholder="Descripción" required/><button>Guardar</button></form>
      </aside>}</div></>}
    </main>
  </div>;
}
const root = window.location.pathname.startsWith("/portal") ? <PortalApp baseUrl={API}/> : window.location.pathname.startsWith("/reset-password") ? <PasswordRecovery/> : <App/>;
createRoot(document.getElementById("root")!).render(<React.StrictMode>{root}</React.StrictMode>);
