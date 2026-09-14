// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PortalAccessManager } from "./PortalAccessManager";

describe("PortalAccessManager",()=>{
  it("creates a representative, grants scoped access, and revokes it",async()=>{
    const representative={uuid:"rep-1",username:"caregiver",display_name:"Casey Caregiver"};
    const grant={uuid:"grant-1",patient_uuid:"patient-1",representative_name:"Casey Caregiver",relationship_code:"guardian",scopes:["appointments"],consent_basis:"legal-guardian"};
    const api=vi.fn((path:string,init?:RequestInit)=>Promise.resolve(path==="/api/v1/portal-representatives"?(init?representative:[representative]):path.endsWith("/portal-access-grants")?(init?grant:[grant]):{...grant,revoked_at:"2026-09-14T12:00:00Z"})) as any;
    render(<PortalAccessManager api={api} patients={[{uuid:"patient-1",first_name:"Ada",last_name:"Portal",date_of_birth:"1990-01-01",sex:"female",portal_allowed:true,allow_email:false,allow_sms:false}]}/>);
    expect(await screen.findByRole("option",{name:"Casey Caregiver"})).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Grant patient"),{target:{value:"patient-1"}});
    await screen.findByText(/guardian · appointments/);
    fireEvent.click(screen.getByRole("button",{name:"Revoke access"}));
    await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/patients/patient-1/portal-access-grants/grant-1/revoke",expect.objectContaining({method:"POST"})));
  });
});
