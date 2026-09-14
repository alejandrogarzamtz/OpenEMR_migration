// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PatientForm } from "./PatientForm";

describe("PatientForm", () => {
  it("normalizes optional fields and submits consent", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<PatientForm onSubmit={onSubmit} onCancel={() => undefined}/>);
    fireEvent.change(screen.getByLabelText("Nombre"), {target:{value:"Alex"}});
    fireEvent.change(screen.getByLabelText("Apellidos"), {target:{value:"Rivera"}});
    fireEvent.change(screen.getByLabelText("Fecha de nacimiento"), {target:{value:"1992-06-10"}});
    fireEvent.change(screen.getByLabelText("Sexo al nacer"), {target:{value:"female"}});
    fireEvent.change(screen.getByLabelText("Correo"), {target:{value:"alex@example.com"}});
    fireEvent.click(screen.getByLabelText("Autoriza correo"));
    fireEvent.click(screen.getByRole("button", {name:"Guardar paciente"}));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({first_name:"Alex",last_name:"Rivera",email:"alex@example.com",middle_name:undefined,allow_email:true,allow_sms:false});
  });
});

