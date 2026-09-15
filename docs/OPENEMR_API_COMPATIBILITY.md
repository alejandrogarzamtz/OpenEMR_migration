# OpenEMR API compatibility

OpenRM exposes compatibility URLs for integrations using OpenEMR's Standard
REST API: `/apis/default/api` for staff and `/apis/default/portal` for patients.
Responses retain the `validationErrors`, `internalErrors`, and `data` envelope.
Patient payloads accept and return `fname`, `mname`, `lname`, and `DOB` aliases.

The first group covers facilities, patients, encounters, practitioners,
appointments, version/product discovery, and all five legacy portal routes.
Staff routes enforce modern ACLs. Portal routes derive the patient only from the
authenticated portal session and never accept a caller-provided patient ID.

[`LEGACY_API_INVENTORY.md`](LEGACY_API_INVENTORY.md) records exact route status.
Unmigrated routes are not silently emulated; their underlying domain must be
completed before the compatibility contract is declared migrated.
