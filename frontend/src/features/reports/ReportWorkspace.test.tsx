// @vitest-environment jsdom
import { fireEvent,render,screen,waitFor } from "@testing-library/react";
import { describe,expect,it,vi } from "vitest";
import { ReportWorkspace } from "./ReportWorkspace";

describe("ReportWorkspace",()=>{
  it("shows catalog status and renders a reproducible report run",async()=>{
    const api=vi.fn().mockResolvedValueOnce([{key:"appointments_report",title:"Appointments Report",category:"operations",permission:"patients:appt:read",legacy_path:"interface/reports/appointments_report.php",migrated:true},{key:"cqm",title:"Cqm",category:"clinical",permission:"patients:med:read",legacy_path:"interface/reports/cqm.php",migrated:false}]).mockResolvedValueOnce({uuid:"r1",report_key:"appointments_report",parameters:{},columns:["patient","status"],rows:[{patient:"Fixture, Report",status:"scheduled"}],totals:{appointments:1},row_count:1,checksum:"abcdef0123456789",created_at:"2026-01-01T00:00:00Z"});
    Object.assign(api,{raw:vi.fn()});
    render(<ReportWorkspace api={api}/>);fireEvent.click(await screen.findByText("Appointments Report"));fireEvent.click(screen.getByText("Run report"));
    expect(await screen.findByText("Fixture, Report")).toBeTruthy();expect(screen.getByText("1 rows")).toBeTruthy();expect(screen.getByText(/Checksum abcdef012345/)).toBeTruthy();
    await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/reports/appointments_report/runs",expect.objectContaining({method:"POST"})));
  });
});
