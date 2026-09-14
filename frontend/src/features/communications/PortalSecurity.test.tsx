// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ApiRequest } from "../../api/client";
import { PortalSecurity } from "./PortalSecurity";

describe("PortalSecurity",()=>{
  it("enrolls and confirms portal MFA while showing one-time recovery codes",async()=>{
    const api=vi.fn().mockResolvedValueOnce({enabled:false,recovery_codes_remaining:0}).mockResolvedValueOnce({secret:"PORTALSECRET",provisioning_uri:"otpauth://portal"}).mockResolvedValueOnce({recovery_codes:["AAAA-BBBB"]}).mockResolvedValueOnce({enabled:true,method:"totp",recovery_codes_remaining:10}) as unknown as ApiRequest;
    render(<PortalSecurity api={api}/>);
    fireEvent.change(await screen.findByPlaceholderText("Current password"),{target:{value:"patient-password-123"}});fireEvent.click(screen.getByText("Set up authenticator app"));
    expect(await screen.findByText("PORTALSECRET")).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("6-digit code"),{target:{value:"123456"}});fireEvent.click(screen.getByText("Confirm MFA"));
    expect(await screen.findByText("AAAA-BBBB")).toBeTruthy();
    await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/portal/mfa/confirm",expect.objectContaining({method:"POST"})));
  });
});
