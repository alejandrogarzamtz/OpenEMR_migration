// @vitest-environment jsdom
import { fireEvent,render,screen,waitFor } from "@testing-library/react";
import { describe,expect,it,vi } from "vitest";
import { PatientPhotos } from "./PatientPhotos";

describe("PatientPhotos",()=>{
  it("loads the authenticated primary image and uploads a new version",async()=>{
    const rows=[{uuid:"photo-1",original_name:"portrait.png",mime_type:"image/png",sha256:"abc",size_bytes:1024,is_primary:true,active:true,created_at:"2026-01-01T00:00:00Z"}];
    const api=vi.fn((_path:string,init?:RequestInit)=>Promise.resolve(init?rows[0]:rows)) as any; api.raw=vi.fn(()=>Promise.resolve(new Response(new Blob(["image"]))));
    vi.spyOn(URL,"createObjectURL").mockReturnValue("blob:photo"); vi.spyOn(URL,"revokeObjectURL").mockImplementation(()=>{});
    render(<PatientPhotos api={api} patientUuid="patient-1"/>);
    expect((await screen.findByAltText("Fotografía principal del paciente") as HTMLImageElement).src).toContain("blob:photo");
    fireEvent.change(screen.getByLabelText("Subir fotografía del paciente"),{target:{files:[new File(["new"],"new.png",{type:"image/png"})]}});
    await waitFor(()=>expect(api.mock.calls.some((call:unknown[])=>(call[1] as RequestInit|undefined)?.method==="POST")).toBe(true));
    expect(api.raw).toHaveBeenCalledWith("/api/v1/patients/patient-1/photos/photo-1/content");
  });
});
