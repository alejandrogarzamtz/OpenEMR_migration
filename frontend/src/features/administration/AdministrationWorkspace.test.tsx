// @vitest-environment jsdom
import { cleanup,fireEvent,render,screen,waitFor } from "@testing-library/react";
import { afterEach,describe,expect,it,vi } from "vitest";
import { AdministrationWorkspace } from "./AdministrationWorkspace";

afterEach(cleanup);

describe("AdministrationWorkspace",()=>{
  it("loads facilities, warehouses, and practitioners",async()=>{
    const api=vi.fn().mockResolvedValueOnce([{uuid:"f1",name:"North Clinic",active:true}]).mockResolvedValueOnce([{uuid:"w1",code:"north",name:"North Pharmacy",facility_uuid:"f1",active:true}]).mockResolvedValueOnce([{uuid:"p1",first_name:"Ana",last_name:"Rivera",specialty:"Family Medicine",primary_facility_uuid:"f1",calendar_enabled:true,active:true}]).mockResolvedValueOnce([{uuid:"e1",name:"Medical Library",url_template:"https://example.org/?q=[%]",sequence:1,active:true}]).mockResolvedValueOnce([{uuid:"s1",client_id:"analytics",name:"Analytics",allowed_scopes:["system/Patient.rs"],active:true,created_at:"2026-09-15"}]);
    render(<AdministrationWorkspace api={api}/>);
    expect((await screen.findAllByText("North Clinic")).length).toBeGreaterThan(0);expect(screen.getByText("North Pharmacy")).toBeTruthy();expect(screen.getByText("Rivera, Ana")).toBeTruthy();
    expect(screen.getByText("Medical Library")).toBeTruthy();expect(screen.getByText("Analytics")).toBeTruthy();await waitFor(()=>expect(api).toHaveBeenCalledTimes(5));
  });
  it("registers an asymmetric SMART backend client",async()=>{
    const api=vi.fn();[[],[],[],[],[]].forEach(value=>api.mockResolvedValueOnce(value));api.mockResolvedValueOnce({uuid:"s2"});[[],[],[],[],[]].forEach(value=>api.mockResolvedValueOnce(value));render(<AdministrationWorkspace api={api}/>);await screen.findByText("SMART backend clients");fireEvent.change(screen.getByPlaceholderText("Client name"),{target:{value:"Warehouse analytics"}});fireEvent.change(screen.getByLabelText("Public JWKS"),{target:{value:'{"keys":[{"kty":"RSA","kid":"one"}]}'}});fireEvent.change(screen.getByLabelText("Allowed SMART scopes"),{target:{value:"system/Patient.rs system/Observation.rs"}});fireEvent.click(screen.getByText("Register SMART client"));await waitFor(()=>expect(api).toHaveBeenCalledTimes(11));const request=JSON.parse(String(api.mock.calls[5][1].body));expect(request.allowed_scopes).toEqual(["system/Patient.rs","system/Observation.rs"]);expect(request.jwks.keys[0].kid).toBe("one");
  });
});
