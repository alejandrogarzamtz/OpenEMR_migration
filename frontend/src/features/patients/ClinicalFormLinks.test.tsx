// @vitest-environment jsdom
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ClinicalFormLinks } from "./ClinicalFormLinks";

describe("ClinicalFormLinks",()=>{it("links and unlinks patient evidence",async()=>{
  let documents:any[]=[];const api=vi.fn(async(path:string,options?:RequestInit)=>{if(path.endsWith("/links"))return {documents,results:[]};if(options?.method==="POST"){documents=[{uuid:"d1",label:"scan.txt",linked_at:"2026-09-14T12:00:00Z"}];return {documents,results:[]};}if(options?.method==="DELETE"){documents=[];return;}throw new Error(path);});
  render(<ClinicalFormLinks api={api as any} patientUuid="p1" formUuid="f1" documents={[{uuid:"d1",name:"scan.txt"}]} results={[{uuid:"r1",name:"Hemoglobin",value:"13.4",unit:"g/dL"}]} locked={false}/>);await screen.findByText(/0 documento/);
  fireEvent.change(screen.getByLabelText("Documento para vincular"),{target:{value:"d1"}});fireEvent.submit(screen.getByLabelText("Documento para vincular").closest("form")!);await screen.findByText("scan.txt");
  fireEvent.click(screen.getByLabelText("Desvincular scan.txt"));await waitFor(()=>expect(screen.queryByLabelText("Desvincular scan.txt")).toBeNull());expect(api).toHaveBeenCalledWith(expect.stringContaining("/documents/d1"),{method:"DELETE"});
});});
