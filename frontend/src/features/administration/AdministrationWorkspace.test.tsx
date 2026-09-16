// @vitest-environment jsdom
import { cleanup,fireEvent,render,screen,waitFor } from "@testing-library/react";
import { afterEach,describe,expect,it,vi } from "vitest";
import { AdministrationWorkspace } from "./AdministrationWorkspace";

afterEach(cleanup);

describe("AdministrationWorkspace",()=>{
  it("loads facilities, warehouses, and practitioners",async()=>{
    const api=vi.fn().mockResolvedValueOnce([{uuid:"f1",name:"North Clinic",active:true}]).mockResolvedValueOnce([{uuid:"w1",code:"north",name:"North Pharmacy",facility_uuid:"f1",active:true}]).mockResolvedValueOnce([{uuid:"p1",first_name:"Ana",last_name:"Rivera",specialty:"Family Medicine",primary_facility_uuid:"f1",calendar_enabled:true,active:true}]).mockResolvedValueOnce([{uuid:"e1",name:"Medical Library",url_template:"https://example.org/?q=[%]",sequence:1,active:true}]).mockResolvedValueOnce([{uuid:"s1",client_id:"analytics",name:"Analytics",client_kind:"backend",redirect_uris:[],launch_types:[],allowed_scopes:["system/Patient.rs"],active:true,created_at:"2026-09-15"}]).mockResolvedValueOnce([{uuid:"u1",email:"clinician@example.com",role:"clinician",active:true,permissions:["patients:demo:read"]}]).mockResolvedValueOnce([{uuid:"g1",key:"organization.name",category:"organization",value_type:"string",value:"OpenRM",description:"Application name",version:1}]).mockResolvedValueOnce([{uuid:"l1",code:"en",name:"English",rtl:false,active:true}]).mockResolvedValueOnce([{uuid:"t1",key:"patient-letter",locale_code:"en",version:1,name:"Patient letter",category:"document",content:"Hello",content_type:"text/plain",allowed_variables:[],active:true}]).mockResolvedValueOnce({extensions:[{uuid:"x1",key:"lab-bridge",name:"Lab Bridge",version:"1.0.0",status:"enabled",manifest:{events:[]}}],subscriptions:[],deliveries:[]});
    render(<AdministrationWorkspace api={api}/>);
    expect((await screen.findAllByText("North Clinic")).length).toBeGreaterThan(0);expect(screen.getByText("North Pharmacy")).toBeTruthy();expect(screen.getByText("Rivera, Ana")).toBeTruthy();
    expect(screen.getByText("organization.name")).toBeTruthy();await waitFor(()=>expect(api).toHaveBeenCalledTimes(10));
    fireEvent.click(screen.getByRole("button",{name:/Access/}));expect(screen.getByText("Analytics")).toBeTruthy();expect(screen.getByText("clinician@example.com")).toBeTruthy();
    fireEvent.click(screen.getByRole("button",{name:/Content/}));expect(screen.getByText("Medical Library")).toBeTruthy();expect(screen.getByText("Patient letter")).toBeTruthy();
    fireEvent.click(screen.getByRole("button",{name:/Integrations/}));expect(screen.getAllByText("Lab Bridge").length).toBeGreaterThan(0);
  });
  it("registers an asymmetric SMART backend client",async()=>{
    const api=vi.fn();[[],[],[],[],[],[],[],[],[],{extensions:[],subscriptions:[],deliveries:[]}].forEach(value=>api.mockResolvedValueOnce(value));api.mockResolvedValueOnce({uuid:"s2"});[[],[],[],[],[],[],[],[],[],{extensions:[],subscriptions:[],deliveries:[]}].forEach(value=>api.mockResolvedValueOnce(value));render(<AdministrationWorkspace api={api}/>);await screen.findByRole("button",{name:/Access/});fireEvent.click(screen.getByRole("button",{name:/Access/}));await screen.findByText("SMART applications");fireEvent.change(screen.getByPlaceholderText("Client name"),{target:{value:"Warehouse analytics"}});fireEvent.change(screen.getByLabelText("Public JWKS"),{target:{value:'{"keys":[{"kty":"RSA","kid":"one"}]}'}});fireEvent.change(screen.getByLabelText("Allowed SMART scopes"),{target:{value:"system/Patient.rs system/Observation.rs"}});fireEvent.click(screen.getByText("Register SMART application"));await waitFor(()=>expect(api).toHaveBeenCalledTimes(21));const request=JSON.parse(String(api.mock.calls[10][1].body));expect(request.allowed_scopes).toEqual(["system/Patient.rs","system/Observation.rs"]);expect(request.jwks.keys[0].kid).toBe("one");expect(request.client_kind).toBe("backend");
  });
});
