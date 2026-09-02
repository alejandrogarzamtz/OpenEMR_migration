import React, { FormEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
type Patient = { uuid:string; first_name:string; last_name:string; date_of_birth:string; sex:string; email?:string };

function App() {
  const [token, setToken] = useState(localStorage.getItem("token") ?? "");
  const [patients, setPatients] = useState<Patient[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  async function login(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const data = new FormData(e.currentTarget);
    const response = await fetch(`${API}/api/v1/auth/token`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({email:data.get("email"), password:data.get("password")})});
    if (!response.ok) return setError("Credenciales inválidas");
    const body = await response.json(); localStorage.setItem("token", body.access_token); setToken(body.access_token);
  }
  async function load(q = query) {
    const response = await fetch(`${API}/api/v1/patients?q=${encodeURIComponent(q)}`, {headers:{Authorization:`Bearer ${token}`}});
    if (response.status === 401) { localStorage.removeItem("token"); setToken(""); return; }
    setPatients((await response.json()).items);
  }
  useEffect(() => { if (token) void load(""); }, [token]);
  if (!token) return <main className="login"><form onSubmit={login}><p className="eyebrow">OPENEMR NEXT</p><h1>Expediente clínico</h1><label>Correo<input name="email" type="email" defaultValue="admin@example.com" required /></label><label>Contraseña<input name="password" type="password" defaultValue="change-me-now" required /></label>{error && <p className="error">{error}</p>}<button>Ingresar</button></form></main>;
  return <div className="shell"><aside><div className="brand">OE</div><nav><a className="active">Pacientes</a><a>Agenda</a><a>Encuentros</a><a>Reportes</a></nav><button className="logout" onClick={() => {localStorage.removeItem("token");setToken("")}}>Salir</button></aside><main><header><div><p className="eyebrow">ATENCIÓN CLÍNICA</p><h1>Pacientes</h1></div><button>+ Nuevo paciente</button></header><section className="card"><div className="toolbar"><input aria-label="Buscar pacientes" placeholder="Buscar por nombre o correo" value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>e.key==="Enter"&&load()} /><span>{patients.length} resultados</span></div><table><thead><tr><th>Paciente</th><th>Fecha de nacimiento</th><th>Sexo</th><th>Correo</th></tr></thead><tbody>{patients.map(p=><tr key={p.uuid}><td><strong>{p.last_name}, {p.first_name}</strong><small>{p.uuid.slice(0,8)}</small></td><td>{p.date_of_birth}</td><td>{p.sex}</td><td>{p.email ?? "—"}</td></tr>)}</tbody></table>{patients.length===0&&<div className="empty">No hay pacientes que mostrar.</div>}</section></main></div>;
}
createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
