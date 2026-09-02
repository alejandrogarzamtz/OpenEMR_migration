import React, { FormEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import "./clinical.css";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
type Patient = { uuid:string; first_name:string; last_name:string; date_of_birth:string; sex:string; email?:string };
type Item = { uuid:string; title:string; status:string; code?:string; reaction?:string; dosage?:string };
type LabOrder = { uuid:string; ordered_at:string; code:string; name:string; status:string };
type ClinicalDocument = { uuid:string; name:string; mime_type:string; uploaded_at:string };
type Coverage = { uuid:string; payer_name:string; policy_number:string; priority:string };
type Charge = { uuid:string; encounter_uuid:string; code:string; description:string; unit_price:string; units:number };
type Claim = { uuid:string; status:string; total:string; balance:string };
type Immunization = { uuid:string; vaccine_name:string; cvx_code:string; administered_at:string };
type Vitals = { uuid:string; observed_at:string; systolic?:string; diastolic?:string; heart_rate?:string; oxygen_saturation?:string; bmi?:string };
type Prescription = { uuid:string; drug_name:string; dosage_instructions:string; status:string };
type Summary = { patient:Patient; problems:Item[]; allergies:Item[]; medications:Item[]; encounters:{uuid:string;occurred_at:string;chief_complaint?:string}[]; labOrders:LabOrder[]; documents:ClinicalDocument[]; coverages:Coverage[]; charges:Charge[]; claims:Claim[]; immunizations:Immunization[]; vitals:Vitals[]; prescriptions:Prescription[] };

function Login({ done }:{ done:(token:string)=>void }) {
  const [error,setError]=useState("");
  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault(); const data=new FormData(event.currentTarget);
    const response=await fetch(`${API}/api/v1/auth/token`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:data.get("email"),password:data.get("password")})});
    if(!response.ok)return setError("Credenciales inválidas");
    const body=await response.json(); localStorage.setItem("token",body.access_token); done(body.access_token);
  }
  return <main className="login"><form onSubmit={submit}><p className="eyebrow">OPENEMR NEXT</p><h1>Expediente clínico</h1><label>Correo<input name="email" type="email" defaultValue="admin@example.com" required/></label><label>Contraseña<input name="password" type="password" defaultValue="change-me-now" required/></label>{error&&<p className="error">{error}</p>}<button>Ingresar</button></form></main>;
}

function Group({title,items}:{title:string;items:Item[]}){
  return <section className="summary-group"><h3>{title}<span>{items.length}</span></h3>{items.length?items.map(item=><article key={item.uuid}><strong>{item.title}</strong><small>{item.code||item.reaction||item.dosage||item.status}</small></article>):<p>Sin registros activos</p>}</section>;
}

function App(){
  const [token,setToken]=useState(localStorage.getItem("token")??"");
  const [patients,setPatients]=useState<Patient[]>([]);
  const [query,setQuery]=useState("");
  const [selected,setSelected]=useState<Summary|null>(null);
  const [error,setError]=useState("");

  async function api(path:string,init:RequestInit={}){
    const response=await fetch(`${API}${path}`,{...init,headers:{Authorization:`Bearer ${token}`,...(init.headers??{})}});
    if(response.status===401){localStorage.removeItem("token");setToken("");throw Error("Unauthorized");}
    if(!response.ok){const body=await response.json().catch(()=>({detail:"Request failed"}));throw Error(body.detail);}
    return response.json();
  }
  async function loadPatients(search=query){setPatients((await api(`/api/v1/patients?q=${encodeURIComponent(search)}`)).items);}
  async function openPatient(patient:Patient){
    setError("");
    const [summary,labOrders,documents,coverages,charges,claims,immunizations,vitals,prescriptions]=await Promise.all([api(`/api/v1/patients/${patient.uuid}/summary`),api(`/api/v1/patients/${patient.uuid}/lab-orders`),api(`/api/v1/patients/${patient.uuid}/documents`),api(`/api/v1/patients/${patient.uuid}/coverages`),api(`/api/v1/patients/${patient.uuid}/charges`),api(`/api/v1/patients/${patient.uuid}/claims`),api(`/api/v1/patients/${patient.uuid}/immunizations`),api(`/api/v1/patients/${patient.uuid}/vitals`),api(`/api/v1/patients/${patient.uuid}/prescriptions`)]);
    setSelected({...summary,labOrders,documents,coverages,charges,claims,immunizations,vitals,prescriptions});
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
  useEffect(()=>{if(token)void loadPatients("");},[token]);
  if(!token)return <Login done={setToken}/>;
  return <div className="shell">
    <aside><div className="brand">OE</div><nav><a className="active">Pacientes</a><a>Agenda</a><a>Encuentros</a><a>Reportes</a></nav><button className="logout" onClick={()=>{localStorage.removeItem("token");setToken("");}}>Salir</button></aside>
    <main><header><div><p className="eyebrow">ATENCIÓN CLÍNICA</p><h1>Pacientes</h1></div></header>
      {error&&<p className="error">{error}</p>}
      <div className={selected?"workspace detail-open":"workspace"}><section className="card">
        <div className="toolbar"><input aria-label="Buscar pacientes" placeholder="Buscar por nombre o correo" value={query} onChange={event=>setQuery(event.target.value)} onKeyDown={event=>event.key==="Enter"&&void loadPatients()}/><span>{patients.length} resultados</span></div>
        <table><thead><tr><th>Paciente</th><th>Fecha de nacimiento</th><th>Sexo</th><th>Correo</th></tr></thead><tbody>{patients.map(patient=><tr className="patient-row" key={patient.uuid} onClick={()=>void openPatient(patient)}><td><strong>{patient.last_name}, {patient.first_name}</strong><small>{patient.uuid.slice(0,8)}</small></td><td>{patient.date_of_birth}</td><td>{patient.sex}</td><td>{patient.email??"—"}</td></tr>)}</tbody></table>
        {!patients.length&&<div className="empty">No hay pacientes que mostrar.</div>}
      </section>{selected&&<aside className="patient-drawer">
        <button className="close" onClick={()=>setSelected(null)}>×</button><p className="eyebrow">RESUMEN CLÍNICO</p><h2>{selected.patient.first_name} {selected.patient.last_name}</h2><p>{selected.patient.date_of_birth} · {selected.patient.sex}</p>
        <Group title="Problemas" items={selected.problems}/><Group title="Alergias" items={selected.allergies}/><Group title="Medicamentos" items={selected.medications}/>
        <section className="summary-group"><h3>Inmunizaciones<span>{selected.immunizations.length}</span></h3>{selected.immunizations.map(item=><article key={item.uuid}><strong>{item.vaccine_name}</strong><small>CVX {item.cvx_code} · {new Date(item.administered_at).toLocaleDateString()}</small></article>)}</section>
        <section className="summary-group"><h3>Signos vitales<span>{selected.vitals.length}</span></h3>{selected.vitals.slice(0,3).map(item=><article key={item.uuid}><strong>{item.systolic&&item.diastolic?`${item.systolic}/${item.diastolic} mmHg`:"Registro de vitales"}</strong><small>FC {item.heart_rate??"—"} · SpO₂ {item.oxygen_saturation??"—"}% · BMI {item.bmi??"—"}</small></article>)}</section>
        <section className="summary-group"><h3>Recetas<span>{selected.prescriptions.length}</span></h3>{selected.prescriptions.map(item=><article key={item.uuid}><strong>{item.drug_name}</strong><small>{item.dosage_instructions} · {item.status}</small></article>)}</section>
        <section className="summary-group"><h3>Laboratorio<span>{selected.labOrders.length}</span></h3>{selected.labOrders.map(order=><article key={order.uuid}><strong>{order.name}</strong><small>{order.code} · {order.status}</small></article>)}</section>
        <form className="quick-add compact" onSubmit={addLabOrder}><input name="code" placeholder="Código LOINC" required/><input name="name" placeholder="Estudio" required/><button>Crear orden</button></form>
        <section className="summary-group"><h3>Documentos<span>{selected.documents.length}</span></h3>{selected.documents.map(document=><article key={document.uuid}><button className="text-button" onClick={()=>void downloadDocument(document)}>{document.name}</button><small>{document.mime_type}</small></article>)}</section>
        <form className="quick-add compact" onSubmit={uploadDocument}><input name="file" type="file" required/><button>Subir documento</button></form>
        <section className="summary-group"><h3>Encuentros<span>{selected.encounters.length}</span></h3>{selected.encounters.map(encounter=><article key={encounter.uuid}><strong>{encounter.chief_complaint||"Encuentro clínico"}</strong><small>{new Date(encounter.occurred_at).toLocaleString()}</small></article>)}</section>
        <section className="summary-group"><h3>Coberturas<span>{selected.coverages.length}</span></h3>{selected.coverages.map(coverage=><article key={coverage.uuid}><strong>{coverage.payer_name}</strong><small>{coverage.policy_number} · {coverage.priority}</small></article>)}</section>
        <form className="quick-add compact" onSubmit={addCoverage}><input name="payer_name" placeholder="Aseguradora" required/><input name="policy_number" placeholder="Póliza" required/><button>Agregar cobertura</button></form>
        <section className="summary-group"><h3>Facturación<span>{selected.claims.length}</span></h3>{selected.claims.map(claim=><article key={claim.uuid}><strong>${claim.total} · {claim.status}</strong><small>Saldo ${claim.balance}</small></article>)}{selected.charges.map(charge=><article key={charge.uuid}><strong>{charge.code} · ${charge.unit_price}</strong><small>Cargo sin reclamar</small></article>)}</section>
        {selected.encounters.length>0&&<form className="quick-add compact" onSubmit={addCharge}><input name="code" placeholder="Código CPT" required/><input name="description" placeholder="Descripción" required/><input name="unit_price" type="number" step="0.01" min="0.01" placeholder="Importe" required/><button>Agregar cargo</button></form>}
        {selected.charges.length>0&&<button className="wide-action" onClick={()=>void createClaim()}>Crear reclamación</button>}
        <form className="quick-add" onSubmit={addItem}><h3>Agregar al expediente</h3><select name="category"><option value="problem">Problema</option><option value="allergy">Alergia</option><option value="medication">Medicamento</option></select><input name="title" placeholder="Descripción" required/><button>Guardar</button></form>
      </aside>}</div>
    </main>
  </div>;
}
createRoot(document.getElementById("root")!).render(<React.StrictMode><App/></React.StrictMode>);
