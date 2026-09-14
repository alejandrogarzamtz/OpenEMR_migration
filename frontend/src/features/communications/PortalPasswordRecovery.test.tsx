// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PortalPasswordRecovery } from "./PortalPasswordRecovery";

afterEach(()=>{vi.restoreAllMocks();window.history.replaceState({},"","/");});

describe("PortalPasswordRecovery",()=>{
  it("uses a non-enumerating email recovery request",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(null,{status:202}));
    render(<PortalPasswordRecovery baseUrl="http://api"/>);fireEvent.change(screen.getByLabelText("Email"),{target:{value:"patient@example.com"}});fireEvent.click(screen.getByText("Send instructions"));
    expect(await screen.findByText(/If the portal account exists/)).toBeTruthy();await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith("http://api/api/v1/portal/auth/password-reset/request",expect.anything()));
  });

  it("confirms a one-time token without putting it in the request body twice",async()=>{
    window.history.replaceState({},"","/portal/reset-password?token=one-time-token");const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(null,{status:204}));
    render(<PortalPasswordRecovery baseUrl="http://api"/>);fireEvent.change(screen.getByLabelText("New password"),{target:{value:"replacement-password-789"}});fireEvent.click(screen.getByText("Save password"));
    expect(await screen.findByText(/password has been changed/)).toBeTruthy();const body=JSON.parse(String(fetchMock.mock.calls[0][1]?.body));expect(body).toEqual({token:"one-time-token",new_password:"replacement-password-789"});
  });
});
