// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PatientFlowBoard } from "./PatientFlowBoard";

describe("PatientFlowBoard",()=>{
  it("loads the board and posts a transition",async()=>{
    const episode={uuid:"flow-1",patient_name:"Rivera, Alex",started_at:"2026-10-01T15:00:00Z",current_status:"arrived",current_room:"Lobby",current_since:"2026-10-01T15:01:00Z"};
    const api=vi.fn().mockResolvedValueOnce([episode]).mockResolvedValueOnce({...episode,current_status:"in-progress"}).mockResolvedValueOnce([{...episode,current_status:"in-progress"}]);
    render(<PatientFlowBoard api={api}/>);
    expect(await screen.findByText("Rivera, Alex")).toBeTruthy();
    fireEvent.change(screen.getByRole("combobox"),{target:{value:"in-progress"}});
    fireEvent.click(screen.getByText("Update"));
    await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/patient-flow/flow-1/events",expect.objectContaining({method:"POST"})));
  });
});
