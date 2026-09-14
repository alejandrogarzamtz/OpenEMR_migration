// @vitest-environment jsdom
import React from "react";
import {render,screen} from "@testing-library/react";
import {describe,expect,it,vi} from "vitest";
import {ExternalClinicalData} from "./ExternalClinicalData";

describe("ExternalClinicalData",()=>{it("renders external encounters and procedures with provenance",async()=>{
 const api=vi.fn().mockResolvedValue({encounters:[{uuid:"e1",occurred_on:"2026-01-03",diagnosis:"Remote diagnosis",provider_name:"Dr Rivera",facility_name:"Partner Clinic",external_id:"EXT-E"}],procedures:[{uuid:"p1",occurred_on:"2026-01-04",code_system:"CPT",code:"71045",code_text:"Chest radiograph",facility_name:"Partner Imaging",external_id:"EXT-P"}]});
 render(<ExternalClinicalData api={api} patientUuid="patient-1"/>);
 expect(await screen.findByText("Remote diagnosis")).toBeTruthy();expect(screen.getByText("Chest radiograph")).toBeTruthy();expect(screen.getByText("Source ID EXT-P")).toBeTruthy();expect(api).toHaveBeenCalledWith("/api/v1/patients/patient-1/external-data");
})});
