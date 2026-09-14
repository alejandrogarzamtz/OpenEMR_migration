// @vitest-environment jsdom
import { fireEvent,render,screen,waitFor } from "@testing-library/react";
import { describe,expect,it,vi } from "vitest";
import { SecurityWorkspace } from "./SecurityWorkspace";

describe("SecurityWorkspace",()=>{
  it("enrolls TOTP and presents one-time recovery codes",async()=>{
    const api=vi.fn().mockResolvedValueOnce({enabled:false,recovery_codes_remaining:0}).mockResolvedValueOnce({secret:"BASE32SECRET",provisioning_uri:"otpauth://totp/OpenRM"}).mockResolvedValueOnce({recovery_codes:["AAAA-BBBB"]}).mockResolvedValueOnce({enabled:true,method:"totp",recovery_codes_remaining:10});
    render(<SecurityWorkspace api={api}/>); fireEvent.change(await screen.findByPlaceholderText("Contraseña actual"),{target:{value:"password"}}); fireEvent.click(screen.getByText("Configurar aplicación TOTP"));
    expect(await screen.findByText("BASE32SECRET")).toBeTruthy(); fireEvent.change(screen.getByPlaceholderText("Código de 6 dígitos"),{target:{value:"123456"}}); fireEvent.click(screen.getByText("Confirmar MFA"));
    expect(await screen.findByText("AAAA-BBBB")).toBeTruthy(); await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/auth/mfa/confirm",expect.objectContaining({method:"POST"})));
  });
});
