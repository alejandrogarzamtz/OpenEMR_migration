import { ChangeEvent, useEffect, useState } from "react";
import type { ApiRequest } from "../../api/client";

type PatientPhoto={uuid:string;original_name:string;mime_type:string;sha256:string;size_bytes:number;is_primary:boolean;active:boolean;created_at:string;inactivated_reason?:string};

export function PatientPhotos({api,patientUuid}:{api:ApiRequest;patientUuid:string}){
  const [photos,setPhotos]=useState<PatientPhoto[]>([]),[imageUrl,setImageUrl]=useState(""),[error,setError]=useState("");
  async function load(){
    try{
      const rows=await api<PatientPhoto[]>(`/api/v1/patients/${patientUuid}/photos`); setPhotos(rows);
      const primary=rows.find(photo=>photo.active&&photo.is_primary);
      if(!primary||!api.raw){setImageUrl(current=>{if(current)URL.revokeObjectURL(current);return "";});return;}
      const response=await api.raw(`/api/v1/patients/${patientUuid}/photos/${primary.uuid}/content`); const next=URL.createObjectURL(await response.blob());
      setImageUrl(current=>{if(current)URL.revokeObjectURL(current);return next;});
    }catch(reason){setError(reason instanceof Error?reason.message:"No se pudieron cargar las fotografías");}
  }
  useEffect(()=>{void load();return()=>setImageUrl(current=>{if(current)URL.revokeObjectURL(current);return "";});},[patientUuid]);
  async function upload(event:ChangeEvent<HTMLInputElement>){const file=event.target.files?.[0];if(!file)return;const body=new FormData();body.append("file",file);try{await api(`/api/v1/patients/${patientUuid}/photos`,{method:"POST",body});event.target.value="";await load();}catch(reason){setError(reason instanceof Error?reason.message:"No se pudo subir la fotografía");}}
  async function action(photo:PatientPhoto,kind:"primary"|"inactivate"){try{const init:RequestInit={method:"POST"};if(kind==="inactivate"){const reason=window.prompt("Motivo de inactivación");if(!reason)return;init.headers={"Content-Type":"application/json"};init.body=JSON.stringify({reason});}await api(`/api/v1/patients/${patientUuid}/photos/${photo.uuid}/${kind}`,init);await load();}catch(reason){setError(reason instanceof Error?reason.message:"No se pudo actualizar la fotografía");}}
  return <section className="summary-group patient-photos"><h3>Fotografía<span>{photos.filter(photo=>photo.active).length}</span></h3><div className="photo-layout">{imageUrl?<img className="patient-photo" src={imageUrl} alt="Fotografía principal del paciente"/>:<div className="patient-photo-placeholder" aria-hidden="true"><span>Sin foto</span></div>}<div><p>{imageUrl?"Fotografía principal del expediente":"Sin fotografía activa."}</p><label className="file-upload-action"><strong>Subir nueva versión</strong><small>JPG, PNG o BMP</small><input aria-label="Subir fotografía del paciente" type="file" accept="image/jpeg,image/png,image/bmp" onChange={event=>void upload(event)} hidden/></label></div></div>{error&&<p className="error">{error}</p>}{photos.map(photo=><article key={photo.uuid}><strong>{photo.original_name}{photo.is_primary?" · principal":""}</strong><small>{photo.mime_type} · {(photo.size_bytes/1024).toFixed(1)} KiB · {photo.active?"activa":`inactiva${photo.inactivated_reason?` (${photo.inactivated_reason})`:""}`}</small>{photo.active&&!photo.is_primary&&<button className="text-button" onClick={()=>void action(photo,"primary")}>Usar como principal</button>}{photo.active&&<button className="text-button" onClick={()=>void action(photo,"inactivate")}>Inactivar versión</button>}</article>)}</section>;
}
