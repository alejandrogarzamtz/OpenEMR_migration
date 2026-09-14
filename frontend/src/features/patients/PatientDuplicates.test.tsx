// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PatientDuplicates } from "./PatientDuplicates";

describe("PatientDuplicates",()=>{
  it("shows scored candidates and opens the selected chart",async()=>{
    const patient={uuid:"duplicate-1",first_name:"Ana",last_name:"García",date_of_birth:"1980-01-01",sex:"female",portal_allowed:false,allow_email:false,allow_sms:false};
    const api=vi.fn().mockResolvedValue([{patient,score:85,matched_fields:["date_of_birth","last_name","first_name"]}]); const onOpen=vi.fn();
    render(<PatientDuplicates api={api} patientUuid="source-1" onOpen={onOpen}/>);
    expect(await screen.findByText("García, Ana")).toBeTruthy(); expect(screen.getByText(/score 85\/100/)).toBeTruthy();
    fireEvent.click(screen.getByText("Review chart")); expect(onOpen).toHaveBeenCalledWith(patient);
    await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/patients/source-1/duplicate-candidates"));
  });
});
