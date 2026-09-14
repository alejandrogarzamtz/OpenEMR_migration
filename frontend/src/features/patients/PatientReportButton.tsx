import { useState } from "react";
import type { ApiRequest } from "../../api/client";

export function PatientReportButton({api,patientUuid}:{api:ApiRequest;patientUuid:string}){
  const [error,setError]=useState("");
  async function openReport(){
    try{
      if(!api.raw)throw new Error("Authenticated report export is unavailable");
      const response=await api.raw(`/api/v1/patients/${patientUuid}/report.html`);const url=URL.createObjectURL(await response.blob());const opened=window.open(url,"_blank","noopener,noreferrer");
      if(!opened){URL.revokeObjectURL(url);throw new Error("Allow pop-ups to open the printable report");}
      opened.addEventListener("load",()=>opened.print(),{once:true});
      window.setTimeout(()=>URL.revokeObjectURL(url),60_000);
    }catch(reason){setError(reason instanceof Error?reason.message:"Could not open patient report");}
  }
  return <><button className="wide-action" onClick={()=>void openReport()}>Imprimir reporte clínico</button>{error&&<p className="error">{error}</p>}</>;
}
