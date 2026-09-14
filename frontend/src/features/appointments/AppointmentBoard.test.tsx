// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppointmentBoard } from "./AppointmentBoard";

describe("AppointmentBoard",()=>{
  it("loads appointments and resolves patient names",async()=>{
    const api=vi.fn().mockResolvedValue([{uuid:"a1",patient_uuid:"p1",starts_at:"2026-10-01T15:00:00Z",ends_at:"2026-10-01T15:30:00Z",status:"scheduled",provider_name:"Dr. Rivera"}]);
    render(<AppointmentBoard api={api} patients={[{uuid:"p1",first_name:"Alex",last_name:"Rivera",date_of_birth:"1992-06-10",sex:"female",portal_allowed:false,allow_email:false,allow_sms:false}]}/>);
    await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/appointments"));
    expect(screen.getByText("Rivera")).toBeTruthy();expect(screen.getByText("Dr. Rivera")).toBeTruthy();
  });
});

