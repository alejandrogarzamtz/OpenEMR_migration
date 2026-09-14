# Specialized clinical forms

OpenRM retains OpenEMR encounter-form payloads losslessly in the generic
`clinical_forms.content` document while providing typed authoring contracts for
ten shipped form families. This
separates source preservation from modern validation: imported records remain
available as authored, while new and edited records must satisfy the selected
form's semantic rules.

Authenticated users with clinical access can retrieve the authoring metadata
from `GET /api/v1/clinical-form-definitions`. The React patient chart uses this
contract to render:

- four independent SOAP narrative sections;
- all 138 source ROS indicators with positive, negative, and not-assessed
  states; and
- all 37 source physical-examination lines with mutually exclusive status,
  diagnosis, and comments; and
- source-complete structured editors for dictation, progress notes, clinic
  notes, clinical instructions, aftercare plans, treatment plans, and transfer
  summaries.

The backend rejects unknown fields, invalid states, duplicate or unknown exam
lines, empty specialized forms, oversized narratives, and semantically invalid
updates. Existing signature and encounter-lock rules continue to apply after
validation. Historical source identifiers and spellings are retained where
changing them would break deterministic reconciliation.

Run the source-contract verifier after changing a definition:

```bash
python3 scripts/verify_clinical_form_definitions.py
```

The verifier always checks the modern contract against the versioned legacy
snapshot in `docs/legacy-clinical-form-contract.json`. When the ignored local
`openemr-legacy/` reference tree is available, it additionally reads the
preserved `form_soap` and `form_ros` SQL, the physical-exam line registry, and
the seven structured-form tables, then compares their exact identifier sets.
It emits stable counts, SHA-256 evidence, and the verification source. The
legacy progress-note `date_of_signature` maps to the append-only signature
timestamp instead of accepting a caller-controlled value. Relational care
plans, linked clinical notes, and specialized editors for the other installed
form families remain parity work.
