// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InventoryWorkspace } from "./InventoryWorkspace";

describe("InventoryWorkspace",()=>{
  it("loads products and opens their lot ledger",async()=>{
    const product={uuid:"p1",name:"Test Vaccine",ndc_number:"0001",on_hand:8,reorder_point:"2",active:true};
    const api=vi.fn().mockResolvedValueOnce([product]).mockResolvedValueOnce([{uuid:"l1",lot_number:"LOT-1",warehouse_id:"main",on_hand:8,expiration:"2028-01-01"}]);
    render(<InventoryWorkspace api={api} language="en"/>);
    fireEvent.click(await screen.findByText("Test Vaccine"));
    expect(await screen.findByText("LOT-1")).toBeTruthy();
    expect(screen.getByText("8 on hand")).toBeTruthy();
    await waitFor(()=>expect(api).toHaveBeenCalledWith("/api/v1/inventory/products/p1/lots"));
  });
});
