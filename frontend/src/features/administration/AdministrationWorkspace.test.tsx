// @vitest-environment jsdom
import { render,screen,waitFor } from "@testing-library/react";
import { describe,expect,it,vi } from "vitest";
import { AdministrationWorkspace } from "./AdministrationWorkspace";

describe("AdministrationWorkspace",()=>{
  it("loads facilities, warehouses, and practitioners",async()=>{
    const api=vi.fn().mockResolvedValueOnce([{uuid:"f1",name:"North Clinic",active:true}]).mockResolvedValueOnce([{uuid:"w1",code:"north",name:"North Pharmacy",facility_uuid:"f1",active:true}]).mockResolvedValueOnce([{uuid:"p1",first_name:"Ana",last_name:"Rivera",specialty:"Family Medicine",primary_facility_uuid:"f1",calendar_enabled:true,active:true}]).mockResolvedValueOnce([{uuid:"e1",name:"Medical Library",url_template:"https://example.org/?q=[%]",sequence:1,active:true}]);
    render(<AdministrationWorkspace api={api}/>);
    expect((await screen.findAllByText("North Clinic")).length).toBeGreaterThan(0);expect(screen.getByText("North Pharmacy")).toBeTruthy();expect(screen.getByText("Rivera, Ana")).toBeTruthy();
    expect(screen.getByText("Medical Library")).toBeTruthy();await waitFor(()=>expect(api).toHaveBeenCalledTimes(4));
  });
});
