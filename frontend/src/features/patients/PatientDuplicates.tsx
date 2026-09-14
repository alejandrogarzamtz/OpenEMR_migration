import { useEffect, useState } from "react";
import type { ApiRequest } from "../../api/client";
import type { Patient } from "./types";

type Candidate={patient:Patient;score:number;matched_fields:string[]};

export function PatientDuplicates({api,patientUuid,onOpen}:{api:ApiRequest;patientUuid:string;onOpen:(patient:Patient)=>void}){
  const [items,setItems]=useState<Candidate[]>([]); const [error,setError]=useState("");
  useEffect(()=>{setItems([]);api<Candidate[]>(`/api/v1/patients/${patientUuid}/duplicate-candidates`).then(setItems).catch(reason=>setError(reason instanceof Error?reason.message:"Duplicate review could not be loaded"));},[patientUuid]);
  return <section className="summary-group duplicate-review"><h3>Possible duplicates<span>{items.length}</span></h3>{error&&<p className="error">{error}</p>}{items.map(item=><article key={item.patient.uuid}><strong>{item.patient.last_name}, {item.patient.first_name}</strong><small>{item.patient.date_of_birth} · score {item.score}/100 · {item.matched_fields.join(", ")}</small><button className="text-button" onClick={()=>onOpen(item.patient)}>Review chart</button></article>)}{!items.length&&!error&&<p>No possible duplicates detected.</p>}<p className="portal-notice">Candidates require human review. No clinical records are merged automatically.</p></section>;
}
