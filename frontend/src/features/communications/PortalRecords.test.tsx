// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ApiRequest } from "../../api/client";
import { PortalRecords } from "./PortalRecords";

describe("PortalRecords",()=>{
  it("shows only the records returned by the isolated portal API and downloads documents",async()=>{
    URL.createObjectURL=vi.fn(()=>"blob:test"); URL.revokeObjectURL=vi.fn();
    const raw=vi.fn().mockResolvedValue(new Response(new Blob(["instructions"])));
    const api=vi.fn((path:string)=>Promise.resolve(path.endsWith("appointments")?[{uuid:"a1",starts_at:"2026-10-01T14:00:00Z",status:"scheduled",title:"Follow-up"}]:path.endsWith("results")?[{uuid:"r1",order_name:"CBC",name:"Hemoglobin",value:"14.1",unit:"g/dL",observed_at:"2026-09-15T12:00:00Z"}]:path.endsWith("documents")?[{uuid:"d1",name:"instructions.txt",mime_type:"text/plain",uploaded_at:"2026-09-15T12:00:00Z"}]:path.endsWith("forms")?[{uuid:"f1",title:"Visit summary",form_type:"soap",content:{plan:"Hydrate"},signed_at:"2026-09-15T12:00:00Z"}]:path.endsWith("statement")?{currency:"USD",payments_available:false,total_charges:"20.00",total_paid:"10.00",balance:"10.00",claims:[{uuid:"c1",status:"submitted",total:"20.00",paid:"10.00",balance:"10.00",created_at:"2026-09-15T12:00:00Z",payments:[]}]}:[])) as unknown as ApiRequest;
    api.raw=raw;
    render(<PortalRecords api={api}/>);
    expect(await screen.findByText("Hemoglobin")).toBeTruthy();
    expect(screen.getByText("Follow-up")).toBeTruthy();
    expect(screen.getByText(/plan: Hydrate/)).toBeTruthy();
    expect(screen.getByText("USD 10.00")).toBeTruthy();
    expect(screen.getByText(/Online payments are not configured/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button",{name:"instructions.txt"}));
    await waitFor(()=>expect(raw).toHaveBeenCalledWith("/api/v1/portal/documents/d1/content"));
  });
});
