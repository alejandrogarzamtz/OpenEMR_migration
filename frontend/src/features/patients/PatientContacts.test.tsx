// @vitest-environment jsdom
import { render,screen } from "@testing-library/react";
import { describe,expect,it,vi } from "vitest";
import { PatientContacts } from "./PatientContacts";

describe("PatientContacts",()=>{
  it("loads isolated contact and previous-name collections",async()=>{
    const api=vi.fn((path:string)=>Promise.resolve(path.endsWith("addresses")?[{uuid:"a",line1:"One Main",use:"home",is_primary:true,active:true}]:path.endsWith("telecoms")?[{uuid:"t",system:"sms",use:"mobile",value:"5550100",is_primary:true,active:true}]:path.endsWith("related-people")?[{uuid:"p",first_name:"Grace",last_name:"Guardian",relationship_code:"MTH",role_code:"GUARD",is_emergency_contact:true,active:true}]:[{uuid:"n",first_name:"Alicia",last_name:"Former",use:"old",period_end:"2020-01-01",reason:"Legal change"}])) as any;
    render(<PatientContacts api={api} patientUuid="patient-1"/>);
    expect(await screen.findByText(/One Main/)).toBeTruthy(); expect(screen.getByText(/sms: 5550100/)).toBeTruthy(); expect(screen.getByText(/Grace Guardian/)).toBeTruthy(); expect(screen.getByText(/Alicia Former/)).toBeTruthy();
    expect(api).toHaveBeenCalledTimes(4); expect(api.mock.calls.every((call:unknown[])=>String(call[0]).includes("patient-1"))).toBe(true);
  });
});
