import { useEffect, useState } from "react";
import type { ApiRequest } from "../../api/client";

type Address={uuid:string;line1:string;city?:string;use:string;is_primary:boolean;active:boolean};
type Telecom={uuid:string;system:string;use:string;value:string;is_primary:boolean;active:boolean};
type Person={uuid:string;first_name:string;last_name:string;relationship_code:string;role_code:string;is_emergency_contact:boolean;active:boolean};

export function PatientContacts({api,patientUuid}:{api:ApiRequest;patientUuid:string}){
  const [addresses,setAddresses]=useState<Address[]>([]); const [telecoms,setTelecoms]=useState<Telecom[]>([]); const [people,setPeople]=useState<Person[]>([]);
  useEffect(()=>{void Promise.all([api<Address[]>(`/api/v1/patients/${patientUuid}/addresses`),api<Telecom[]>(`/api/v1/patients/${patientUuid}/telecoms`),api<Person[]>(`/api/v1/patients/${patientUuid}/related-people`)]).then(([a,t,p])=>{setAddresses(a);setTelecoms(t);setPeople(p);});},[patientUuid]);
  return <section className="card"><h2>Addresses and contacts</h2><h3>Addresses</h3>{addresses.map(item=><p key={item.uuid}>{item.line1}{item.city?`, ${item.city}`:""} · {item.use}{item.is_primary?" · primary":""}</p>)}<h3>Telecoms</h3>{telecoms.map(item=><p key={item.uuid}>{item.system}: {item.value} · {item.use}{item.is_primary?" · primary":""}</p>)}<h3>Related people</h3>{people.map(item=><p key={item.uuid}>{item.first_name} {item.last_name} · {item.relationship_code} / {item.role_code}{item.is_emergency_contact?" · emergency":""}</p>)}</section>;
}
