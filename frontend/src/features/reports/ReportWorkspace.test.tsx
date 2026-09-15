// @vitest-environment jsdom
import { cleanup,fireEvent,render,screen,waitFor } from "@testing-library/react";
import { afterEach,describe,expect,it,vi } from "vitest";
import { ReportWorkspace } from "./ReportWorkspace";

describe("ReportWorkspace",()=>{
  afterEach(cleanup);
  it("shows catalog status and renders a reproducible report run",async()=>{
    const api=vi.fn().mockResolvedValueOnce([{key:"appointments_report",title:"Appointments Report",category:"operations",permission:"patients:appt:read",legacy_path:"interface/reports/appointments_report.php",migrated:true},{key:"cqm",title:"Cqm",category:"clinical",permission:"patients:med:read",legacy_path:"interface/reports/cqm.php",migrated:false}]).mockResolvedValueOnce({uuid:"r1",report_key:"appointments_report",parameters:{},columns:["patient","status"],rows:[{patient:"Fixture, Report",status:"scheduled"}],totals:{appointments:1},row_count:1,checksum:"abcdef0123456789",created_at:"2026-01-01T00:00:00Z"});
    Object.assign(api,{raw:vi.fn()});
    render(<ReportWorkspace api={api}/>);fireEvent.click(await screen.findByText("Appointments Report"));fireEvent.click(screen.getByText("Run report"));
    expect(await screen.findByText("Fixture, Report")).toBeTruthy();expect(screen.getByText("1 rows")).toBeTruthy();expect(screen.getByText(/Checksum abcdef012345/)).toBeTruthy();
    await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/reports/appointments_report/runs",expect.objectContaining({method:"POST"})));
  });
  it("exposes and submits the clinical cohort dimensions",async()=>{
    const api=vi.fn().mockResolvedValueOnce([{key:"clinical_reports",title:"Clinical Reports",category:"clinical",permission:"patients:med:read",legacy_path:"interface/reports/clinical_reports.php",migrated:true}]).mockResolvedValueOnce({uuid:"r2",report_key:"clinical_reports",parameters:{},columns:["patient_name","drug"],rows:[{patient_name:"Clinical Cohort",drug:"Sumatriptan"}],totals:{patients:1},row_count:1,checksum:"abcdef0123456789",created_at:"2026-01-01T00:00:00Z"});
    render(<ReportWorkspace api={api as any}/>);fireEvent.click(await screen.findByText("Clinical Reports"));fireEvent.change(screen.getByLabelText("Drug"),{target:{value:"Suma%"}});fireEvent.click(screen.getByLabelText("Prescriptions"));fireEvent.change(screen.getByLabelText("Report option"),{target:{value:"Procedure"}});fireEvent.click(screen.getByText("Run report"));await screen.findByText("Clinical Cohort");
    const request=JSON.parse(String((api.mock.calls[1][1] as RequestInit).body));expect(request.drug_name).toBe("Suma%");expect(request.include_prescriptions).toBe(true);expect(request.clinical_type).toBe("Procedure");
  });
});
