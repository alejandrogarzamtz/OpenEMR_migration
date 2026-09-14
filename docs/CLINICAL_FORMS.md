# Specialized clinical forms

OpenRM retains OpenEMR encounter-form payloads losslessly in the generic
`clinical_forms.content` document while providing typed authoring contracts for
the shipped SOAP, review-of-systems (ROS), and physical-examination forms. This
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
  diagnosis, and comments.

The backend rejects unknown fields, invalid states, duplicate or unknown exam
lines, empty specialized forms, oversized narratives, and semantically invalid
updates. Existing signature and encounter-lock rules continue to apply after
validation. Historical source identifiers and spellings are retained where
changing them would break deterministic reconciliation.

Run the source-contract verifier after changing a definition:

```bash
python3 scripts/verify_clinical_form_definitions.py
```

The verifier reads the preserved `form_soap` and `form_ros` SQL plus the
physical-exam line registry, compares exact identifier sets, and emits stable
counts and SHA-256 evidence. Specialized editors for the remaining installed
form families, dictation, and form-specific clinical rules remain parity work.
