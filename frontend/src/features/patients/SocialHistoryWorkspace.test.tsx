// @vitest-environment jsdom
import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import {describe,expect,it,vi} from "vitest";
import {SocialHistoryWorkspace} from "./SocialHistoryWorkspace";

describe("SocialHistoryWorkspace",()=>{it("lists versions and records a new social history",async()=>{
  let items:any[]=[{uuid:"h1",recorded_at:"2034-01-02T10:00:00Z",tobacco:"Never",alcohol:"Occasional"}];
  const api=vi.fn(async(_path:string,init?:RequestInit)=>{if(init?.method==="POST"){const body=JSON.parse(String(init.body));items=[{uuid:"h2",recorded_at:"2034-02-03T10:00:00Z",...body},...items];return items[0];}return items;}) as any;
  render(<SocialHistoryWorkspace api={api} patientUuid="patient-1"/>);await screen.findByText("Never");fireEvent.click(screen.getByText("Nueva versión"));fireEvent.change(screen.getByLabelText("Tabaco"),{target:{value:"Former"}});fireEvent.change(screen.getByLabelText("Ejercicio"),{target:{value:"Walks daily"}});fireEvent.click(screen.getByText("Registrar historia"));await screen.findByText("Former");await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/patients/patient-1/social-history",expect.objectContaining({method:"POST"})));expect(screen.getAllByText(/Historia social/).length).toBeGreaterThan(0);
});});
