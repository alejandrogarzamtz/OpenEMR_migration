// @vitest-environment jsdom
import { fireEvent,render,screen,waitFor } from "@testing-library/react";
import { describe,expect,it,vi } from "vitest";
import type { ApiRequest } from "../../api/client";
import { CarePlanWorkspace } from "./CarePlanWorkspace";

describe("CarePlanWorkspace",()=>{
  it("creates, updates and inactivates a patient-scoped care plan",async()=>{
    let plans:any[]=[];
    const api=vi.fn(async (_path:string,init?:RequestInit)=>{if(init?.method==="POST"){const body=JSON.parse(String(init.body));plans=[{...body,uuid:"plan-1",active:true,created_at:body.recorded_at,updated_at:body.recorded_at}];return plans[0];}if(init?.method==="PUT"){plans=[{...plans[0],...JSON.parse(String(init.body))}];return plans[0];}if(init?.method==="DELETE"){plans=[];return undefined;}return plans;}) as unknown as ApiRequest;
    vi.spyOn(window,"prompt").mockReturnValue("Plan superseded");render(<CarePlanWorkspace api={api} patientUuid="patient-1" encounterUuid="encounter-1"/>);
    fireEvent.click(screen.getByText("Nuevo plan de cuidado"));fireEvent.change(screen.getByLabelText("Registrado"),{target:{value:"2026-09-14T12:00"}});fireEvent.change(screen.getByLabelText("Código"),{target:{value:"SNOMED:123"}});fireEvent.change(screen.getByLabelText("Descripción del código"),{target:{value:"Mobility plan"}});fireEvent.change(screen.getByLabelText("Descripción"),{target:{value:"Walk daily"}});fireEvent.click(screen.getByText("Agregar plan"));
    await screen.findByText("Walk daily");expect(api).toHaveBeenCalledWith("/api/v1/patients/patient-1/care-plans",expect.objectContaining({method:"POST"}));
    fireEvent.change(screen.getByLabelText("Estado Walk daily"),{target:{value:"active"}});await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/patients/patient-1/care-plans/plan-1",expect.objectContaining({method:"PUT"})));
    fireEvent.click(screen.getByText("Inactivar"));await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/patients/patient-1/care-plans/plan-1?reason=Plan%20superseded",{method:"DELETE"}));
  });
});
