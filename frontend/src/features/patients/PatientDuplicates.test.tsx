// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PatientDuplicates } from "./PatientDuplicates";

afterEach(cleanup);

describe("PatientDuplicates",()=>{
  it("shows scored candidates and opens the selected chart",async()=>{
    const patient={uuid:"duplicate-1",first_name:"Ana",last_name:"García",date_of_birth:"1980-01-01",sex:"female",portal_allowed:false,allow_email:false,allow_sms:false};
    const api=vi.fn((path:string)=>Promise.resolve(path.endsWith("/merges")?[]:[{patient,score:85,matched_fields:["date_of_birth","last_name","first_name"]}])) as any; const onOpen=vi.fn();
    render(<PatientDuplicates api={api} patientUuid="source-1" onOpen={onOpen}/>);
    expect(await screen.findByText("García, Ana")).toBeTruthy(); expect(screen.getByText(/score 85\/100/)).toBeTruthy();
    fireEvent.click(screen.getByText("Review chart")); expect(onOpen).toHaveBeenCalledWith(patient);
    await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/patients/source-1/duplicate-candidates"));
  });

  it("requires a preview, reason, and exact retained UUID before merging",async()=>{
    const source={uuid:"source-1",first_name:"Ana",last_name:"Garcia",date_of_birth:"1980-01-01",sex:"female",portal_allowed:false,allow_email:false,allow_sms:false};
    const target={...source,uuid:"11111111-1111-1111-1111-111111111111"};
    const api=vi.fn((path:string,init?:RequestInit)=>Promise.resolve(init?.method==="POST"?{uuid:"merge-1"}:path.includes("merge-preview")?{source,target,duplicate_score:85,matched_fields:["date_of_birth"],record_counts:{encounters:2},conflicts:[]}:path.endsWith("/merges")?[]:[{patient:target,score:85,matched_fields:["date_of_birth","last_name","first_name"]}])) as any; const onOpen=vi.fn();
    render(<PatientDuplicates api={api} patientUuid={source.uuid} onOpen={onOpen}/>); fireEvent.click(await screen.findByText("Prepare merge"));
    expect(await screen.findByText(/encounters: 2/)).toBeTruthy(); fireEvent.change(screen.getByLabelText("Reason"),{target:{value:"Confirmed duplicate records"}}); fireEvent.change(screen.getByLabelText("Retained chart UUID"),{target:{value:target.uuid}}); fireEvent.click(screen.getByText("Merge permanently"));
    await waitFor(()=>expect(api).toHaveBeenCalledWith(`/api/v1/patients/${source.uuid}/merge`,expect.objectContaining({method:"POST"}))); expect(onOpen).toHaveBeenCalledWith(target);
  });
});
