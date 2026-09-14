// @vitest-environment jsdom
import { fireEvent,render,screen,waitFor } from "@testing-library/react";
import { describe,expect,it,vi } from "vitest";
import { PatientReportButton } from "./PatientReportButton";

describe("PatientReportButton",()=>{
  it("opens an authenticated printable report",async()=>{
    const api=vi.fn() as any;api.raw=vi.fn(()=>Promise.resolve(new Response("<html>report</html>",{headers:{"Content-Type":"text/html"}})));
    vi.spyOn(URL,"createObjectURL").mockReturnValue("blob:report");vi.spyOn(URL,"revokeObjectURL").mockImplementation(()=>{});const popup={addEventListener:vi.fn(),print:vi.fn()} as unknown as Window;vi.spyOn(window,"open").mockReturnValue(popup);
    render(<PatientReportButton api={api} patientUuid="patient-1"/>);fireEvent.click(screen.getByText("Reporte clínico"));fireEvent.click(screen.getByText("Imprimir"));
    await waitFor(()=>expect(api.raw).toHaveBeenCalledWith("/api/v1/patients/patient-1/report.html"));expect(window.open).toHaveBeenCalledWith("blob:report","_blank","noopener,noreferrer");expect(popup.addEventListener).toHaveBeenCalled();
  });
});
