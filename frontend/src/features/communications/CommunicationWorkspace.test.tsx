// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CommunicationWorkspace } from "./CommunicationWorkspace";

describe("CommunicationWorkspace",()=>{
  it("creates and replies to patient-bound secure threads",async()=>{
    const summary={uuid:"thread-1",patient_uuid:"patient-1",patient_name:"Ada Portal",subject:"Care plan",status:"open",updated_at:"2026-01-01T00:00:00Z",messages:[]};
    const api=vi.fn((path:string,init?:RequestInit)=>Promise.resolve(path==="/api/v1/messages"?(init?[summary]:[]):["/api/v1/portal-representatives","/api/v1/staff-directory","/api/v1/questionnaires","/api/v1/staff-message-threads"].includes(path)?[]:path.endsWith("/replies")?{...summary,messages:[{uuid:"message-1",sender_kind:"staff",body:"Follow up",created_at:"2026-01-01T00:00:00Z"}]}:summary)) as any;
    render(<CommunicationWorkspace api={api} patients={[{uuid:"patient-1",first_name:"Ada",last_name:"Portal",date_of_birth:"1990-01-01",sex:"female",email:"ada@example.com",portal_allowed:true,allow_email:true,allow_sms:false}]}/>);
    fireEvent.change(screen.getByLabelText("Paciente"),{target:{value:"patient-1"}}); fireEvent.change(screen.getByPlaceholderText("Asunto"),{target:{value:"Care plan"}}); fireEvent.change(screen.getByPlaceholderText("Mensaje clínico seguro"),{target:{value:"Initial note"}}); fireEvent.click(screen.getByText("Enviar al portal"));
    expect(await screen.findByText("Ada Portal")).toBeTruthy(); fireEvent.change(screen.getByLabelText("Respuesta"),{target:{value:"Follow up"}}); fireEvent.click(screen.getByText("Responder"));
    await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/messages/thread-1/replies",expect.objectContaining({method:"POST"})));
  });
});
