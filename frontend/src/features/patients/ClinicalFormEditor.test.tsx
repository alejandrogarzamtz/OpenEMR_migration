// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ApiRequest } from "../../api/client";
import { ClinicalFormEditor } from "./ClinicalFormEditor";

const definitions={
  soap:{title:"SOAP note",kind:"narrative",fields:[{key:"subjective",label:"Subjective",type:"text"},{key:"assessment",label:"Assessment",type:"text"}]},
  ros:{title:"Review of systems",kind:"review-of-systems",fields:[{key:"fever",label:"Fever",type:"tri-state"}]},
  physical_exam:{title:"Physical examination",kind:"exam-findings",lines:[{line_id:"GENWELL",system:"GEN",label:"Appearance"}]},
  clinic_note:{title:"Clinical note",kind:"narrative",fields:[{key:"note",label:"Note",type:"text",required:true}]},
  dictation:{title:"Dictation",kind:"structured",fields:[{key:"dictation",label:"Dictation",type:"text",required:true},{key:"reviewed",label:"Reviewed",type:"boolean",required:true}]},
  custom:{title:"Custom form",kind:"custom-json"},
};

describe("ClinicalFormEditor",()=>{
  it("authors typed SOAP, ROS, and physical-exam payloads",async()=>{
    const api=vi.fn((path:string)=>Promise.resolve(path==="/api/v1/clinical-form-definitions"?definitions:{})) as unknown as ApiRequest;
    const saved=vi.fn();render(<ClinicalFormEditor api={api} patientUuid="patient-1" encounterUuid="encounter-1" onSaved={saved}/>);
    await screen.findByText("SOAP note");fireEvent.change(screen.getByLabelText("Título"),{target:{value:"Visit SOAP"}});fireEvent.change(screen.getByLabelText("Assessment"),{target:{value:"Migraine"}});fireEvent.click(screen.getByText("Guardar borrador"));
    await waitFor(()=>expect(api).toHaveBeenLastCalledWith("/api/v1/patients/patient-1/clinical-forms",expect.objectContaining({method:"POST",body:JSON.stringify({encounter_uuid:"encounter-1",form_type:"soap",title:"Visit SOAP",content:{subjective:"",assessment:"Migraine"}})})));
    fireEvent.change(screen.getByLabelText("Tipo de formulario"),{target:{value:"ros"}});fireEvent.change(screen.getByLabelText("Título"),{target:{value:"ROS"}});fireEvent.change(screen.getByLabelText("Fever"),{target:{value:"positive"}});fireEvent.click(screen.getByText("Guardar borrador"));
    await waitFor(()=>expect(api).toHaveBeenLastCalledWith("/api/v1/patients/patient-1/clinical-forms",expect.objectContaining({body:JSON.stringify({encounter_uuid:"encounter-1",form_type:"ros",title:"ROS",content:{fever:"positive"}})})));
    fireEvent.change(screen.getByLabelText("Tipo de formulario"),{target:{value:"physical_exam"}});fireEvent.change(screen.getByLabelText("Título"),{target:{value:"Exam"}});fireEvent.change(screen.getByLabelText("Appearance estado"),{target:{value:"normal"}});fireEvent.click(screen.getByText("Guardar borrador"));
    await waitFor(()=>expect(api).toHaveBeenLastCalledWith("/api/v1/patients/patient-1/clinical-forms",expect.objectContaining({body:JSON.stringify({encounter_uuid:"encounter-1",form_type:"physical_exam",title:"Exam",content:{findings:[{line_id:"GENWELL",status:"normal",diagnosis:"",comments:""}]}})})));
    fireEvent.change(screen.getByLabelText("Tipo de formulario"),{target:{value:"dictation"}});fireEvent.change(screen.getByLabelText("Título"),{target:{value:"Dictation"}});fireEvent.change(screen.getByLabelText("Dictation"),{target:{value:"Clinical narrative"}});fireEvent.click(screen.getByLabelText("Reviewed"));fireEvent.click(screen.getByText("Guardar borrador"));
    await waitFor(()=>expect(api).toHaveBeenLastCalledWith("/api/v1/patients/patient-1/clinical-forms",expect.objectContaining({body:JSON.stringify({encounter_uuid:"encounter-1",form_type:"dictation",title:"Dictation",content:{dictation:"Clinical narrative",reviewed:true}})})));
    expect(saved).toHaveBeenCalledTimes(4);
  });
});
