// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StaffEngagement } from "./StaffEngagement";

describe("StaffEngagement",()=>{
  it("assigns a questionnaire and starts a staff group thread",async()=>{
    const user={uuid:"user-1",email:"clinician@example.com",role:"clinician"};const form={uuid:"form-1",title:"PHQ-9"};const thread={uuid:"thread-1",subject:"Coordination",status:"open",participants:[user],messages:[]};
    const api=vi.fn((path:string,init?:RequestInit)=>Promise.resolve(path==="/api/v1/staff-directory"?[user]:path==="/api/v1/questionnaires"?[form]:path==="/api/v1/staff-message-threads"?(init?thread:[]):{})) as any;
    render(<StaffEngagement api={api} patients={[{uuid:"patient-1",first_name:"Ada",last_name:"Portal",date_of_birth:"1990-01-01",sex:"female",portal_allowed:true,allow_email:false,allow_sms:false}]}/>);
    fireEvent.change(await screen.findByLabelText("Questionnaire patient"),{target:{value:"patient-1"}});fireEvent.change(screen.getByLabelText("Questionnaire"),{target:{value:"form-1"}});fireEvent.click(screen.getByText("Assign"));
    await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/patients/patient-1/questionnaire-assignments",expect.objectContaining({method:"POST"})));
    fireEvent.change(screen.getByPlaceholderText("Staff subject"),{target:{value:"Coordination"}});fireEvent.change(screen.getByPlaceholderText("Message to staff"),{target:{value:"Please review"}});fireEvent.change(screen.getByLabelText("Staff participants"),{target:{value:"user-1"}});fireEvent.click(screen.getByText("Start conversation"));
    await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/staff-message-threads",expect.objectContaining({method:"POST"})));
  });
});
