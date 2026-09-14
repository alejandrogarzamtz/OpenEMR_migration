// @vitest-environment jsdom
import { fireEvent,render,screen,waitFor,within } from "@testing-library/react";
import { describe,expect,it,vi } from "vitest";
import { PatientContacts } from "./PatientContacts";

describe("PatientContacts",()=>{
  it("loads isolated contact and previous-name collections",async()=>{
    const api=vi.fn((path:string)=>Promise.resolve(path.endsWith("addresses")?[{uuid:"a",line1:"One Main",use:"home",is_primary:true,active:true}]:path.endsWith("telecoms")?[{uuid:"t",system:"sms",use:"mobile",value:"5550100",is_primary:true,active:true}]:path.endsWith("related-people")?[{uuid:"p",first_name:"Grace",last_name:"Guardian",relationship_code:"MTH",role_code:"GUARD",is_emergency_contact:true,active:true}]:path.endsWith("name-history")?[{uuid:"n",first_name:"Alicia",last_name:"Former",use:"old",period_end:"2020-01-01",reason:"Legal change"}]:path.endsWith("employments")?[{uuid:"e",employer_name:"Community Clinic",occupation_code:"RN",active:true}]:path.endsWith("consents")?[{uuid:"c",purpose:"health-information-exchange",decision:"permit",status:"active",source:"staff"}]:[{uuid:"f",field_key:"clinic_program",title:"Clinic program",data_type:1,options:[{id:"A",title:"Program A",active:true}],required:false,value:"A",value_source:"legacy"}])) as any;
    render(<PatientContacts api={api} patientUuid="patient-1"/>);
    expect(await screen.findByText(/One Main/)).toBeTruthy(); expect(screen.getByText(/sms: 5550100/)).toBeTruthy(); expect(screen.getByText(/Grace Guardian/)).toBeTruthy(); expect(screen.getByText(/Alicia Former/)).toBeTruthy(); expect(screen.getByText(/Community Clinic/)).toBeTruthy(); expect(screen.getByText(/health-information-exchange · permit/)).toBeTruthy(); expect((screen.getByLabelText("Clinic program") as HTMLSelectElement).value).toBe("A");
    expect(api).toHaveBeenCalledTimes(7); expect(api.mock.calls.every((call:unknown[])=>String(call[0]).includes("patient-1"))).toBe(true);
  });

  it("submits employment without invalid empty optional values",async()=>{
    const api=vi.fn((_path:string,options?:RequestInit)=>Promise.resolve(options?{}:[])) as any;
    const view=render(<PatientContacts api={api} patientUuid="patient-2"/>);
    const component=within(view.container);
    await component.findByText("No employment history recorded.");
    fireEvent.change(component.getByLabelText("Employer name"),{target:{value:"Health Cooperative"}});
    fireEvent.click(component.getByText("Add employment"));
    await waitFor(()=>expect(api.mock.calls.some((call:unknown[])=>Boolean(call[1]))).toBe(true));
    const post=api.mock.calls.find((call:unknown[])=>Boolean(call[1]));
    expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({employer_name:"Health Cooperative"});
  });
});
