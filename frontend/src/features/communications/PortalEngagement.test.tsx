// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PortalEngagement } from "./PortalEngagement";

describe("PortalEngagement",()=>{
  it("submits assigned questionnaires and marks notifications read",async()=>{
    const assignment={uuid:"assignment-1",title:"PHQ-9",status:"assigned",questions:[{id:"q1",text:"Interest",min:0,max:3}]};
    const notice={uuid:"notice-1",event_type:"questionnaire",title:"New questionnaire",body:"Ready",created_at:"2026-01-01T00:00:00Z"};
    const preferences={email_enabled:false,sms_enabled:false,in_app_enabled:true,message_events:true,appointment_events:true,result_events:true,questionnaire_events:true,timezone_name:"UTC"};
    const api=vi.fn((path:string)=>Promise.resolve(path.includes("questionnaires")?[assignment]:path.includes("notification-preferences")?preferences:[notice])) as any;
    render(<PortalEngagement api={api} patientUuid="patient-1" scopes={["questionnaires","notifications"]}/>);
    fireEvent.change(await screen.findByLabelText("Interest"),{target:{value:"1"}});fireEvent.click(screen.getByText("Submit questionnaire"));
    await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/portal/questionnaires/assignment-1/responses",expect.objectContaining({method:"POST",body:JSON.stringify({answers:{q1:1}})})));
    fireEvent.click(await screen.findByText("Mark as read"));await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/portal/notifications/notice-1/read",expect.objectContaining({method:"POST"})));
  });
});
