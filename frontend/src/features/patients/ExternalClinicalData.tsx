import {useEffect,useState} from "react";
import type {ApiRequest} from "../../api/client";

type ExternalEncounter={uuid:string;occurred_on:string;diagnosis?:string;provider_name?:string;facility_name?:string;external_id?:string};
type ExternalProcedure={uuid:string;occurred_on:string;code_system?:string;code?:string;code_text?:string;facility_name?:string;external_id?:string};
type ExternalData={encounters:ExternalEncounter[];procedures:ExternalProcedure[]};

export function ExternalClinicalData({api,patientUuid}:{api:ApiRequest;patientUuid:string}){
 const [data,setData]=useState<ExternalData>({encounters:[],procedures:[]}),[error,setError]=useState("");
 useEffect(()=>{setError("");void api<ExternalData>(`/api/v1/patients/${patientUuid}/external-data`).then(setData).catch(reason=>setError(reason instanceof Error?reason.message:"Could not load external clinical data"))},[patientUuid]);
 const count=data.encounters.length+data.procedures.length;
 return <section className="summary-group"><h3>External clinical data<span>{count}</span></h3>
  {data.encounters.map(item=><article key={item.uuid}><strong>{item.diagnosis||"External encounter"}</strong><small>{item.occurred_on} · {[item.provider_name,item.facility_name].filter(Boolean).join(" · ")||"External source"}</small>{item.external_id&&<small>Source ID {item.external_id}</small>}</article>)}
  {data.procedures.map(item=><article key={item.uuid}><strong>{item.code_text||"External procedure"}</strong><small>{item.occurred_on} · {[item.code_system&&item.code?`${item.code_system}:${item.code}`:item.code,item.facility_name].filter(Boolean).join(" · ")}</small>{item.external_id&&<small>Source ID {item.external_id}</small>}</article>)}
  {!count&&!error&&<p>No external encounters or procedures.</p>}{error&&<p className="error">{error}</p>}
 </section>;
}
