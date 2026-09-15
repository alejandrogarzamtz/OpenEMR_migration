// @vitest-environment jsdom
import { cleanup,fireEvent,render,screen,waitFor } from "@testing-library/react";
import { afterEach,describe,expect,it,vi } from "vitest";
import { SmartAuthorizeApp } from "./SmartAuthorizeApp";

afterEach(()=>{cleanup();vi.unstubAllGlobals();window.history.replaceState({},"","/");});

describe("SmartAuthorizeApp",()=>{
  it("authenticates, displays scopes and approves a patient context",async()=>{
    window.history.replaceState({},"","/smart/authorize?request=opaque-request");const navigate=vi.fn();const fetchMock=vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({client_name:"Trusted App",client_id:"trusted",scopes:["patient/Patient.rs","openid"],identity_kind:"staff",patient_context_required:true,expires_at:"2026-09-15T12:00:00Z"}),{status:200,headers:{"Content-Type":"application/json"}}))
      .mockResolvedValueOnce(new Response(JSON.stringify({access_token:"staff-token",mfa_required:false}),{status:200,headers:{"Content-Type":"application/json"}}))
      .mockResolvedValueOnce(new Response(JSON.stringify({identity_kind:"staff",patients:[{uuid:"p1",name:"Alex Patient"}],fixed_patient:false}),{status:200,headers:{"Content-Type":"application/json"}}))
      .mockResolvedValueOnce(new Response(JSON.stringify({redirect_to:"https://app.example.org/callback?code=one&state=two"}),{status:200,headers:{"Content-Type":"application/json"}}));vi.stubGlobal("fetch",fetchMock);
    render(<SmartAuthorizeApp baseUrl="http://localhost:8000" navigate={navigate}/>);expect(await screen.findByText("Authorize Trusted App")).toBeTruthy();fireEvent.change(screen.getByLabelText("Email"),{target:{value:"clinician@example.com"}});fireEvent.change(screen.getByLabelText("Password"),{target:{value:"secret"}});fireEvent.click(screen.getByText("Continue securely"));expect(await screen.findByText("patient/Patient.rs")).toBeTruthy();expect(await screen.findByText("Alex Patient")).toBeTruthy();fireEvent.click(screen.getByText("Allow access"));await waitFor(()=>expect(navigate).toHaveBeenCalledWith("https://app.example.org/callback?code=one&state=two"));
  });
});
