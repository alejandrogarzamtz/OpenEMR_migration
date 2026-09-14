import { useState } from "react";
import type { ApiRequest } from "../../api/client";

const groups=[
  {label:"Demografía",keys:["demographics","addresses","telecommunications","previous-names","related-people","employment"]},
  {label:"Clínica",keys:["clinical-items","prescriptions","immunizations","vitals"]},
  {label:"Encuentros",keys:["encounters","clinical-forms"]},
  {label:"Laboratorio",keys:["laboratory"]},
  {label:"Documentos",keys:["documents"]},
  {label:"Finanzas",keys:["insurance","claims"]},
];
const allKeys=groups.flatMap(group=>group.keys);

export function PatientReportButton({api,patientUuid}:{api:ApiRequest;patientUuid:string}){
  const [error,setError]=useState(""),[start,setStart]=useState(""),[end,setEnd]=useState(""),[selected,setSelected]=useState(new Set(allKeys));
  function path(extension:string){const query=new URLSearchParams();if(start)query.set("start",start);if(end)query.set("end",end);if(selected.size!==allKeys.length)query.set("sections",Array.from(selected).join(","));const suffix=query.toString();return `/api/v1/patients/${patientUuid}/report.${extension}${suffix?`?${suffix}`:""}`;}
  function toggle(keys:string[]){setSelected(current=>{const next=new Set(current);const enabled=keys.every(key=>next.has(key));for(const key of keys)enabled?next.delete(key):next.add(key);return next;});}
  async function openReport(format:"html"|"pdf"){
    try{
      setError("");if(selected.size===0)throw new Error("Selecciona al menos una sección");
      if(!api.raw)throw new Error("Authenticated report export is unavailable");
      const response=await api.raw(path(format));const url=URL.createObjectURL(await response.blob());
      if(format==="pdf"){const link=document.createElement("a");link.href=url;link.download=`patient-${patientUuid}-report.pdf`;link.click();window.setTimeout(()=>URL.revokeObjectURL(url),60_000);return;}
      const opened=window.open(url,"_blank","noopener,noreferrer");
      if(!opened){URL.revokeObjectURL(url);throw new Error("Allow pop-ups to open the printable report");}
      opened.addEventListener("load",()=>opened.print(),{once:true});
      window.setTimeout(()=>URL.revokeObjectURL(url),60_000);
    }catch(reason){setError(reason instanceof Error?reason.message:"Could not open patient report");}
  }
  return <details className="report-options"><summary>Reporte clínico</summary><div className="quick-add compact"><label>Desde<input aria-label="Reporte desde" type="date" value={start} onChange={event=>setStart(event.target.value)}/></label><label>Hasta<input aria-label="Reporte hasta" type="date" value={end} onChange={event=>setEnd(event.target.value)}/></label>{groups.map(group=><label key={group.label}><input type="checkbox" checked={group.keys.every(key=>selected.has(key))} onChange={()=>toggle(group.keys)}/>{group.label}</label>)}<button type="button" onClick={()=>void openReport("html")}>Imprimir</button><button type="button" className="secondary" onClick={()=>void openReport("pdf")}>Descargar PDF</button></div>{error&&<p className="error">{error}</p>}</details>;
}
