import { FormEvent } from "react";
import type { PatientInput } from "./types";

type Props = { onSubmit: (patient: PatientInput) => Promise<void>; onCancel: () => void };

function optional(data: FormData, name: string) {
  const value = String(data.get(name) ?? "").trim();
  return value || undefined;
}

export function PatientForm({ onSubmit, onCancel }: Props) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await onSubmit({
      first_name: String(data.get("first_name")), middle_name: optional(data, "middle_name"),
      last_name: String(data.get("last_name")), preferred_name: optional(data, "preferred_name"),
      date_of_birth: String(data.get("date_of_birth")), sex: String(data.get("sex")),
      gender_identity: optional(data, "gender_identity"), pronouns: optional(data, "pronouns"),
      language: optional(data, "language"), race: optional(data, "race"), ethnicity: optional(data, "ethnicity"),
      email: optional(data, "email"), phone: optional(data, "phone"),
      address_line_1: optional(data, "address_line_1"), address_line_2: optional(data, "address_line_2"),
      city: optional(data, "city"), state: optional(data, "state"), postal_code: optional(data, "postal_code"),
      country_code: optional(data, "country_code"), allow_email: data.get("allow_email") === "on",
      allow_sms: data.get("allow_sms") === "on", duplicate_override_reason: optional(data, "duplicate_override_reason"),
    });
  }

  return <form className="patient-form card" onSubmit={submit}><h2>Nuevo paciente</h2><div className="form-grid">
    <label>Nombre<input name="first_name" required maxLength={100}/></label><label>Segundo nombre<input name="middle_name" maxLength={100}/></label>
    <label>Apellidos<input name="last_name" required maxLength={100}/></label><label>Nombre preferido<input name="preferred_name" maxLength={100}/></label>
    <label>Fecha de nacimiento<input name="date_of_birth" type="date" required/></label><label>Sexo al nacer<input name="sex" required maxLength={30}/></label>
    <label>Identidad de género<input name="gender_identity" maxLength={100}/></label><label>Pronombres<input name="pronouns" maxLength={100}/></label>
    <label>Idioma<input name="language" maxLength={100}/></label><label>Raza<input name="race" maxLength={100}/></label><label>Etnicidad<input name="ethnicity" maxLength={100}/></label>
    <label>Correo<input name="email" type="email"/></label><label>Teléfono<input name="phone" type="tel" maxLength={50}/></label>
    <label>Dirección<input name="address_line_1" maxLength={255}/></label><label>Dirección 2<input name="address_line_2" maxLength={255}/></label>
    <label>Ciudad<input name="city" maxLength={100}/></label><label>Estado<input name="state" maxLength={100}/></label>
    <label>Código postal<input name="postal_code" maxLength={30}/></label><label>País (ISO)<input name="country_code" minLength={2} maxLength={2}/></label>
  </div><label><input name="allow_email" type="checkbox"/> Autoriza correo</label><label><input name="allow_sms" type="checkbox"/> Autoriza SMS</label>
  <label>Justificación de excepción por duplicado<input name="duplicate_override_reason" minLength={10} maxLength={500} placeholder="Completar únicamente después de revisar una alerta de posible duplicado"/></label>
  <div className="form-actions"><button type="button" onClick={onCancel}>Cancelar</button><button>Guardar paciente</button></div></form>;
}
