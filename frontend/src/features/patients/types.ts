export type Patient = {
  uuid: string;
  first_name: string;
  middle_name?: string;
  last_name: string;
  preferred_name?: string;
  date_of_birth: string;
  sex: string;
  gender_identity?: string;
  pronouns?: string;
  language?: string;
  race?: string;
  ethnicity?: string;
  email?: string;
  phone?: string;
  address_line_1?: string;
  address_line_2?: string;
  city?: string;
  state?: string;
  postal_code?: string;
  country_code?: string;
  portal_allowed: boolean;
  allow_email: boolean;
  allow_sms: boolean;
};

export type PatientInput = Omit<Patient, "uuid" | "portal_allowed">;

