# C-CDA and EHI export

OpenRM provides authenticated patient exports at:

- `GET /api/v1/patients/{patient_uuid}/ccda` for a C-CDA R2.1 XML clinical summary;
- `GET /api/v1/patients/{patient_uuid}/ehi-export` for a ZIP package containing
  the C-CDA document, a JSON designated record set, and `manifest.json`.

The designated record set begins with the requested patient and follows
declared database foreign keys outward. This preserves directly and indirectly
related migrated records without including another patient's chart. Binary
values are represented by byte length and SHA-256 rather than embedded in JSON;
the C-CDA document and JSON file each have a SHA-256 entry in the manifest.

Both operations require a staff clinical identity and append an audit event.
The package is generated on demand and is not retained by the API. Deployments
must protect downloaded files, configure appropriate retention outside OpenRM,
and validate organizational disclosure policy before production use. The
implementation and tests establish OpenRM's export contract; they do not imply
third-party certification or conformance attestation.
